"""Native checkpoint recovery without a legacy geometry store."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event
import unittest

from cadgen._document import (AssemblyGroup, Document, GeometryLeaf, LogicalIdentity,
                              Mutation, NativeResult, OperatorSpec, RevisionState,
                              SubelementRef, TopologyHistory, TopologyRelation)
from cadgen._document.checkpoint import (CHECKPOINT_VERSION, CheckpointCodec,
                                        CheckpointCorrupt, CheckpointIncompatible,
                                        _native_topology_attestation, _shape_digest,
                                        _write_native, checkpoint_engine_version)
from cadgen._document.native import topology_map
from cadgen._document.resources import Cancelled
from cadgen._document.roots import IDENTITY_TRANSFORM, walk_root
from cadgen._document.storage import Catalog
from tests.python.packages.cadgen.document.test_core import BOX, box, volume


SELECT_FACE = OperatorSpec("test.checkpoint.face", "1", Mutation.READ_ONLY)


def translated(x: float) -> tuple[float, ...]:
    result = list(IDENTITY_TRANSFORM)
    result[3] = x
    return tuple(result)


def first_face(tx, root):
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    history = TopologyHistory(
        unchanged=(TopologyRelation(
            SubelementRef(0, "TopAbs_FACE", 2),
            (SubelementRef(None, "TopAbs_FACE", 1),)),),
        complete=True,
        reason="",
    )
    return tx.evaluate(
        SELECT_FACE, 1, (root,),
        lambda shapes, arena: NativeResult(
            TopExp_Explorer(shapes[0], TopAbs_FACE).Current(), history),
        logical_id="selected-face",
    )


def shared_face_compounds():
    """Two unrelated roots whose reachable topology shares one face."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS_Compound

    shared = TopExp_Explorer(
        BRepPrimAPI_MakeBox(1., 2., 3.).Shape(), TopAbs_FACE).Current()
    extras = (
        TopExp_Explorer(BRepPrimAPI_MakeBox(2., 4., 5.).Shape(),
                        TopAbs_FACE).Current(),
        TopExp_Explorer(BRepPrimAPI_MakeBox(3., 6., 7.).Shape(),
                        TopAbs_FACE).Current(),
    )
    builder = BRep_Builder()
    roots = []
    for extra in extras:
        root = TopoDS_Compound()
        builder.MakeCompound(root)
        builder.Add(root, shared)
        builder.Add(root, extra)
        roots.append(root)
    return tuple(roots)


def detached_shape(shape):
    """Standalone native roundtrip intentionally severs cross-root sharing."""
    from io import BytesIO
    from OCP.BinTools import BinTools, BinTools_FormatVersion
    from OCP.TopoDS import TopoDS_Shape

    stream = BytesIO()
    BinTools.Write_s(shape, stream, False, False,
                     BinTools_FormatVersion.BinTools_FormatVersion_VERSION_4)
    result = TopoDS_Shape()
    BinTools.Read_s(result, BytesIO(stream.getvalue()))
    return result


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="document-checkpoint-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "catalog"
        self.runtime = {"fixture": "checkpoint-v1"}
        self.catalog = Catalog(self.root, engine_version=checkpoint_engine_version())
        self.addCleanup(self.catalog.close)
        self.codec = CheckpointCodec(self.catalog, runtime=self.runtime)

    def revision(self):
        document = Document("checkpoint-part", runtime=self.runtime)
        with document.begin("captured-source", required_exports=("part.step",)) as tx:
            first = box(tx)
            tx._record(first, LogicalIdentity("first-box"))
            second = box(tx)
            face = first_face(tx, first)
            shared = AssemblyGroup("module", (
                GeometryLeaf("first", first, label="First", appearance={"color": (1., 0., 0., 1.)}),
                GeometryLeaf("second", second, translated(12.), label="Second",
                             appearance={"material": b"steel"}),
                GeometryLeaf("face", face, label="Selected face"),
            ), label="Shared")
            root = AssemblyGroup("root", (
                AssemblyGroup("left", (shared,), translated(-20.)),
                AssemblyGroup("right", (shared,), translated(20.)),
            ), appearance={"finish": {"roughness": .25}})
            tx.bind_root(root, unrepresented_metadata=())
            revision = tx.commit()
        document.complete_exports(revision.revision_id, ("part.step",))
        return document, revision, first, second, face

    def publish(self, document, revision):
        staged = self.codec.stage(document, revision.revision_id)
        expected = self.catalog.head(document.document_id)
        self.assertTrue(self.codec.commit(staged, expected_head=expected))
        return staged.revision_id

    def test_deep_allocation_chain_recovers_without_python_recursion(self):
        document = Document("deep", runtime=self.runtime)
        passthrough = OperatorSpec("test.deep.passthrough", "1", Mutation.READ_ONLY)
        with document.begin("deep-source") as tx:
            handle = box(tx)
            for _ in range(1100):
                handle = tx.evaluate(passthrough, (), (handle,),
                                     lambda shapes, arena: NativeResult(shapes[0]))
            tx.bind_root(GeometryLeaf("root", handle), unrepresented_metadata=())
            revision = tx.commit()
        self.publish(document, revision)
        recovered = self.codec.recover(document.document_id).document
        self.assertEqual(1101, len(recovered._allocations))
        for allocation in recovered._allocations.values():
            for parent in allocation.inputs:
                parent_bounds = recovered._allocations[parent.allocation_id].ancestry_interval
                self.assertLess(parent_bounds[1], allocation.ancestry_interval[1])
                self.assertLessEqual(allocation.ancestry_interval[0], parent_bounds[0])

    def test_roundtrip_preserves_revision_root_history_allocations_and_warm_reuse(self):
        source, revision, first, second, face = self.revision()
        catalog_revision = self.publish(source, revision)
        with self.catalog.lease(catalog_revision) as lease:
            self.catalog.record_export(
                lease, "part.step", hashlib.sha256(b"historical STEP").hexdigest(),
                {"version": 1, "kind": "historical-step"},
            )

        recovered = self.codec.recover(source.document_id, catalog_revision)
        document = recovered.document
        self.assertNotEqual(source.owner_id, document.owner_id)
        self.assertEqual(revision.revision_id, recovered.revision.revision_id)
        self.assertEqual(RevisionState.EXPORTS_COMPLETE, recovered.historical_state)
        self.assertEqual(("part.step",), recovered.historical_completed_exports)
        self.assertEqual(("part.step",), tuple(item.product for item in recovered.historical_receipts))
        self.assertEqual(RevisionState.GEOMETRY_READY,
                         document.state(recovered.revision.revision_id))
        self.assertEqual(set(), document._completed_exports[recovered.revision.revision_id])
        self.assertEqual(revision.required_exports, recovered.revision.required_exports)
        self.assertEqual(revision.source_identity, recovered.revision.source_identity)
        self.assertEqual(revision.unrepresented_metadata,
                         recovered.revision.unrepresented_metadata)
        self.assertEqual(
            {identity.value: handle.evaluation_id for identity, handle in revision.features.items()},
            {identity.value: handle.evaluation_id
             for identity, handle in recovered.revision.features.items()},
        )

        original_nodes = [(path, type(node).__name__, node.node_id.value, node.transform,
                           node.label, dict(node.appearance)
                           if hasattr(node.appearance, "items") else node.appearance)
                          for path, node in walk_root(revision.root)]
        recovered_nodes = [(path, type(node).__name__, node.node_id.value, node.transform,
                            node.label, dict(node.appearance)
                            if hasattr(node.appearance, "items") else node.appearance)
                           for path, node in walk_root(recovered.revision.root)]
        self.assertEqual(original_nodes, recovered_nodes)
        left, right = recovered.revision.root.children
        self.assertIs(left.children[0], right.children[0])

        by_allocation = {handle.allocation_id: handle
                         for handle in recovered.revision.evaluations}
        restored_first = by_allocation[first.allocation_id]
        restored_second = by_allocation[second.allocation_id]
        restored_face = by_allocation[face.allocation_id]
        self.assertEqual(first.prototype_id, restored_first.prototype_id)
        self.assertEqual(first.evaluation_id, restored_first.evaluation_id)
        self.assertEqual(second.allocation_id, restored_second.allocation_id)
        self.assertNotEqual(restored_first.allocation_id, restored_second.allocation_id)
        self.assertEqual(source.history(face), document.history(restored_face))
        self.assertTrue(topology_map(document._get(restored_first).shape).Contains(
            document._get(restored_face).shape))

        with document.begin("warm-replay") as tx:
            warm = tx.evaluate(
                BOX, (10., 8., 2.), (),
                lambda inputs, arena: self.fail("recovered prototype should be reused"),
            )
            warm_face = tx.evaluate(
                SELECT_FACE, 1, (warm,),
                lambda inputs, arena: self.fail("recovered dependency should be reused"),
            )
            self.assertEqual(restored_first.prototype_id, warm.prototype_id)
            self.assertEqual(restored_face.prototype_id, warm_face.prototype_id)
            self.assertEqual((tx.stats.computed, tx.stats.reused), (0, 2))
            tx._validate_handle(restored_first)
            tx._validate_handle(restored_second)
            tx._validate_handle(restored_face)
            private_first = tx.escape_arena.native(restored_first)
            private_second = tx.escape_arena.native(restored_second)
            private_face = tx.escape_arena.native(restored_face)
            self.assertFalse(private_first.IsSame(private_second))
            self.assertTrue(topology_map(private_first).Contains(private_face))
            self.assertIs(private_first, tx.escape_arena.native(restored_first))
            self.assertAlmostEqual(tx.query(restored_first, volume), 160.)

    def test_exact_catalog_revision_recovery_and_cas(self):
        source, first_revision, *_ = self.revision()
        first = self.publish(source, first_revision)
        with source.begin("changed") as tx:
            handle = box(tx, (3., 4., 5.))
            tx.bind_root(GeometryLeaf("changed", handle))
            second_revision = tx.commit()
        second_stage = self.codec.stage(source, second_revision.revision_id)
        self.assertFalse(self.codec.commit(second_stage, expected_head=None))
        second_stage = self.codec.stage(source, second_revision.revision_id)
        self.assertTrue(self.codec.commit(second_stage, expected_head=first))
        old = self.codec.recover(source.document_id, first)
        latest = self.codec.recover(source.document_id)
        old_handle = next(iter(old.revision.evaluations))
        latest_handle = next(iter(latest.revision.evaluations))
        with old.document.begin() as tx:
            self.assertAlmostEqual(tx.query(old_handle, volume), 160.)
        with latest.document.begin() as tx:
            self.assertAlmostEqual(tx.query(latest_handle, volume), 60.)

    def test_recovered_revision_pin_controls_resident_collection(self):
        source, revision, *_ = self.revision()
        recovered = self.codec.recover(source.document_id, self.publish(source, revision))
        document = recovered.document
        old_id = recovered.revision.revision_id
        old_handle = recovered.revision.evaluations[0]
        pin = document.pin(old_id)
        with document.begin("replacement") as tx:
            replacement = box(tx, (2., 2., 2.))
            tx.bind_root(GeometryLeaf("replacement", replacement))
            tx.commit()
        # The recovered export is deliberately a current unfulfilled
        # obligation. Mark failure here so this test isolates pin retention.
        document.fail(old_id)
        document.collect(keep_revisions=0)
        with document.begin("pinned-query") as tx:
            self.assertAlmostEqual(tx.query(old_handle, volume), 160., places=6)
        pin.release()
        document.collect(keep_revisions=0)
        with self.assertRaises(KeyError):
            document.pin(old_id)
        with self.assertRaises(ValueError):
            document._get(old_handle)

    def test_manifest_schema_runtime_and_native_payload_are_rejected(self):
        source, revision, *_ = self.revision()
        valid_id = self.publish(source, revision)
        with self.catalog.lease(valid_id) as lease:
            valid = self.catalog.read(lease)

        manifest = json.loads(valid.payloads["document-manifest"])
        manifest["version"] = CHECKPOINT_VERSION + 1
        bad_manifest = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        staged = self.catalog.stage(
            source.document_id, valid.metadata,
            {"document-manifest": bad_manifest,
             "document-native": valid.payloads["document-native"]},
        )
        self.assertTrue(self.catalog.checkpoint(staged, expected_head=valid_id))
        with self.assertRaises(CheckpointIncompatible):
            self.codec.recover(source.document_id, staged.revision_id)

        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        wrong_native, _relations = _write_native(
            (BRepPrimAPI_MakeBox(1., 1., 1.).Shape(),))
        staged_native = self.catalog.stage(
            source.document_id, valid.metadata,
            {"document-manifest": valid.payloads["document-manifest"],
             "document-native": wrong_native},
        )
        self.assertTrue(self.catalog.checkpoint(staged_native,
                                                expected_head=staged.revision_id))
        with self.assertRaises(CheckpointCorrupt):
            self.codec.recover(source.document_id, staged_native.revision_id)

        wrong_metadata = dict(valid.metadata, version=CHECKPOINT_VERSION + 1)
        staged_metadata = self.catalog.stage(source.document_id, wrong_metadata,
                                             valid.payloads)
        self.assertTrue(self.catalog.checkpoint(staged_metadata,
                                                expected_head=staged_native.revision_id))
        with self.assertRaises(CheckpointIncompatible):
            self.codec.recover(source.document_id, staged_metadata.revision_id)
        with self.assertRaises(CheckpointIncompatible):
            CheckpointCodec(self.catalog, runtime={"fixture": "other"}).recover(
                source.document_id, valid_id)

    def test_cancellation_releases_admission_without_staging(self):
        source, revision, *_ = self.revision()
        cancellation = Event()
        cancellation.set()
        with self.assertRaises(Cancelled):
            self.codec.stage(source, revision.revision_id, cancellation=cancellation)
        self.assertIsNone(self.catalog.head(source.document_id))
        self.assertEqual((0, 0, 0), source.admission.used)

    def test_equal_input_references_cannot_change_sharing_during_recovery(self):
        source = Document("sharing-proof", runtime=self.runtime)
        with source.begin() as tx:
            first, second = box(tx), box(tx)
            combined = tx.evaluate(
                OperatorSpec("sharing-sensitive", mutation=Mutation.READ_ONLY), (), (first, first),
                lambda shapes, arena: NativeResult(shapes[0]))
            tx.bind_root(GeometryLeaf("result", combined), unrepresented_metadata=())
            revision = tx.commit()
        valid_id = self.publish(source, revision)
        with self.catalog.lease(valid_id) as lease:
            valid = self.catalog.read(lease)
        manifest = json.loads(valid.payloads["document-manifest"])
        row = next(row for row in manifest["allocations"] if row["allocation_id"] == combined.allocation_id)
        self.assertEqual([first.allocation_id, first.allocation_id], row["inputs"])
        # Both handles have the same evaluation ID and geometry; changing only
        # this allocation edge must still invalidate the alias-sensitive key.
        row["inputs"][1] = second.allocation_id
        staged = self.catalog.stage(source.document_id, valid.metadata, {
            "document-manifest": json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(),
            "document-native": valid.payloads["document-native"],
        })
        self.assertTrue(self.catalog.checkpoint(staged, expected_head=valid_id))
        with self.assertRaisesRegex(CheckpointCorrupt, "sharing disagrees"):
            self.codec.recover(source.document_id, staged.revision_id)

    def test_catalog_module_remains_kernel_free(self):
        source_root = Path(__file__).resolve().parents[5] / "packages/cadgen/src"
        script = (
            "import sys\n"
            "from cadgen._document.storage import Catalog\n"
            "assert not any(name == 'OCP' or name.startswith('OCP.') for name in sys.modules)\n"
            "c = Catalog(sys.argv[1]); c.close()\n"
            "assert not any(name == 'OCP' or name.startswith('OCP.') for name in sys.modules)\n"
        )
        environment = dict(os.environ, PYTHONPATH=str(source_root))
        with tempfile.TemporaryDirectory(prefix="kernel-free-catalog-") as folder:
            result = subprocess.run(
                [sys.executable, "-c", script, str(Path(folder) / "catalog")],
                env=environment, capture_output=True, text=True, timeout=15,
            )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_incompatible_catalog_engine_requires_disposable_reset(self):
        source, revision, *_ = self.revision()
        self.publish(source, revision)
        self.catalog.close()
        wrong = Catalog(self.root, engine_version="other-checkpoint-runtime")
        self.addCleanup(wrong.close)
        self.assertIsNone(wrong.head(source.document_id))
        with self.assertRaises(CheckpointIncompatible):
            CheckpointCodec(wrong, runtime=self.runtime)

    def test_cross_prototype_subshape_sharing_is_attested_and_split_is_rejected(self):
        roots = shared_face_compounds()
        self.assertFalse(roots[0].IsSame(roots[1]))
        self.assertFalse(roots[0].IsPartner(roots[1]))
        self.assertFalse(topology_map(roots[0]).Contains(roots[1]))

        constructors = (
            OperatorSpec("test.checkpoint.shared-left", "1", Mutation.READ_ONLY,
                         closed_constructor=True),
            OperatorSpec("test.checkpoint.shared-right", "1", Mutation.READ_ONLY,
                         closed_constructor=True),
        )
        document = Document("shared-native-subshape", runtime=self.runtime)
        with document.begin("shared-face") as tx:
            handles = tuple(
                tx.evaluate(spec, (), (),
                            lambda inputs, arena, shape=shape: NativeResult(shape))
                for spec, shape in zip(constructors, roots)
            )
            tx.bind_root(AssemblyGroup("shared", tuple(
                GeometryLeaf(f"part-{index}", handle)
                for index, handle in enumerate(handles)
            )))
            revision = tx.commit()
        valid_id = self.publish(document, revision)
        with self.catalog.lease(valid_id) as lease:
            valid = self.catalog.read(lease)
        manifest = json.loads(valid.payloads["document-manifest"])
        # The shared graph survives the one global native payload before the
        # negative test substitutes an independently serialized prototype.
        self.codec.recover(document.document_id, valid_id)
        memberships = manifest["native_topology"]["prototypes"]
        shared_classes = ({member[0] for member in memberships[0]}
                          & {member[0] for member in memberships[1]})
        # More than the face itself is shared: its wire, edges, and vertices
        # have the same TShapes across the two unrelated compound roots.
        self.assertGreater(len(shared_classes), 1)

        ordered_shapes = tuple(document._prototypes[key].shape
                               for key in sorted(document._prototypes))
        split_second = detached_shape(ordered_shapes[1])
        self.assertEqual(_shape_digest(ordered_shapes[1]),
                         _shape_digest(split_second))
        split_native, split_topology = _write_native(
            (ordered_shapes[0], split_second))
        self.assertNotEqual(manifest["native_topology"], split_topology)
        staged = self.catalog.stage(
            document.document_id, valid.metadata,
            {"document-manifest": valid.payloads["document-manifest"],
             "document-native": split_native},
        )
        self.assertTrue(self.catalog.checkpoint(staged, expected_head=valid_id))
        with self.assertRaisesRegex(CheckpointCorrupt, "topology alias relationships"):
            self.codec.recover(document.document_id, staged.revision_id)

    def test_topology_attestation_distinguishes_same_partner_and_allocation(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Trsf, gp_Vec

        original = BRepPrimAPI_MakeBox(1., 2., 3.).Shape()
        transform = gp_Trsf()
        transform.SetTranslation(gp_Vec(9., 0., 0.))
        moved = original.Moved(TopLoc_Location(transform))
        reversed_shape = original.Reversed()
        independent = BRepPrimAPI_MakeBox(1., 2., 3.).Shape()
        topology = _native_topology_attestation(
            (original, moved, reversed_shape, independent))
        original_root, moved_root, reversed_root, independent_root = (
            members[0] for members in topology["prototypes"])
        self.assertNotEqual(original_root[0], moved_root[0])
        self.assertEqual(original_root[1], moved_root[1])
        original_location = topology["same_classes"][original_root[0] - 1][1]
        moved_location = topology["same_classes"][moved_root[0] - 1][1]
        self.assertNotEqual(original_location, moved_location)
        self.assertEqual(original_root[:2], reversed_root[:2])
        self.assertNotEqual(original_root[2], reversed_root[2])
        self.assertNotEqual(original_root[1], independent_root[1])

    def test_topology_attestation_manifest_growth_is_linear_diagnostic(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

        shapes = tuple(BRepPrimAPI_MakeBox(1., 2., 3.).Shape()
                       for _ in range(300))

        def evidence(count):
            topology = _native_topology_attestation(shapes[:count])
            size = len(json.dumps(topology, sort_keys=True,
                                  separators=(",", ":")).encode())
            memberships = sum(len(row) for row in topology["prototypes"])
            return topology, size, memberships

        one_hundred, size_100, members_100 = evidence(100)
        three_hundred, size_300, members_300 = evidence(300)
        self.assertEqual(3 * members_100, members_300)
        self.assertEqual(members_100, len(one_hundred["same_classes"]))
        self.assertEqual(members_100, one_hundred["partner_classes"])
        self.assertEqual(members_300, len(three_hundred["same_classes"]))
        self.assertEqual(members_300, three_hundred["partner_classes"])
        self.assertEqual(1, len(one_hundred["locations"]))
        self.assertEqual(1, len(three_hundred["locations"]))
        # Decimal class identifiers grow slightly wider, but there is no
        # prototype-pair matrix. The 3x topology input stays well below 4x.
        self.assertLess(size_300, size_100 * 4)


if __name__ == "__main__":
    unittest.main()
