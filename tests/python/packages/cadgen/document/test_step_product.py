"""Pinned-root STEP proof: bytes, readback provenance, ownership, publication."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import math
from pathlib import Path
from threading import Event
import unittest
from unittest.mock import patch

from cadgen._document import Document, ExportConflict, Mutation, NativeResult, OperatorSpec, RevisionState
from cadgen._document.resources import Cancelled
from cadgen._document.roots import AssemblyGroup, GeometryLeaf, IDENTITY_TRANSFORM
from cadgen._document.step_product import (StepOptions, StepProductSession, UnsupportedStepProduct,
                                          _owned_xcaf_document, destination_digest)
from tests.python.support.tmp_root import generated_cad_directory


BOX = OperatorSpec("test.step-product.box", "1", Mutation.READ_ONLY)
PLATE = OperatorSpec("test.step-product.plate", "1", Mutation.READ_ONLY)


def translation(x=0., y=0., z=0.):
    values = list(IDENTITY_TRANSFORM)
    values[3], values[7], values[11] = x, y, z
    return tuple(values)


def box(tx, size=(4., 3., 2.)):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    return tx.evaluate(BOX, size, (), lambda inputs, arena: NativeResult(BRepPrimAPI_MakeBox(*size).Shape()))


def plate(tx):
    def compute(inputs, arena):
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
        native = BRepPrimAPI_MakeBox(16., 8., 2.).Shape()
        for x in (4., 12.):
            hole = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, 4., -1.), gp_Dir(0., 0., 1.)), 1., 4.).Shape()
            native = BRepAlgoAPI_Cut(native, hole).Shape()
        return NativeResult(native)
    return tx.evaluate(PLATE, (), (), compute)


def native_volume(native):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    values = GProp_GProps()
    BRepGProp.VolumeProperties_s(native, values)
    return values.Mass()


class StepProductTests(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="document-step-product-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.target = self.directory / "part.step"
        self.doc = Document("step-products", runtime={"fixture": "v1"})

    def revision(self, *, size=(4., 3., 2.), transform=IDENTITY_TRANSFORM,
                 label="part", appearance=(), required_exports=None,
                 coverage=(), root_builder=None, primitive=box):
        exports = (str(self.target),) if required_exports is None else required_exports
        with self.doc.begin("ordinary Python replay", required_exports=exports) as tx:
            handle = primitive(tx, size) if primitive is box else primitive(tx)
            root = (root_builder(handle) if root_builder else
                    GeometryLeaf("part", handle, transform, label, appearance))
            tx.bind_root(root, unrepresented_metadata=coverage)
            revision = tx.commit()
        return revision, handle

    def session(self, revision):
        return StepProductSession(self.doc, revision.revision_id, work_directory=self.directory / "staging")

    def assert_bounds(self, actual, expected):
        for value, wanted in zip(actual, expected):
            self.assertAlmostEqual(value, wanted, places=6)

    def test_small_plate_readback_is_immutable_and_byte_bound(self):
        revision, _ = self.revision(primitive=plate, appearance={"color": (.2, .4, .6, 1.)})
        with self.session(revision) as session:
            product = session.prepare(self.target.name)
            self.assertEqual(hashlib.sha256(product.payload).hexdigest(), product.sha256)
            saved = product.returned_root
            self.assertEqual(saved.name, "part")
            self.assertEqual((saved.geometry.solids, saved.geometry.faces), (1, 8))
            self.assertAlmostEqual(saved.geometry.volume, 256. - 4. * math.pi, places=6)
            self.assert_bounds(saved.geometry.bounds, (0., 0., 0., 16., 8., 2.))
            self.assertTrue(saved.geometry.valid)
            self.assertEqual(session.metrics.prototype_copies, 1)
            self.assertEqual(session.metrics.independent_parses, 1)
            self.assertFalse(self.target.exists())
            with self.assertRaises(FrozenInstanceError):
                product.sha256 = "other"
            receipt = session.publish(self.target, expected_prior_digest=None)
            self.assertEqual(receipt.sha256, destination_digest(self.target))
            self.assertEqual(receipt.revision_id, revision.revision_id)
            self.assertEqual(self.doc.state(revision.revision_id), RevisionState.EXPORTS_COMPLETE)

    def test_unchanged_root_reuses_bytes_across_new_allocations(self):
        first, a = self.revision(primitive=plate)
        with self.session(first) as session:
            original = session.prepare(self.target.name)
            session.publish(self.target, expected_prior_digest=None)
        second, b = self.revision(primitive=plate)
        self.assertEqual(a.prototype_id, b.prototype_id)
        self.assertNotEqual(a.allocation_id, b.allocation_id)
        with self.session(second) as session, \
             patch("cadgen._document.step_product.copy_shape", side_effect=AssertionError("native copy on byte hit")), \
             patch("cadgen.step_export.write_xcaf_doc_step_file", side_effect=AssertionError("STEP rewrite on byte hit")), \
             patch("cadgen._document.step_product._read_saved_metadata", side_effect=AssertionError("readback on byte hit")):
            reused = session.prepare(self.target.name)
            self.assertIs(reused, original)
            self.assertEqual((session.metrics.reused, session.metrics.computed,
                              session.metrics.prototype_copies, session.metrics.independent_parses), (1, 0, 0, 0))
            before = self.target.stat().st_mtime_ns
            receipt = session.publish(self.target, expected_prior_digest=original.sha256)
            self.assertEqual(receipt.action, "verified-existing")
            self.assertEqual(self.target.stat().st_mtime_ns, before)

    def test_24_repeated_occurrences_copy_and_parse_one_definition(self):
        def assembly(handle):
            return AssemblyGroup("assembly", tuple(GeometryLeaf(f"p{i}", handle,
                                 translation(i * 5., 0., 0.), f"part-{i}") for i in range(24)), label="assembly")
        revision, _ = self.revision(root_builder=assembly)
        from cadgen._document import step_product
        with self.session(revision) as session, patch.object(step_product, "_geometry_facts", wraps=step_product._geometry_facts) as facts:
            product = session.prepare(self.target.name)
            self.assertEqual(session.metrics.prototype_copies, 1)
            self.assertEqual(facts.call_count, 1)
            saved = product.returned_root
            self.assertEqual(len(saved.children), 24)
            for i, child in enumerate(saved.children):
                self.assertEqual(child.name, f"part-{i}")
                self.assert_bounds(child.geometry.bounds, (i * 5., 0., 0., i * 5. + 4., 3., 2.))

    def test_nested_hierarchy_inherits_color_and_preserves_root_placement(self):
        def assembly(handle):
            group = AssemblyGroup("group", (GeometryLeaf("one", handle, translation(2., 0., 0.), "one"),
                                             GeometryLeaf("two", handle, translation(8., 0., 0.), "two")),
                                  translation(0., 10., 0.), "group", {"color": (.2, .4, .6, 1.)})
            return AssemblyGroup("root", (group,), translation(20., 0., 3.), "root")
        revision, _ = self.revision(root_builder=assembly)
        with self.session(revision) as session:
            product = session.prepare(self.target.name)
            saved = product.returned_root
            self.assertEqual(product.returned_root_path, (1, 1))
            self.assertIs(saved, product.saved_roots[0].children[0])
            self.assertEqual(product.saved_roots[0].local_transform, IDENTITY_TRANSFORM)
            self.assertEqual(saved.name, "root")
            self.assertEqual(saved.children[0].name, "group")
            one, two = saved.children[0].children
            self.assert_bounds(one.geometry.bounds, (22., 10., 3., 26., 13., 5.))
            self.assert_bounds(two.geometry.bounds, (28., 10., 3., 32., 13., 5.))
            for actual, expected in zip(one.color, (.2, .4, .6, 1.)):
                self.assertAlmostEqual(actual, expected, places=6)
            self.assertEqual(one.color, two.color)
            self.assertEqual(session.metrics.prototype_copies, 1)

    def test_occurrence_colors_are_independent_for_one_prototype(self):
        red, blue = (1., 0., 0., 1.), (0., 0., 1., 1.)
        def assembly(handle):
            return AssemblyGroup("colors", (GeometryLeaf("red", handle, label="red", appearance={"color": red}),
                                              GeometryLeaf("blue", handle, translation(5., 0., 0.), "blue", {"color": blue})),
                                 label="colors")
        revision, _ = self.revision(root_builder=assembly)
        with self.session(revision) as session:
            product = session.prepare(self.target.name)
            self.assertEqual([child.color for child in product.returned_root.children], [red, blue])
            self.assertEqual(session.metrics.prototype_copies, 1)
            self.assertEqual(session.metrics.appearance_copies, 1)

    def test_placement_name_color_and_geometry_change_product_identity(self):
        signatures = []
        cases = ({}, {"transform": translation(5., 0., 0.)}, {"label": "renamed"},
                 {"appearance": {"color": (1., 0., 0., 1.)}}, {"size": (5., 3., 2.)})
        for settings in cases:
            with self.subTest(settings=settings):
                revision, _ = self.revision(**settings)
                with self.session(revision) as session:
                    product = session.prepare(self.target.name)
                    self.assertEqual(session.metrics.computed, 1)
                    signatures.append(product.identity)
                    saved = product.returned_root
                    self.assertEqual(saved.name, settings.get("label", "part"))
                    if "transform" in settings:
                        self.assert_bounds(saved.geometry.bounds, (5., 0., 0., 9., 3., 2.))
                    if "size" in settings:
                        self.assertAlmostEqual(saved.geometry.volume, 30.)
        self.assertEqual(len(set(signatures)), len(cases))

    def test_prototype_native_location_composes_with_occurrence_transform(self):
        def located(tx):
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
            from OCP.gp import gp_Trsf, gp_Vec
            from OCP.TopLoc import TopLoc_Location
            def compute(inputs, arena):
                pose = gp_Trsf()
                pose.SetTranslation(gp_Vec(7., 0., 0.))
                return NativeResult(BRepPrimAPI_MakeBox(4., 3., 2.).Shape().Moved(TopLoc_Location(pose)))
            return tx.evaluate(OperatorSpec("test.step-product.native-placement"), (), (), compute)
        revision, _ = self.revision(primitive=located, transform=translation(0., 5., 0.))
        with self.session(revision) as session:
            saved = session.prepare(self.target.name).returned_root
            self.assert_bounds(saved.geometry.bounds, (7., 5., 0., 11., 8., 2.))

    def test_saved_facts_follow_lossy_step_bytes_not_authored_native(self):
        import build123d as bd
        def cap(tx):
            def compute(inputs, arena):
                sphere = bd.Rot(90, 0, 0) * bd.Rot(0, 0, -90) * bd.Sphere(1)
                ellipsoid = sphere.transform_geometry(bd.Matrix([[2.7, 0, 0, 0], [0, 2.7, 0, 0],
                                                                 [0, 0, 1.4, 0], [0, 0, 0, 1]]))
                pad = bd.Pos(0, 0, 5.4) * ellipsoid
                shape = pad - bd.Pos(0, 0, 4.15 - 10) * bd.Box(30, 30, 20)
                return NativeResult(shape.wrapped)
            return tx.evaluate(OperatorSpec("test.step-product.lossy-cap"), (), (), compute)
        revision, handle = self.revision(primitive=cap)
        authored_volume = native_volume(self.doc._get(handle).shape)
        with self.session(revision) as session:
            product = session.prepare(self.target.name)
            session.publish(self.target, expected_prior_digest=None)
            saved_volume = product.returned_root.geometry.volume
        imported = bd.import_step(str(self.target))
        self.assertAlmostEqual(saved_volume, imported.volume, places=6)
        self.assertGreater(authored_volume, 40.)
        self.assertLess(saved_volume, 1.)
        self.assertGreater(abs(authored_volume - saved_volume), 1.)
        self.assertAlmostEqual(native_volume(self.doc._get(handle).shape), authored_volume)

    def test_private_materialization_cannot_mutate_retained_prototype(self):
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.TDF import TDF_LabelSequence
        from OCP.XCAFDoc import XCAFDoc_DocumentTool
        from OCP.gp import gp_Pnt
        revision, handle = self.revision()
        def first_vertex(native):
            return TopoDS.Vertex_s(TopExp_Explorer(native, TopAbs_VERTEX).Current())
        retained = first_vertex(self.doc._get(handle).shape)
        original = BRep_Tool.Pnt_s(retained).Coord()
        with self.session(revision) as session, _owned_xcaf_document() as document:
            session._materialize_xcaf(document)
            shapes = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
            roots = TDF_LabelSequence()
            shapes.GetFreeShapes(roots)
            private = first_vertex(shapes.GetShape_s(roots.Value(1)))
            self.assertFalse(private.IsPartner(retained))
            BRep_Builder().UpdateVertex(private, gp_Pnt(40., 20., 10.), .01)
            self.assertEqual(BRep_Tool.Pnt_s(retained).Coord(), original)

    def test_publication_restores_missing_and_externally_changed_bytes(self):
        revision, _ = self.revision()
        with self.session(revision) as session:
            product = session.prepare(self.target.name)
            for prior in (None, b"external edit", None):
                if prior is None:
                    self.target.unlink(missing_ok=True)
                else:
                    self.target.write_bytes(prior)
                expected = destination_digest(self.target)
                receipt = session.publish(self.target, expected_prior_digest=expected)
                self.assertEqual(receipt.previous_sha256, expected)
                self.assertEqual(receipt.action, "written")
                self.assertEqual(self.target.read_bytes(), product.payload)
            self.assertEqual(session.metrics.writes, 3)

    def test_output_conflicts_preserve_bytes_and_export_obligation(self):
        revision, _ = self.revision()
        with self.session(revision) as session:
            session.prepare(self.target.name)
            self.target.write_bytes(b"external editor")
            with self.assertRaises(ExportConflict):
                session.publish(self.target, expected_prior_digest=None)
            self.assertEqual(self.target.read_bytes(), b"external editor")
            self.assertEqual(self.doc.state(revision.revision_id), RevisionState.GEOMETRY_READY)
            second, _ = self.revision(size=(6., 3., 2.))
            with self.assertRaises(ExportConflict):
                session.publish(self.target, expected_prior_digest=destination_digest(self.target))
            self.assertEqual(self.doc.state(second.revision_id), RevisionState.GEOMETRY_READY)
            self.assertEqual(self.target.read_bytes(), b"external editor")

    def test_each_declared_export_requires_actual_publication_and_exact_pin(self):
        second_path = self.directory / "second" / self.target.name
        revision, _ = self.revision(required_exports=(str(self.target), str(second_path)))
        session = self.session(revision)
        try:
            session.prepare(self.target.name)
            with self.assertRaises(ValueError):
                session.publish(self.directory / "undeclared" / self.target.name, expected_prior_digest=None)
            session.publish(self.target, expected_prior_digest=None)
            self.assertEqual(self.doc.state(revision.revision_id), RevisionState.GEOMETRY_READY)
            session.publish(second_path, expected_prior_digest=None)
            self.assertEqual(self.doc.state(revision.revision_id), RevisionState.EXPORTS_COMPLETE)
        finally:
            session.close()
        with self.assertRaises(RuntimeError):
            session.prepare(self.target.name)

    def test_unknown_or_unsupported_metadata_rejects_cold_product(self):
        for coverage in (None, ("cad_material",), ("cad_face_ordinal_colors",), ("_occurrence_tree",)):
            with self.subTest(coverage=coverage):
                revision, _ = self.revision(coverage=coverage)
                with self.assertRaises(UnsupportedStepProduct):
                    self.session(revision)
                self.assertEqual(self.doc._pins[revision.revision_id], 0)
        revision, _ = self.revision(appearance={"roughness": .3})
        with self.assertRaises(UnsupportedStepProduct):
            self.session(revision)

    def test_options_basename_and_runtime_are_serialization_identity(self):
        revision, _ = self.revision()
        identities = []
        with self.session(revision) as session:
            for name, options in (("part.step", StepOptions()), ("other.step", StepOptions()),
                                  ("part.step", StepOptions(originating_system="other writer")),
                                  ("part.step", StepOptions(schema="AP242DIS"))):
                identities.append(session.prepare(name, options=options).identity)
            self.doc.runtime = {"fixture": "v2"}
            identities.append(session.prepare("part.step").identity)
        self.assertEqual(len(identities), len(set(identities)))

    def test_material_tag_and_logical_keys_keep_fresh_root_but_reuse_step_bytes(self):
        first, _ = self.revision(appearance={"material": "aluminum"})
        with self.session(first) as session:
            original = session.prepare(self.target.name)
        second, _ = self.revision(root_builder=lambda handle:
                                 GeometryLeaf("new-logical-key", handle, label="part",
                                              appearance={"material": "steel"}))
        with self.session(second) as session:
            self.assertIs(session.prepare(self.target.name), original)
            self.assertEqual(session.metrics.reused, 1)
            self.assertEqual(session._pin.revision.root.appearance["material"], "steel")
            self.assertEqual(session._pin.revision.root.node_id.value, "new-logical-key")

    def test_collection_keeps_pinned_products_then_reclaims_unreachable_bytes(self):
        first, _ = self.revision(required_exports=())
        session = self.session(first)
        try:
            product = session.prepare(self.target.name)
            self.revision(size=(6., 3., 2.), required_exports=())
            self.doc.collect(keep_revisions=0)
            self.assertIn(product.identity, self.doc._step_products.entries)
            self.assertIs(session.prepare(self.target.name), product)
        finally:
            session.close()
        self.doc.collect(keep_revisions=0)
        self.assertNotIn(product.identity, self.doc._step_products.entries)
        self.assertEqual(self.doc._step_products.total_bytes, 0)

    def test_product_registry_limits_entries_and_oversize_payload_retention(self):
        revision, _ = self.revision()
        with self.session(revision) as session, patch("cadgen._document.step_product._MAX_PRODUCTS", 2):
            products = [session.prepare(f"part-{index}.step") for index in range(3)]
            self.assertNotIn(products[0].identity, self.doc._step_products.entries)
            self.assertEqual(len(self.doc._step_products.entries), 2)
            self.assertEqual(self.doc._step_products.total_bytes, sum(len(p.payload) for p in products[1:]))
        with self.session(revision) as session, patch("cadgen._document.step_product._MAX_PRODUCT_BYTES", 1):
            oversized = session.prepare("oversized.step")
            self.assertNotIn(oversized.identity, self.doc._step_products.entries)
            self.assertTrue(oversized.payload)

    def test_independent_documents_emit_identical_bytes_without_allocation_ids(self):
        def assembly(handle):
            return AssemblyGroup("assembly", tuple(GeometryLeaf(f"p{i}", handle,
                                 translation(i * 5., 0., 0.), f"part-{i}",
                                 {"color": ((1., 0., 0., 1.) if i % 2 else (0., 0., 1., 1.))})
                                 for i in range(24)), label="assembly")
        first, a = self.revision(root_builder=assembly)
        with self.session(first) as session:
            original = session.prepare(self.target.name)
        self.doc = Document("independently evaluated", runtime={"fixture": "v1"})
        second, b = self.revision(root_builder=assembly)
        self.assertNotEqual(a.owner_id, b.owner_id)
        self.assertNotEqual(a.allocation_id, b.allocation_id)
        with self.session(second) as session:
            independent = session.prepare(self.target.name)
            self.assertEqual(session.metrics.computed, 1)
            self.assertEqual(session.metrics.reused, 0)
        self.assertEqual(independent.identity, original.identity)
        self.assertEqual(independent.payload, original.payload)
        self.assertEqual(independent.saved_roots, original.saved_roots)

    def test_private_xcaf_documents_do_not_accumulate_in_global_application(self):
        from OCP.XCAFApp import XCAFApp_Application
        application = XCAFApp_Application.GetApplication_s()
        before = application.NbDocuments()
        revision, _ = self.revision()
        with self.session(revision) as session:
            session.prepare(self.target.name)
            with patch("cadgen.step_export.write_xcaf_doc_step_file", side_effect=RuntimeError("writer failure")):
                with self.assertRaisesRegex(RuntimeError, "writer failure"):
                    session.prepare("failure.step")
        self.assertEqual(application.NbDocuments(), before)

    def test_cancellation_and_unsupported_transform_do_not_publish(self):
        revision, _ = self.revision()
        cancellation = Event()
        with StepProductSession(self.doc, revision.revision_id, work_directory=self.directory / "staging",
                                cancellation=cancellation) as session:
            cancellation.set()
            with self.assertRaises(Cancelled):
                session.prepare(self.target.name)
        self.assertFalse(self.target.exists())
        transform = list(IDENTITY_TRANSFORM)
        transform[1] = .2
        revision, _ = self.revision(transform=transform)
        with self.session(revision) as session:
            with self.assertRaises(UnsupportedStepProduct):
                session.prepare(self.target.name)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
