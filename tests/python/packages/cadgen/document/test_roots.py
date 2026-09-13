"""Returned hierarchy is independent of temporary computations and exports."""
from dataclasses import FrozenInstanceError, replace
import unittest
from unittest.mock import patch

from cadgen._document import (AssemblyGroup, Document, GeometryLeaf,
                             IDENTITY_TRANSFORM, LogicalIdentity, RevisionState,
                             root_handles, walk_root)
from tests.python.packages.cadgen.document.test_core import box, volume


def translated(x):
    result = list(IDENTITY_TRANSFORM)
    result[3] = x
    return result


class ReturnedRootTests(unittest.TestCase):
    def test_metadata_coverage_is_explicit_and_invalid_binding_is_atomic(self):
        document = Document("metadata-coverage")
        with document.begin() as tx:
            leaf = GeometryLeaf("part", box(tx))
            tx.bind_root(leaf)
            self.assertIsNone(tx.commit().unrepresented_metadata)
        with document.begin() as tx:
            tx.bind_root(leaf, unrepresented_metadata=("cad_material",))
            for invalid in ([], "cad_material", ("",), (1,)):
                with self.subTest(invalid=invalid), self.assertRaises(TypeError):
                    tx.bind_root(replace(leaf, label="invalid"), unrepresented_metadata=invalid)
            revision = tx.commit()
            self.assertIs(leaf, revision.root)
            self.assertEqual(("cad_material",), revision.unrepresented_metadata)
        with document.begin() as tx:
            tx.bind_root(leaf, unrepresented_metadata=())
            self.assertEqual((), tx.commit().unrepresented_metadata)

    def test_direct_solid_identifies_only_returned_geometry_among_tools(self):
        document = Document("direct-solid")
        with document.begin(required_exports=("part.step",)) as tx:
            tool = box(tx, (1., 1., 1.))
            result = box(tx, (3., 4., 5.))
            root = tx.bind_root(GeometryLeaf("result", result, label="Part"))
            revision = tx.commit()
        self.assertIs(revision.root, root)
        self.assertIn(tool, revision.evaluations)
        self.assertEqual(root_handles(revision.root), (result,))
        self.assertEqual(document.state(revision.revision_id), RevisionState.GEOMETRY_READY)
        document.complete_exports(revision.revision_id, ("part.step",))
        self.assertEqual(document.state(revision.revision_id), RevisionState.EXPORTS_COMPLETE)

    def test_discarded_compounds_and_occurrences_are_not_scene_members(self):
        document = Document("discarded-groups")
        with document.begin() as tx:
            discarded = box(tx, (1., 1., 1.))
            returned = box(tx)
            unused = AssemblyGroup("unused", (GeometryLeaf("tool", discarded),))
            root = AssemblyGroup("returned", (GeometryLeaf("part", returned),))
            tx.bind_root(root)
            revision = tx.commit()
        self.assertNotIn(unused, [node for _, node in walk_root(revision.root)])
        self.assertEqual(root_handles(revision.root), (returned,))

    def test_shared_subassemblies_have_path_scoped_occurrences(self):
        document = Document("repeated-subassemblies")
        with document.begin() as tx:
            part = box(tx)
            shared = AssemblyGroup("module", (
                GeometryLeaf("part", part, label="Repeated label"),
                GeometryLeaf("other", part, translated(4), label="Repeated label")))
            root = AssemblyGroup("root", (
                AssemblyGroup("left", (shared,), translated(-10)),
                AssemblyGroup("right", (shared,), translated(10))))
            tx.bind_root(root)
            revision = tx.commit()
        paths = [path for path, node in walk_root(revision.root) if isinstance(node, GeometryLeaf)]
        self.assertEqual(paths, [("root", "left", "module", "part"),
                                ("root", "left", "module", "other"),
                                ("root", "right", "module", "part"),
                                ("root", "right", "module", "other")])
        self.assertEqual(root_handles(root), (part,))
        self.assertEqual(root.children[0].transform[3], -10.)
        self.assertEqual(shared.children[1].transform[3], 4.)

    def test_material_only_revision_needs_no_evaluation_copy_or_codec(self):
        document = Document("material-edit")
        appearance = {"color": [1., 0., 0.], "finish": {"roughness": .2}}
        with document.begin() as tx:
            part = box(tx)
            root = GeometryLeaf("part", part, appearance=appearance)
            tx.bind_root(root)
            tx.commit()
        appearance["color"][0] = 0.
        appearance["finish"]["roughness"] = .9
        self.assertEqual(root.appearance["color"], (1., 0., 0.))
        self.assertEqual(root.appearance["finish"]["roughness"], .2)
        with self.assertRaises(FrozenInstanceError):
            root.label = "changed"
        with self.assertRaises(TypeError):
            root.appearance["color"] = (0., 0., 0.)
        with patch("cadgen._document.core.copy_shape", side_effect=AssertionError("copy")), \
             patch("cadgen._document.core.copy_many", side_effect=AssertionError("copy")), \
             patch("OCP.BinTools.BinTools.Write_s", side_effect=AssertionError("codec")), \
             patch("OCP.BinTools.BinTools.Read_s", side_effect=AssertionError("codec")):
            with document.begin() as tx:
                edited = replace(root, appearance={"color": (0., 1., 0.)})
                tx.bind_root(edited)
                revision = tx.commit()
                self.assertEqual((tx.stats.computed, tx.stats.reused, tx.stats.native_copies), (0, 0, 0))
        self.assertEqual(revision.root.geometry, part)
        self.assertEqual(root.appearance["color"], (1., 0., 0.))

    def test_duplicate_sibling_keys_cycles_and_empty_root_are_rejected(self):
        document = Document("invalid-tree")
        with document.begin() as tx:
            part = box(tx)
            leaf = GeometryLeaf("part", part)
            tx.bind_root(leaf)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                tx.bind_root(AssemblyGroup("root", (leaf, replace(leaf, label="different"))))
            cyclic = AssemblyGroup("cycle", ())
            object.__setattr__(cyclic, "children", (cyclic,))
            with self.assertRaisesRegex(ValueError, "cycle"):
                tx.bind_root(cyclic)
            with self.assertRaisesRegex(ValueError, "reachable geometry"):
                tx.bind_root(AssemblyGroup("empty", ()))
            with self.assertRaises(TypeError):
                tx.bind_root(AssemblyGroup("wrong-child", (object(),)))
            # Failed binding never replaces the last validated candidate root.
            self.assertIs(tx.commit().root, leaf)

    def test_foreign_stale_and_spoofed_allocation_handles_are_rejected(self):
        document = Document("owner")
        foreign = Document("foreign")
        with foreign.begin() as tx:
            foreign_part = box(tx)
            tx.commit()
        with document.begin() as tx:
            stale = box(tx, (1., 1., 1.))
            tx.bind_root(GeometryLeaf("old", stale))
            tx.commit()
        with document.begin() as tx:
            current = box(tx)
            tx.bind_root(GeometryLeaf("new", current))
            tx.commit()
        document.collect(keep_revisions=0)
        with document.begin() as tx:
            other = box(tx, (7., 7., 7.))
            recorded = dict(tx._handles)
            # Both current and other are retained: a valid prototype cannot
            # borrow another allocation's identity to pass the owner boundary.
            for handle in (foreign_part, stale, replace(current, allocation_id=other.allocation_id)):
                with self.subTest(handle=handle), self.assertRaises(ValueError):
                    tx.bind_root(GeometryLeaf("invalid", handle))
            self.assertEqual(tx._handles, recorded)

    def test_pin_and_active_bound_root_retain_prior_geometry_until_replaced(self):
        document = Document("root-lifetime")
        with document.begin() as tx:
            old = box(tx, (1., 2., 3.))
            root = tx.bind_root(GeometryLeaf("old", old))
            first = tx.commit()
        pin = document.pin(first.revision_id)
        active = document.begin()
        active.bind_root(replace(root, label="still reachable"))
        with document.begin() as tx:
            new = box(tx)
            tx.bind_root(GeometryLeaf("new", new))
            tx.commit()
        document.collect(keep_revisions=0)
        self.assertIs(pin.revision.root, root)
        pin.release()
        document.collect(keep_revisions=0)
        self.assertAlmostEqual(active.query(old, volume), 6.)
        active.abort()
        document.collect(keep_revisions=0)
        with self.assertRaises(ValueError):
            document._get(old)
        with self.assertRaises(KeyError):
            document.pin(first.revision_id)
        self.assertEqual(root_handles(document.head.root), (new,))

    def test_graph_only_revision_has_no_returned_scene(self):
        document = Document("unbound")
        with document.begin() as tx:
            part = box(tx)
            revision = tx.commit()
        self.assertIsNone(revision.root)
        self.assertEqual(revision.evaluations, (part,))

    def test_transform_and_appearance_inputs_are_finite_affine_immutable_values(self):
        for transform in ((), IDENTITY_TRANSFORM[:-1], translated(float("nan")),
                          translated(float("inf")), IDENTITY_TRANSFORM[:-1] + (2.,)):
            with self.subTest(transform=transform), self.assertRaises(ValueError):
                GeometryLeaf("part", None, transform)
        matrix = translated(2)
        group = AssemblyGroup("group", [], matrix)
        matrix[3] = 12.
        self.assertEqual(group.transform[3], 2.)
        self.assertEqual(group.children, ())
        with self.assertRaises(ValueError):
            GeometryLeaf("part", None, appearance={"roughness": float("nan")})
        with self.assertRaises(TypeError):
            GeometryLeaf("part", None, label=object())
        self.assertEqual(GeometryLeaf(LogicalIdentity("key"), None).node_id, LogicalIdentity("key"))


if __name__ == "__main__":
    unittest.main()
