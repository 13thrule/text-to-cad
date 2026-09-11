"""Artifact and component indexes retain their closures under manual GC."""

from __future__ import annotations

import os
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")


class ComponentGcReachability(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = generated_cad_directory(prefix="store-gc-component-")
        self.addCleanup(self._tmp.cleanup)
        self.store = Path(self._tmp.name) / "store"
        self._environment = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store)})
        self._environment.start()
        self.addCleanup(self._environment.stop)

    def test_component_index_retains_surf_and_brep_while_a_true_orphan_is_swept(self) -> None:
        from cadgen.store.gc import collect
        from cadgen.store.index import write_entry
        from cadgen.store.objects import has_object, object_path, put_object

        surf = put_object(b"standalone component surf")
        brep = put_object(b"standalone component brep")
        orphan = put_object(b"unreferenced object")
        write_entry("component", "component-id", {"surf": surf, "brep": brep})
        old = time.time() - 7200
        for digest in (surf, brep, orphan):
            os.utime(object_path(digest), (old, old))

        report = collect(grace_seconds=0)

        self.assertEqual(report.reachable, 2)
        self.assertEqual(report.removed, 1)
        self.assertTrue(has_object(surf))
        self.assertTrue(has_object(brep))
        self.assertFalse(has_object(orphan))

    def test_document_only_root_retains_linked_geometry_but_not_external_mesh_hash(self) -> None:
        from cadgen.store.gc import collect
        from cadgen.store.index import remove_entry
        from cadgen.store.objects import has_object, object_path, put_object
        from cadgen.store.records import note_document_mesh, note_document_tree
        from cadgen.store.trees import put_tree, tree_complete

        surf = put_object(b"document component surf")
        brep = put_object(b"document component brep")
        child = put_tree({"components": {"child": {"surf": surf, "brep": brep}}, "links": []})
        parent = put_tree({"components": {}, "links": [{"tree": child}]})
        # An unrelated object can happen to have the same bytes as an exported
        # mesh. The external-output ledger must not keep that object alive.
        external_mesh = put_object(b"external exported mesh")
        document_hash = "d" * 64
        note_document_tree(document_hash, parent)
        note_document_mesh(document_hash, "stl:test-variant", external_mesh)
        old = time.time() - 7200
        for digest in (surf, brep, child, parent, external_mesh):
            os.utime(object_path(digest), (old, old))

        report = collect(grace_seconds=0)

        self.assertEqual(report.records, 0)
        self.assertEqual(report.reachable, 4)
        self.assertEqual(report.removed, 1)
        self.assertTrue(tree_complete(parent))
        self.assertFalse(has_object(external_mesh))

        remove_entry("document", document_hash)
        forgotten = collect(grace_seconds=0)
        self.assertEqual(forgotten.removed, 4)
        self.assertFalse(has_object(parent))

    def test_obsolete_document_index_does_not_retain_unusable_tree(self) -> None:
        from cadgen.store.gc import collect
        from cadgen.store.index import write_entry
        from cadgen.store.objects import has_object, object_path
        from cadgen.store.records import DOCUMENT_SCHEMA_VERSION
        from cadgen.store.trees import put_tree

        tree = put_tree({"components": {}, "links": []})
        write_entry("document", "a" * 64, {
            "schemaVersion": DOCUMENT_SCHEMA_VERSION - 1,
            "tree": tree,
        })
        old = time.time() - 7200
        os.utime(object_path(tree), (old, old))

        report = collect(grace_seconds=0)

        self.assertEqual(report.reachable, 0)
        self.assertEqual(report.removed, 1)
        self.assertFalse(has_object(tree))


if __name__ == "__main__":
    unittest.main()
