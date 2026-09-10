"""Saved readback may reuse only a verified canonical tree of the exact bytes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


class SavedStepReadbackTest(unittest.TestCase):
    def setUp(self):
        scratch = generated_cad_directory(prefix="saved-step-readback-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        environment = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        environment.start()
        self.addCleanup(environment.stop)
        workers = mock.patch("cadgen._internal.component_package._component_build_worker_count", return_value=1)
        workers.start()
        self.addCleanup(workers.stop)

    def shape(self, size=2):
        from build123d import Solid

        shape = Solid.make_box(size, 3, 4)
        shape.label = "part"
        shape.color = (.8, .7, .6, 1)
        shape.cad_face_ordinal_colors = {1: (1., 0., 0., 1.), 3: (0., 0., 1., 1.)}
        return shape

    def build(self, shape=None, *, force=False):
        from cadgen.store.build import build_tree_through_step

        return build_tree_through_step(
            self.shape() if shape is None else shape, self.root / "part.step",
            root_name="root", force=force,
        )

    def seed(self, shape=None):
        from cadgen.store.records import note_document_tree

        result = self.build(shape)
        note_document_tree(result[3], result[2]["documentTree"])
        return result

    def assert_same_document(self, expected, actual):
        self.assertEqual(expected[3], actual[3])
        for key in ("documentTree", "documentOccurrenceMap", "documentNodeMap", "documentAppearance"):
            self.assertEqual(expected[2][key], actual[2][key], key)

    def test_exact_digest_hit_matches_forced_raw_readback_and_has_private_geometry(self):
        from OCP.BRep import BRep_Builder
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.step_scene_package import scene_from_render_package

        expected = self.seed()
        cached = scene_from_render_package(self.root / "part.step", step_hash=expected[3])
        vertex = TopoDS.Vertex_s(TopExp_Explorer(next(iter(cached.prototype_shapes.values())), TopAbs_VERTEX).Current())
        BRep_Builder().UpdateVertex(vertex, gp_Pnt(50, 60, 70), 1e-7)
        with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", side_effect=AssertionError("cache hit parsed STEP")):
            warm = self.build()
        self.assert_same_document(expected, warm)
        self.assertEqual(expected[:2], warm[:2])
        with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", wraps=load_step_scene) as raw:
            forced = self.build(force=True)
        raw.assert_called_once()
        self.assert_same_document(expected, forced)

    def test_new_geometry_digest_is_a_raw_miss_even_with_an_existing_path_record(self):
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.store.records import note_output, write_record

        old = self.seed()
        source = self.root / "removed-source.py"
        write_record(source, {"tree": old[0], "outputs": {str(self.root / "part.step"): {"sha256": old[3]}}})
        note_output(self.root / "part.step", source)
        with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", wraps=load_step_scene) as raw:
            changed = self.build(self.shape(5))
        raw.assert_called_once()
        self.assertNotEqual(old[3], changed[3])
        self.assertNotEqual(old[2]["documentTree"], changed[2]["documentTree"])

    def test_current_pbr_is_rebound_without_reading_source_records_or_staged_sidecars(self):
        shape = self.shape()
        shape.cad_material = {"roughness": .2, "metalness": .6}
        expected = self.seed(shape)
        (self.root / "part.step.json").write_text("not a sidecar", encoding="utf-8")
        shape.cad_material = {"roughness": .8, "metalness": .1}
        with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", side_effect=AssertionError("cache hit parsed STEP")), \
                mock.patch("cadgen.store.records.read_record", side_effect=AssertionError("read source record")):
            changed = self.build(shape)
        self.assertEqual(expected[3], changed[3])
        self.assertEqual(expected[2]["documentTree"], changed[2]["documentTree"])
        self.assertNotEqual(expected[2]["documentAppearance"], changed[2]["documentAppearance"])
        self.assertTrue(all(value == shape.cad_material for value in changed[2]["documentAppearance"].values()))

    def test_nested_located_root_and_repeated_prototypes_keep_names_placements_and_colors(self):
        from build123d import Compound, Location

        first = self.shape().moved(Location((2, 0, 0)))
        first.label, first.color = "first", (1, 0, 0, 1)
        second = self.shape().moved(Location((8, 0, 0)))
        second.label, second.color = "second", (0, 1, 0, 1)
        second.cad_material = {"roughness": .7}
        group = Compound(children=[first, second], label="pair").moved(Location((20, 5, 0), (0, 0, 30)))
        shape = Compound(children=[group], label="root").moved(Location((3, 4, 5), (10, 0, 0)))
        expected = self.seed(shape)
        with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", side_effect=AssertionError("cache hit parsed STEP")):
            warm = self.build(shape)
        self.assert_same_document(expected, warm)
        self.assert_same_document(expected, self.build(shape, force=True))

    def test_indexed_missing_or_digest_mismatched_objects_reparse_and_repair(self):
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen.store.objects import object_hash, object_path
        from cadgen.store.trees import get_tree, tree_objects

        expected = self.seed()
        tree_hash = expected[2]["documentTree"]
        tree = get_tree(tree_hash)
        component = next(iter(tree["components"].values()))
        original = {digest: object_path(digest).read_bytes() for digest in tree_objects(tree_hash)}
        for kind, digest in (("tree", tree_hash), ("brep", component["brep"]), ("surf", component["surf"])):
            for damage in ("missing", "mismatched"):
                with self.subTest(kind=kind, damage=damage):
                    path = object_path(digest)
                    if damage == "missing":
                        path.unlink()
                    else:
                        path.write_bytes(b"damaged object")
                    self.assertIsNone(scene_from_render_package(self.root / "part.step", step_hash=expected[3]))
                    with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", wraps=load_step_scene) as raw:
                        repaired = self.build()
                    raw.assert_called_once()
                    self.assert_same_document(expected, repaired)
                    for object_digest, payload in original.items():
                        self.assertEqual(object_path(object_digest).read_bytes(), payload)
                        self.assertEqual(object_hash(payload), object_digest)

    def test_unreadable_surf_with_valid_hash_is_a_miss_not_missing_face_colors(self):
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen.store.objects import put_object
        from cadgen.store.records import note_document_tree
        from cadgen.store.trees import get_tree, put_tree

        expected = self.seed()
        bad_tree = get_tree(expected[2]["documentTree"])
        next(iter(bad_tree["components"].values()))["surf"] = put_object(b"not a SURF container")
        note_document_tree(expected[3], put_tree(bad_tree))
        self.assertIsNone(scene_from_render_package(self.root / "part.step", step_hash=expected[3]))
        self.assert_same_document(expected, self.build())

    def test_absent_document_index_does_not_reuse_damaged_component_objects(self):
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.store.index import remove_entry
        from cadgen.store.objects import object_path
        from cadgen.store.trees import get_tree

        expected = self.seed()
        component = next(iter(get_tree(expected[2]["documentTree"])["components"].values()))
        for force in (False, True):
            with self.subTest(force=force):
                remove_entry("document", expected[3])
                path = object_path(component["surf"])
                original = path.read_bytes()
                path.write_bytes(b"corrupt component, no document index")
                with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", wraps=load_step_scene) as raw:
                    repaired = self.build(force=force)
                raw.assert_called_once()
                self.assert_same_document(expected, repaired)
                self.assertEqual(path.read_bytes(), original)

    def test_cache_snapshot_can_repair_an_object_deleted_after_lookup(self):
        from cadgen._internal import step_scene_package
        from cadgen.store.objects import object_path
        from cadgen.store.trees import get_tree

        expected = self.seed()
        brep = next(iter(get_tree(expected[2]["documentTree"])["components"].values()))["brep"]
        original = step_scene_package.lookup_document_scene

        def delete_after_lookup(*args, **kwargs):
            result = original(*args, **kwargs)
            self.assertIsNotNone(result[0])
            object_path(brep).unlink()
            return result

        with mock.patch.object(step_scene_package, "lookup_document_scene", side_effect=delete_after_lookup), \
                mock.patch("cadgen._internal.step_scene_loader.load_step_scene", side_effect=AssertionError("verified snapshot was lost")):
            repaired = self.build()
        self.assert_same_document(expected, repaired)
        self.assertTrue(object_path(brep).is_file())

    def test_linked_tree_is_rejected_before_flattening(self):
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen.store.records import note_document_tree
        from cadgen.store.trees import get_tree, put_tree

        expected = self.seed()
        bad_tree = get_tree(expected[2]["documentTree"])
        bad_tree["links"] = [{"id": "o1.1", "tree": expected[0]}]
        note_document_tree(expected[3], put_tree(bad_tree))
        with mock.patch("cadgen.store.trees.flatten_tree", side_effect=AssertionError("linked document flattened")):
            self.assertIsNone(scene_from_render_package(self.root / "part.step", step_hash=expected[3]))

    def test_deleted_asset_between_tree_and_component_reads_reparses(self):
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.store import objects
        from cadgen.store.trees import get_tree

        expected = self.seed()
        tree_hash = expected[2]["documentTree"]
        brep = next(iter(get_tree(tree_hash)["components"].values()))["brep"]
        original = objects.read_verified_object

        def delete_after_tree(digest):
            data = original(digest)
            if digest == tree_hash:
                objects.object_path(brep).unlink(missing_ok=True)
            return data

        with mock.patch.object(objects, "read_verified_object", side_effect=delete_after_tree), \
                mock.patch("cadgen._internal.step_scene_loader.load_step_scene", wraps=load_step_scene) as raw:
            repaired = self.build()
        raw.assert_called_once()
        self.assert_same_document(expected, repaired)

    def test_cached_placement_and_face_color_correspondence_checks_still_run(self):
        from build123d import Compound
        from cadgen._internal import step_scene_package

        shape = Compound(children=[self.shape()], label="root")
        self.seed(shape)
        original = step_scene_package.lookup_document_scene

        def changed_placement(*args, **kwargs):
            scene, repair = original(*args, **kwargs)
            leaf = scene.roots[0]
            while leaf.children:
                leaf = leaf.children[0]
            transform = list(leaf.transform)
            transform[3] += 1
            leaf.transform = tuple(transform)
            return scene, repair

        with mock.patch.object(step_scene_package, "lookup_document_scene", side_effect=changed_placement):
            with self.assertRaisesRegex(RuntimeError, "placement"):
                self.build(shape)

        def missing_colors(*args, **kwargs):
            scene, repair = original(*args, **kwargs)
            scene.prototype_face_colors.clear()
            return scene, repair

        with mock.patch.object(step_scene_package, "lookup_document_scene", side_effect=missing_colors):
            with self.assertRaisesRegex(RuntimeError, "per-face colours"):
                self.build(shape)

    def test_saved_reader_repairs_corrupt_objects_without_code_index_reads(self):
        import cadgen

        expected = self.seed()
        guard_root = self.root / "reader-guard"
        guard_root.mkdir()
        # The real transient compile process inherits this guard. Historical
        # compile bookkeeping may be written, but no reader can consult it.
        (guard_root / "sitecustomize.py").write_text(textwrap.dedent("""\
            import os
            import sys
            root = os.path.abspath(os.environ["CADGEN_CACHE_DIR"])
            forbidden = tuple(os.path.join(root, "index", kind) for kind in ("model", "output"))
            def guard(event, args):
                if event not in {"open", "os.listdir", "os.scandir"} or not args:
                    return
                if not isinstance(args[0], (str, bytes)):
                    return
                path = os.path.abspath(os.fsdecode(args[0]))
                write_only = (event == "open" and len(args) > 2 and isinstance(args[2], int)
                              and args[2] & os.O_ACCMODE == os.O_WRONLY)
                if not write_only and any(path == prefix or path.startswith(prefix + os.sep) for prefix in forbidden):
                    raise AssertionError("saved reader read code index: " + path)
            sys.addaudithook(guard)
            sys._cadgen_saved_reader_guard = True
            """), encoding="utf-8")
        script = textwrap.dedent("""\
            import hashlib
            import json
            import sys
            from pathlib import Path
            from unittest import mock
            from cadgen._internal.step_scene_package import load_step_scene_cached
            from cadgen.daemon import executors
            from cadgen.step import compile
            from cadgen.store.index import write_entry
            from cadgen.store.objects import object_path, put_object, read_verified_object
            from cadgen.store.records import note_document_tree, tree_for_document_hash
            from cadgen.store.trees import get_tree, put_tree, tree_objects

            assert sys._cadgen_saved_reader_guard
            step = Path(sys.argv[1])
            step_hash, tree_hash = sys.argv[2:4]
            saved_bytes = step.read_bytes()
            original = {digest: read_verified_object(digest) for digest in tree_objects(tree_hash)}
            component = next(iter(get_tree(tree_hash)["components"].values()))
            cases = []
            for kind, digest in (("tree", tree_hash), ("brep", component["brep"]), ("surf", component["surf"])):
                object_path(digest).write_bytes(b"damaged derived object")
                with mock.patch.object(executors, "submit_compile", wraps=executors.submit_compile) as submitted:
                    scene = load_step_scene_cached(step)
                assert submitted.call_count == 1, (kind, submitted.call_count)
                assert scene.step_hash == step_hash
                assert tree_for_document_hash(step_hash) == tree_hash
                assert all(read_verified_object(key) == data for key, data in original.items())
                assert step.read_bytes() == saved_bytes
                cases.append(kind)
            # Byte integrity alone cannot validate a SURF container. Keep the
            # malformed object's valid address in both indexes to prove the
            # reader carries its failed-closure verdict into compilation.
            bad_tree = get_tree(tree_hash)
            cid = next(iter(bad_tree["components"]))
            bad_component = bad_tree["components"][cid]
            bad_component["surf"] = put_object(b"hash-valid but unreadable SURF")
            write_entry("component", cid, {"surf": bad_component["surf"], "brep": bad_component["brep"]})
            note_document_tree(step_hash, put_tree(bad_tree))
            with mock.patch.object(executors, "submit_compile", wraps=executors.submit_compile) as submitted:
                assert load_step_scene_cached(step).step_hash == step_hash
            assert submitted.call_count == 1
            assert submitted.call_args.kwargs["force"] is True
            assert tree_for_document_hash(step_hash) == tree_hash
            assert all(read_verified_object(key) == data for key, data in original.items())
            cases.append("unreadable-surf")
            # Force also bypasses a present document index and repairs existing
            # corrupt component bytes instead of an idempotent write keeping them.
            object_path(component["surf"]).write_bytes(b"force must repair this")
            result = compile(step, force=True)
            assert result.ok and not result.skipped
            assert result.tree == tree_hash
            assert all(read_verified_object(key) == data for key, data in original.items())
            # A healthy saved read retains its no-compile path after repair.
            with mock.patch.object(executors, "submit_compile", side_effect=AssertionError("healthy read compiled")):
                assert load_step_scene_cached(step).step_hash == step_hash
            assert hashlib.sha256(step.read_bytes()).hexdigest() == step_hash
            print(json.dumps({"repaired": cases, "forced": True, "codeIndexReadsForbidden": True}))
            """)
        environment = {key: value for key, value in os.environ.items() if not key.startswith("CADGEN_")}
        environment.update({
            "CADGEN_CACHE_DIR": str(self.root / "store"), "CADGEN_DAEMON": "0",
            "CADGEN_JOBS": "1", "CADGEN_COMPONENT_WORKERS": "1",
            "PYTHONPATH": os.pathsep.join([str(guard_root), str(Path(cadgen.__file__).resolve().parent.parent)]),
        })
        completed = subprocess.run(
            [sys.executable, "-c", script, str(self.root / "part.step"), expected[3], expected[2]["documentTree"]],
            cwd=self.root, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=90,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout.strip().splitlines()[-1]), {
            "repaired": ["tree", "brep", "surf", "unreadable-surf"],
            "forced": True, "codeIndexReadsForbidden": True,
        })


class ObjectRepairTest(unittest.TestCase):
    def setUp(self):
        scratch = generated_cad_directory(prefix="object-repair-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        environment = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        environment.start()
        self.addCleanup(environment.stop)

    def test_opt_in_repair_keeps_valid_objects_untouched_and_repairs_known_bytes(self):
        from cadgen.store import objects

        payload = b"known exact object bytes"
        digest = objects.put_object(payload)
        path = objects.object_path(digest)
        source = self.root / "source.bin"
        source.write_bytes(payload)
        original_stat = path.stat()
        with mock.patch.object(objects, "replace_atomic", side_effect=AssertionError("rewrote valid object")):
            self.assertEqual(objects.put_object(payload, repair=True), digest)
            self.assertEqual(objects.put_object_from_file(source, repair=True), digest)
        self.assertEqual(path.stat().st_mtime_ns, original_stat.st_mtime_ns)
        for writer in (lambda: objects.put_object(payload, repair=True),
                       lambda: objects.put_object_from_file(source, repair=True)):
            path.write_bytes(b"corrupt bytes")
            # Normal idempotent writes remain unchanged; recovery is explicit.
            self.assertEqual(objects.put_object(payload), digest)
            self.assertEqual(path.read_bytes(), b"corrupt bytes")
            self.assertEqual(writer(), digest)
            self.assertEqual(path.read_bytes(), payload)

    def test_two_repair_writers_never_remove_each_others_valid_object(self):
        from concurrent.futures import ThreadPoolExecutor
        from cadgen.store import objects

        payload = b"same expected bytes in both repairing writers"
        digest = objects.put_object(payload)
        path = objects.object_path(digest)
        path.write_bytes(b"corrupt bytes")
        barrier = threading.Barrier(2)
        original = objects._object_matches

        def both_observe_damage(target, expected):
            matches = original(target, expected)
            if target == path:
                barrier.wait(timeout=5)
            return matches

        with mock.patch.object(objects, "_object_matches", side_effect=both_observe_damage), \
                mock.patch.object(Path, "unlink", side_effect=AssertionError("repair unlinked an object")), \
                ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(objects.put_object, payload, repair=True) for _ in range(2)]
            self.assertEqual([future.result(timeout=5) for future in futures], [digest, digest])
        self.assertEqual(path.read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
