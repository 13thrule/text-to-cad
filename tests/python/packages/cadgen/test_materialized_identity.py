"""A materialized tree is reusable only while its exposed geometry is intact."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


class MaterializedIdentityTest(unittest.TestCase):
    def setUp(self):
        from cadgen.store.materialize import reset_memo

        self.scratch = generated_cad_directory(prefix="materialized-identity-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        patcher = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        patcher.start()
        self.addCleanup(patcher.stop)
        reset_memo()
        self.addCleanup(reset_memo)

    def child(self, *, assembly=True, curved=False):
        from build123d import Compound, Location, Solid
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.materialize import materialize

        first = Solid.make_sphere(3) if curved else Solid.make_box(2, 3, 4)
        first.label, first.color = "first", (1, 0, 0, 1)
        if assembly:
            second = Solid.make_torus(8, 2) if curved else Solid.make_box(1, 1, 1)
            second = second.moved(Location((7, 0, 0), (12, 17, 41) if curved else (0, 0, 0)))
            second.label = "second"
            shape = Compound(children=[first, second], label="child")
        else:
            shape = first
        tree, _, _ = build_tree_from_compound(shape, root_name="child")
        return tree, materialize(tree)

    def parent(self, child, *, step=False, expected_export_volume=None):
        from build123d import Compound
        from cadgen.store.build import build_tree_from_compound, build_tree_through_step
        from cadgen.store.materialize import materialize

        shape = Compound(children=[child], label="parent")
        if step:
            from cadgen.step_export import export_build123d_step_file

            def export(document, *args, **kwargs):
                if expected_export_volume is not None:
                    self.assertAlmostEqual(self.signed_volume(document), expected_export_volume, places=9)
                return export_build123d_step_file(document, *args, **kwargs)

            with mock.patch("cadgen.step_export.export_build123d_step_file", side_effect=export):
                tree, descriptor, _, _ = build_tree_through_step(shape, self.root / "parent.step", root_name="parent")
        else:
            tree, descriptor, _ = build_tree_from_compound(shape, root_name="parent")
        return descriptor, materialize(tree)

    def signed_volume(self, shape):
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps

        properties = GProp_GProps()
        BRepGProp.VolumeProperties_s(getattr(shape, "wrapped", shape), properties)
        return properties.Mass()

    def saved_step_volume(self):
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.step_scene_mesh import scene_leaf_occurrences, scene_occurrence_shape

        scene = load_step_scene(self.root / "parent.step", record_read=False)
        return sum(self.signed_volume(scene_occurrence_shape(scene, node)) for node in scene_leaf_occurrences(scene))

    def test_root_placement_label_color_overrides_keep_the_link(self):
        from build123d import Location
        from cadgen.store.build import _tagged_intact
        from cadgen.store.materialize import PARTNER_TAG

        tree, child = self.child(curved=True)
        moved = child.moved(Location((10, 20, 30), (10, 20, 30)))
        moved.label, moved.color = "placed", (0, 0, 1, 1)
        self.assertEqual(_tagged_intact(child), tree)
        self.assertEqual(_tagged_intact(moved), tree)
        self.assertIsNot(getattr(child, PARTNER_TAG), getattr(moved, PARTNER_TAG))
        descriptor, again = self.parent(moved)
        self.assertEqual(len(descriptor["links"]), 1)
        self.assertEqual(descriptor["links"][0]["name"], "placed")
        self.assertEqual(descriptor["links"][0]["color"], [0, 0, 1, 1])
        self.assertAlmostEqual(again.volume, child.volume, places=9)

    def test_descendant_metadata_edit_survives_copy_and_packaging(self):
        from build123d import Location
        from cadgen.store.build import _tagged_intact

        tree, child = self.child()
        child.children[0].label = "edited"
        child.children[0].color = (0, 0, 1, 1)
        moved = child.moved(Location((10, 0, 0)))
        self.assertIsNone(_tagged_intact(child))
        self.assertIsNone(_tagged_intact(moved), "copy blessed a dirty source")
        descriptor, again = self.parent(moved, step=True)
        self.assertEqual(descriptor["links"], [])
        first = again.children[0].children[0]
        self.assertEqual(first.label, "edited")
        self.assertEqual(tuple(first.color), (0, 0, 1, 1))
        self.assertAlmostEqual(again.volume, child.volume, places=9)

    def test_copied_holder_never_refreshes_the_original_baseline(self):
        from build123d import Location
        from cadgen.store.build import _tagged_intact
        from cadgen.store.materialize import PARTNER_TAG

        tree, child = self.child()
        original_holder = getattr(child, PARTNER_TAG)
        baseline = original_holder.baseline
        moved = child.moved(Location((10, 0, 0)))
        moved.children[0].label = "edited-copy"
        moved_again = moved.moved(Location((20, 0, 0)))
        self.assertEqual(_tagged_intact(child), tree)
        self.assertIsNone(_tagged_intact(moved_again))
        self.assertIs(original_holder.baseline, baseline)
        self.assertEqual(child.children[0].label, "first")

    def test_descendant_placement_edit_is_preserved(self):
        from build123d import Location
        from cadgen.store.build import _tagged_intact

        _, child = self.child()
        child.children[0].move(Location((30, 0, 0)))
        self.assertIsNone(_tagged_intact(child))
        descriptor, again = self.parent(child)
        self.assertEqual(descriptor["links"], [])
        first = again.children[0].children[0]
        self.assertAlmostEqual(first.center().X, 31.0, places=7)

    def test_native_geometry_edit_to_a_component_is_not_substituted(self):
        from OCP.BRep import BRep_Builder
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.TopoDS import TopoDS_Compound
        from build123d import Compound, Location, Solid
        from cadgen.store.build import _tagged_intact, build_tree_from_compound
        from cadgen.store.materialize import materialize

        builder, native = BRep_Builder(), TopoDS_Compound()
        builder.MakeCompound(native)
        builder.Add(native, BRepPrimAPI_MakeBox(2, 3, 4).Shape())
        tree, _, _ = build_tree_from_compound(Compound(native), root_name="child")
        child = materialize(tree)
        partner = child.wrapped.TShape()
        builder.Add(child.wrapped, Solid.make_box(1, 1, 1).moved(Location((5, 0, 0))).wrapped)
        self.assertIs(child.wrapped.TShape(), partner)
        self.assertTrue(child.is_valid)
        self.assertIsNone(_tagged_intact(child))
        descriptor, again = self.parent(child.moved(Location((10, 0, 0))), step=True)
        self.assertEqual(descriptor["links"], [])
        self.assertAlmostEqual(again.volume, 25.0, places=9)

    def test_native_add_preserves_existing_descendant_metadata(self):
        from OCP.BRep import BRep_Builder
        from build123d import Location, Solid

        _, child = self.child()
        children_before = tuple(child.children)
        child.children[0].label = "edited"
        child.children[0].color = (0, 0, 1, 1)
        BRep_Builder().Add(child.wrapped, Solid.make_box(2, 1, 1).moved(Location((15, 0, 0))).wrapped)
        descriptor, again = self.parent(child.moved(Location((10, 0, 0))), step=True)
        self.assertEqual(descriptor["links"], [])
        self.assertAlmostEqual(again.volume, 27.0, places=9)
        descendants = again.children[0].children
        self.assertEqual(len(descendants), 3)
        self.assertEqual([node.label for node in descendants[:2]], ["edited", "second"])
        self.assertEqual(tuple(descendants[0].color), (0, 0, 1, 1))
        self.assertEqual(tuple(child.children), children_before)
        self.assertTrue(all(node.parent is child for node in children_before))

    def test_native_remove_does_not_reintroduce_a_stale_wrapper(self):
        from OCP.BRep import BRep_Builder
        from cadgen.store.materialize import _native_children

        _, child = self.child()
        BRep_Builder().Remove(child.wrapped, _native_children(child.wrapped)[0])
        descriptor, again = self.parent(child, step=True)
        self.assertEqual(descriptor["links"], [])
        self.assertAlmostEqual(again.volume, 1.0, places=9)
        self.assertEqual(again.children[0].children[0].label, "second")
        self.assertEqual(len(child.children), 2, "packaging mutated the author's wrappers")

    def test_native_container_reversal_preserves_signed_geometry_and_metadata(self):
        from cadgen.store.build import _tagged_intact

        for step in (False, True):
            with self.subTest(step=step):
                _, child = self.child()
                children_before = tuple(child.children)
                orientations_before = tuple(node.wrapped.Orientation() for node in children_before)
                child.wrapped.Reverse()
                self.assertIsNone(_tagged_intact(child))
                self.assertAlmostEqual(self.signed_volume(child), -25.0, places=9)
                descriptor, again = self.parent(child, step=step, expected_export_volume=-25.0)
                self.assertEqual(descriptor["links"], [])
                # STEP can normalize solid orientation. Its canonical tree must
                # match that read-back; the preview/export must retain our edit.
                self.assertAlmostEqual(self.signed_volume(again), self.saved_step_volume() if step else -25.0, places=9)
                descendants = again.children[0].children
                self.assertEqual([node.label for node in descendants], ["first", "second"])
                self.assertEqual(tuple(descendants[0].color), (1, 0, 0, 1))
                self.assertEqual(tuple(child.children), children_before)
                self.assertEqual(tuple(node.wrapped.Orientation() for node in children_before), orientations_before)
                self.assertTrue(all(node.parent is child for node in children_before))

    def test_native_child_reversal_preserves_its_metadata_and_native_order(self):
        from OCP.BRep import BRep_Builder
        from cadgen.store.materialize import _native_children

        for step in (False, True):
            with self.subTest(step=step):
                _, child = self.child()
                native_first = _native_children(child.wrapped)[0]
                first_before = child.children[0]
                first_orientation = first_before.wrapped.Orientation()
                builder = BRep_Builder()
                builder.Remove(child.wrapped, native_first)
                builder.Add(child.wrapped, native_first.Reversed())
                self.assertAlmostEqual(self.signed_volume(child), -23.0, places=9)
                descriptor, again = self.parent(child, step=step, expected_export_volume=-23.0)
                self.assertEqual(descriptor["links"], [])
                self.assertAlmostEqual(self.signed_volume(again), self.saved_step_volume() if step else -23.0, places=9)
                descendants = again.children[0].children
                self.assertEqual([node.label for node in descendants], ["second", "first"])
                self.assertEqual(tuple(descendants[1].color), (1, 0, 0, 1))
                self.assertIs(child.children[0], first_before)
                self.assertEqual(first_before.wrapped.Orientation(), first_orientation)

    def test_opposite_orientation_occurrences_do_not_share_a_component_identity(self):
        from build123d import Compound, Solid
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.materialize import materialize

        first = Solid.make_box(2, 3, 4)
        reversed_first = Solid(first.wrapped.Reversed())
        first.label, reversed_first.label = "forward", "reversed"
        self.assertTrue(first.wrapped.IsPartner(reversed_first.wrapped))
        shape = Compound(children=[first, reversed_first])
        tree, descriptor, _ = build_tree_from_compound(shape, root_name="opposite")
        self.assertEqual(len(descriptor["components"]), 2)
        again = materialize(tree)
        self.assertAlmostEqual(self.signed_volume(again), 0.0, places=9)
        self.assertEqual([node.label for node in again.children], ["forward", "reversed"])
        self.assertAlmostEqual(self.signed_volume(again.children[0]), 24.0, places=9)
        self.assertAlmostEqual(self.signed_volume(again.children[1]), -24.0, places=9)

    def test_added_reversed_alias_cannot_steal_a_surviving_occurrences_metadata(self):
        from OCP.BRep import BRep_Builder
        from cadgen.store.materialize import _native_children

        _, child = self.child()
        first = _native_children(child.wrapped)[0]
        builder = BRep_Builder()
        builder.Remove(child.wrapped, first)
        builder.Add(child.wrapped, first.Reversed())
        builder.Add(child.wrapped, first)
        descriptor, again = self.parent(child)
        self.assertEqual(descriptor["links"], [])
        self.assertAlmostEqual(self.signed_volume(again), 1.0, places=9)
        descendants = again.children[0].children
        self.assertEqual(descendants[0].label, "second")
        self.assertNotEqual(descendants[1].label, "first")
        self.assertEqual(descendants[2].label, "first")
        self.assertEqual(tuple(descendants[2].color), (1, 0, 0, 1))

    def test_mesh_and_measurement_leave_geometry_intact_and_caller_flags_untouched(self):
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from cadgen._internal.op_memo import _write_brep
        from cadgen.store.build import _tagged_intact
        from cadgen.store.materialize import materialize

        tree, child = self.child(curved=True)
        _ = child.bounding_box()
        BRepMesh_IncrementalMesh(child.wrapped, 0.1, False, 0.5, False)
        before = _write_brep(child.wrapped)
        self.assertEqual(_tagged_intact(child), tree)
        self.assertEqual(_write_brep(child.wrapped), before)
        fresh = materialize(tree)
        self.assertFalse(child.wrapped.IsPartner(fresh.wrapped))
        self.assertEqual(_tagged_intact(fresh), tree)

    def test_missing_holder_and_standard_geometry_replacements_do_not_link(self):
        from build123d import Location, Plane
        from cadgen.store.build import _tagged_intact
        from cadgen.store.materialize import PARTNER_TAG

        _, child = self.child(assembly=False)
        self.assertIsNone(_tagged_intact(child.located(Location((10, 0, 0)))))
        self.assertIsNone(_tagged_intact(child.mirror(Plane.XZ)))
        delattr(child, PARTNER_TAG)
        self.assertIsNone(_tagged_intact(child))

    def test_missing_pin_fails_instead_of_using_materialized_geometry(self):
        from build123d import Compound
        from cadgen.store.build import build_tree_through_step
        from cadgen.store.objects import object_path

        tree, child = self.child()
        object_path(tree).unlink()
        with self.assertRaises((FileNotFoundError, RuntimeError)):
            build_tree_through_step(Compound(children=[child]), self.root / "missing.step", root_name="parent")

    def test_repeated_native_keys_are_stable_and_ambiguous_removal_fails(self):
        from OCP.BRep import BRep_Builder
        from build123d import Compound, Solid
        from cadgen.store.build import _walk_compound
        from cadgen.store.materialize import _native_children, _native_key, materialize_descriptor
        from cadgen.coordination import resolve

        prototype = Solid.make_box(2, 3, 4)
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        descriptor = {
            "components": {"same": {}},
            "occurrences": [
                {"id": "a", "component": "same", "name": "first", "transform": identity},
                {"id": "b", "component": "same", "name": "second", "transform": identity},
            ],
        }
        child = materialize_descriptor(descriptor, shapes={"same": prototype}, tree_hash="test-pin")
        before = tuple(_native_key(node) for node in _native_children(child.wrapped))
        after = tuple(_native_key(node) for node in _native_children(child.wrapped))
        self.assertEqual(before, after)
        self.assertEqual([hash(key) for key in before], [hash(key) for key in after])
        self.assertEqual(before[0], before[1])
        BRep_Builder().Remove(child.wrapped, _native_children(child.wrapped)[0])
        with self.assertRaisesRegex(RuntimeError, "ambiguous native edit"):
            _walk_compound(Compound(children=[child]), root_name="parent", progress=resolve(None))

    def test_nested_repeated_fingerprint_serializes_each_unique_leaf_once(self):
        from build123d import Compound, Location, Solid
        from cadgen._internal import component_package
        from cadgen.store.materialize import _capture_materialized_state

        leaf = Solid.make_sphere(3)
        root = Compound(children=[leaf.moved(Location((5 * index, 0, 0))) for index in range(8)])
        for _ in range(6):
            root = Compound(children=[root])
        with mock.patch.object(component_package, "_shape_brep_bytes", wraps=component_package._shape_brep_bytes) as written:
            state = _capture_materialized_state(root)
        self.assertIsNotNone(state.geometry)
        self.assertEqual(written.call_count, 1, "a container or repeated occurrence reserialized the leaf")

    def test_native_descendant_geometry_change_is_seen_through_container_memo(self):
        from OCP.BRep import BRep_Builder
        from OCP.gp import gp_Pnt
        from cadgen.store.build import _tagged_intact

        _, child = self.child()
        vertex = child.children[0].vertices()[0].wrapped
        BRep_Builder().UpdateVertex(vertex, gp_Pnt(0.2, 0, 0), 1e-7)
        self.assertIsNone(_tagged_intact(child))


if __name__ == "__main__":
    unittest.main()
