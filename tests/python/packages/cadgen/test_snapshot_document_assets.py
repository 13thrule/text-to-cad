"""Real loopback routes for the native snapshot's immutable byte capability."""
import os
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from cadgen.snapshot_core import SnapshotAssetServer
from cadgen.snapshot_document import prepare_display_snapshot
from tests.python.packages.cadgen.test_snapshot_document import fixture, job, StagingTests


class NativeAssetTests(StagingTests, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.prepared = prepare_display_snapshot(fixture(), job())
        self.addCleanup(self.prepared.close)
        self.descriptor = self.prepared.operation["packet"]["jobs"][0]["resolved"]["document"]
        with patch("cadgen.snapshot_core._store_packages_root", side_effect=AssertionError("old store route")):
            self.server = SnapshotAssetServer(self.prepared.root, document=self.descriptor)
        self.addCleanup(self.server.close)

    def request(self, route, *, method="GET", data=None):
        req = urllib.request.Request(self.server.base_url + route, method=method, data=data)
        try:
            with urllib.request.urlopen(req, timeout=2) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def test_native_only_routes_reject_old_assets_store_and_cache(self):
        for route in ("/__render_asset/secret", "/__store_asset/tree", "/__tess_cache/probe", "/__document_asset/../secret"):
            self.assertEqual(404, self.request(route)[0])
        self.assertEqual(405, self.request("/__tess_cache/probe", method="POST", data=b"{}")[0])
        identity = self.descriptor["manifest"]["sha256"]
        self.descriptor["manifest"]["sha256"] = "f" * 64
        self.descriptor["assets"].clear()
        status, body = self.request("/__document_asset/" + identity)
        self.assertEqual(200, status)
        self.assertEqual(fixture().manifest, body)
        self.assertEqual(404, self.request("/__document_asset/" + identity + "?other=1")[0])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO")
    def test_changed_hash_file_and_fifo_substitution_fail_without_stranding_worker(self):
        identity = next(iter(self.descriptor["assets"]))
        path = self.prepared.root / identity
        path.write_bytes(b"x" * self.descriptor["assets"][identity]["bytes"])
        self.assertEqual(404, self.request("/__document_asset/" + identity)[0])
        path.unlink(); os.mkfifo(path)
        self.assertEqual(404, self.request("/__document_asset/" + identity)[0])
        self.server.close()
        self.assertFalse(self.server._thread.is_alive())
        self.assertFalse(self.server._connections)


if __name__ == "__main__": unittest.main()
