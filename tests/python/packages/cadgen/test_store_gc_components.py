"""Component-index objects remain reachable under manual store GC."""

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


if __name__ == "__main__":
    unittest.main()
