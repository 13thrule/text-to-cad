"""Canonical STEP packaging is independent of authored trees and filenames."""

from __future__ import annotations

import hashlib
import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


class DocumentTreePackagingTest(unittest.TestCase):
    def setUp(self):
        scratch = generated_cad_directory(prefix="document-tree-packaging-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        env.start()
        self.addCleanup(env.stop)
        workers = mock.patch("cadgen._internal.component_package._component_build_worker_count", return_value=1)
        workers.start()
        self.addCleanup(workers.stop)

    def box(self, name="box"):
        from build123d import Solid

        shape = Solid.make_box(2, 3, 4)
        shape.label = name
        shape.color = (.8, .7, .6, 1)
        return shape

    def assert_warm_and_cold_repackage(self, output, expected_tree):
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen.store.build import build_document_tree
        from cadgen.store.records import note_document_tree

        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        raw_hash, raw_tree, _ = build_document_tree(load_step_scene(output, record_read=False))
        self.assertEqual(raw_hash, expected_tree)
        note_document_tree(digest, expected_tree)
        warm_scene = scene_from_render_package(output, step_hash=digest)
        self.assertIsNotNone(warm_scene)
        warm_hash, warm_tree, _ = build_document_tree(warm_scene)
        self.assertEqual((warm_hash, warm_tree), (raw_hash, raw_tree))
        copied = self.root / "different-filename.step"
        copied.write_bytes(output.read_bytes())
        # Force extraction in an empty store, not merely a hit of the generated
        # component index. The STEP bytes and intrinsic names are the inputs.
        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "empty-store")}):
            cold_hash, cold_tree, _ = build_document_tree(load_step_scene(copied, record_read=False))
        self.assertEqual((cold_hash, cold_tree), (raw_hash, raw_tree))
        return raw_tree

    def test_single_part_root_wrapper_is_canonical_across_warm_cold_and_file_copies(self):
        from cadgen.store.build import build_tree_through_step
        from cadgen.store.trees import get_tree

        shape = self.box("authored-part-name")
        shape.cad_material = {"roughness": .2, "metalness": .7}
        output = self.root / "original.step"
        result, tree, stats, _ = build_tree_through_step(shape, output, root_name="authored-root-name")
        self.assertEqual(tree["occurrences"][0]["name"], "authored-part-name")
        self.assertEqual(tree["occurrences"][0]["material"], shape.cad_material)
        canonical = self.assert_warm_and_cold_repackage(output, stats["documentTree"])
        self.assertNotEqual(result, stats["documentTree"])
        self.assertEqual(set(stats["documentOccurrenceMap"]["o1"]),
                         {occurrence["id"] for occurrence in canonical["occurrences"]})
        self.assertEqual(stats["documentAppearance"],
                         {occurrence["id"]: shape.cad_material for occurrence in canonical["occurrences"]})
        self.assertTrue(all("material" not in occurrence for occurrence in canonical["occurrences"]))
        self.assertNotIn("documentTree", get_tree(result))

    def test_nested_repeated_products_preserve_names_colors_and_world_placements_when_warm(self):
        from build123d import Compound, Location
        from cadgen.store.build import build_tree_through_step

        prototype = self.box()
        first = prototype.moved(Location((2, 0, 0)))
        first.label, first.color = "red", (1, 0, 0, 1)
        second = prototype.moved(Location((8, 0, 0)))
        second.label, second.color = "green", (0, 1, 0, 1)
        group = Compound(children=[first, second], label="pair").moved(Location((20, 5, 0), (0, 0, 30)))
        shape = Compound(children=[group], label="assembly-root")
        output = self.root / "nested.step"
        _, _, stats, _ = build_tree_through_step(shape, output, root_name="assembly-root")
        canonical = self.assert_warm_and_cold_repackage(output, stats["documentTree"])
        self.assertEqual([occurrence["name"] for occurrence in canonical["occurrences"]], ["red", "green"])
        self.assertEqual(stats["documentOccurrenceMap"]["o1"], stats["documentOccurrenceMap"]["o1.1"])
        self.assertEqual(len(stats["documentOccurrenceMap"]["o1.1"]), 2)
        self.assertEqual(stats["documentAppearance"], {})

    def test_a_native_compound_product_keeps_its_product_boundary(self):
        from build123d import Compound, Location
        from cadgen._internal.step_scene_types import LoadedStepScene, OccurrenceNode
        from cadgen.store.build import build_document_tree
        from cadgen.store.trees import IDENTITY_16

        shape = Compound(children=[self.box("one"), self.box("two").moved(Location((8, 0, 0)))])
        scene = LoadedStepScene(
            step_path=self.root / "unrelated-filename.step",
            roots=[OccurrenceNode(path=(1,), name="native-product", source_name="native-product",
                                  transform=tuple(IDENTITY_16), prototype_key=1)],
            prototype_shapes={1: shape.wrapped},
        )
        _, tree, _ = build_document_tree(scene)
        self.assertEqual(tree["label"], "native-product")
        self.assertEqual(len(tree["occurrences"]), 1)
        self.assertEqual(tree["assembly"]["root"]["children"], [])

    def test_one_child_groups_keep_exact_document_nodes_even_with_identical_leaf_sets(self):
        from build123d import Compound
        from cadgen.store.build import build_tree_through_step
        from cadgen.store.trees import get_tree

        inner = Compound(children=[self.box("leaf")], label="inner")
        outer = Compound(children=[inner], label="outer")
        shape = Compound(children=[outer], label="root")
        _, _, stats, _ = build_tree_through_step(shape, self.root / "one-child.step", root_name="root")
        authored_ids = ["o1", "o1.1", "o1.1.1", "o1.1.1.1"]
        leaves = stats["documentOccurrenceMap"]["o1"]
        self.assertEqual(len(leaves), 1)
        self.assertTrue(all(stats["documentOccurrenceMap"][node_id] == leaves for node_id in authored_ids))
        node_map = stats["documentNodeMap"]
        self.assertEqual(set(node_map), set(authored_ids))
        self.assertEqual(len(set(node_map.values())), len(authored_ids))

        written = get_tree(stats["documentTree"])["assembly"]["root"]
        for authored_id, name in zip(authored_ids, ("root", "outer", "inner", "leaf")):
            self.assertEqual((node_map[authored_id], name), (written["id"], written["name"]))
            self.assertEqual(written["leafPartIds"], leaves)
            if written["children"]:
                written = written["children"][0]

    def test_multiple_free_roots_keep_a_stable_synthetic_group_when_repackaged(self):
        from cadgen._internal.step_scene_loader import _location_from_transform_matrix
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen._internal.step_scene_types import LoadedStepScene, OccurrenceNode
        from cadgen.store.build import build_document_tree
        from cadgen.store.records import note_document_tree
        from cadgen.store.trees import IDENTITY_16

        moved = list(IDENTITY_16)
        moved[3] = 8
        scene = LoadedStepScene(
            step_path=self.root / "arbitrary-name.step",
            roots=[OccurrenceNode(path=(index,), name=name, source_name=name,
                                  transform=tuple(transform), prototype_key=1,
                                  location=_location_from_transform_matrix(tuple(transform)))
                   for index, name, transform in ((1, "first", IDENTITY_16), (2, "second", moved))],
            prototype_shapes={1: self.box().wrapped},
        )
        digest, tree, _ = build_document_tree(scene)
        self.assertEqual(tree["label"], "model")
        self.assertEqual([occ["id"] for occ in tree["occurrences"]], ["o1.1", "o1.2"])
        note_document_tree("1" * 64, digest)
        warm = scene_from_render_package(self.root / "renamed.step", step_hash="1" * 64)
        warm_digest, warm_tree, _ = build_document_tree(warm)
        self.assertEqual((warm_digest, warm_tree), (digest, tree))

    def test_unnamed_step_fallback_uses_intrinsic_geometry_location_and_a_fixed_name(self):
        from types import SimpleNamespace

        from build123d import Location
        from cadgen._internal import step_scene_loader as loader

        shape = self.box().moved(Location((8, 2, 0)))
        reader = SimpleNamespace(ReadFile=lambda _: loader.IFSelect_RetDone,
                                 TransferRoots=lambda: None, OneShape=lambda: shape.wrapped)
        with mock.patch.object(loader, "STEPControl_Reader", return_value=reader):
            first = loader._load_fallback_occurrence_tree(self.root / "first.step")
            copied = loader._load_fallback_occurrence_tree(self.root / "copied.step")
        self.assertEqual(first[0][0].name, "model")
        self.assertEqual(first[0][0].name, copied[0][0].name)
        self.assertEqual(first[0][0].transform, copied[0][0].transform)
        self.assertEqual(first[0][0].transform[3], 8)
        self.assertEqual(first[0][0].transform[7], 2)
        self.assertTrue(next(iter(first[1].values())).Location().IsIdentity())

    def test_changed_placement_of_a_linked_repeat_is_rejected(self):
        from build123d import Compound, Location
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.store.build import build_tree_from_compound, build_tree_through_step
        from cadgen.store.materialize import materialize

        child_tree, _, _ = build_tree_from_compound(self.box("child"), root_name="child")
        first = materialize(child_tree)
        second = materialize(child_tree).moved(Location((8, 0, 0)))
        shape = Compound(children=[first, second], label="parent")

        def changed_placement(*args, **kwargs):
            scene = load_step_scene(*args, **kwargs)
            repeated = scene.roots[0].children[1]
            transform = list(repeated.transform)
            transform[3] += 1
            repeated.transform = tuple(transform)
            return scene

        with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", side_effect=changed_placement):
            with self.assertRaisesRegex(RuntimeError, "leaf placement changed"):
                build_tree_through_step(shape, self.root / "changed.step", root_name="parent")

    def test_reordered_written_products_cannot_receive_another_parts_material(self):
        from build123d import Compound, Location
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.store.build import build_tree_through_step

        first, second = self.box("first"), self.box("second").moved(Location((8, 0, 0)))
        first.cad_material, second.cad_material = {"roughness": .1}, {"roughness": .9}
        shape = Compound(children=[first, second], label="parent")

        def reordered(*args, **kwargs):
            scene = load_step_scene(*args, **kwargs)
            scene.roots[0].children.reverse()
            return scene

        with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", side_effect=reordered):
            with self.assertRaisesRegex(RuntimeError, "written product name changed"):
                build_tree_through_step(shape, self.root / "reordered.step", root_name="parent")


if __name__ == "__main__":
    unittest.main()
