"""Metadata reads verify a fresh closure without retaining native payloads."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import Future
import json
import os
from pathlib import Path
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")
from cadgen.store import surfaces, trees
from cadgen.store.build import build_tree_from_compound
from cadgen.store.objects import object_path
from cadgen.viewer.surfaces import SurfaceSubscribers, pinned_surface_object


class PendingSurface(Future):
    def detach(self):
        pass


class MetadataCapture(unittest.TestCase):
    def setUp(self):
        temp = generated_cad_directory(prefix="metadata-capture-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.enterContext(mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "CADGEN_DAEMON": "0", "CADGEN_COMPONENT_WORKERS": "1",
        }))
        from build123d import Solid

        children = [build_tree_from_compound(Solid.make_box(x, 2, 3), root_name=f"box {x}")[0]
                    for x in (1, 2)]
        links = [{"id": f"o{i}", "tree": tree, "name": f"part {i}",
                  "transform": list(trees.IDENTITY_16)} for i, tree in enumerate(children, 1)]
        self.tree = trees.put_tree({
            "units": "mm", "entryKind": "assembly", "components": {}, "occurrences": [],
            "links": links, "assembly": {"root": {
                "id": "root", "nodeType": "assembly", "children": [
                    {"id": link["id"], "nodeType": "link", "children": []} for link in links],
            }},
        })
        self.geometry, self.payloads = trees.capture_tree(self.tree)
        self.producer = surfaces.producer_identity()
        self.view = surfaces.request_view(self.tree, producer=self.producer)
        self.cid = next(iter(self.view["components"]))
        self.request = {
            "tree": self.tree, "viewId": self.view["viewId"], "producer": self.producer,
            "components": [{"cid": self.cid, "surfaceInput": self.view["components"][self.cid]["surfaceInput"]}],
        }
        self.manager = SurfaceSubscribers()
        self.addCleanup(lambda: [self.manager.cancel(token) for token in list(self.manager._jobs)])

    def test_metadata_releases_each_payload_and_native_capture_stays_owned(self):
        live = set()
        observed = []
        read = trees.read_verified_object

        class TrackedBytes(bytes):
            def __new__(cls, value):
                item = super().__new__(cls, value)
                live.add(id(item))
                return item

            def __del__(self):
                live.remove(id(self))

        def tracked(digest):
            self.assertFalse(live, "metadata retained a previous raw object during the next read")
            observed.append(digest)
            return TrackedBytes(read(digest))

        with mock.patch.object(trees, "read_verified_object", side_effect=tracked):
            metadata, payloads = trees.capture_tree(self.tree, retain_payloads=False)
        self.assertEqual(metadata, self.geometry)
        self.assertEqual(payloads, {})
        self.assertFalse(live)
        self.assertEqual(Counter(observed), Counter(self.payloads.keys()))
        metadata["occurrences"][0]["name"] = "private edit"
        owned, captured = trees.capture_tree(self.tree)
        self.assertEqual((owned, captured), (self.geometry, self.payloads))

        from cadgen._internal.component_package import decode_geometry_component
        from build123d import Location

        entry = owned["components"][self.cid]
        first = decode_geometry_component(entry, captured[entry["brep"]])
        second = decode_geometry_component(entry, captured[entry["brep"]])
        self.assertFalse(first.wrapped.IsPartner(second.wrapped))
        previous = second.bounding_box().min.X
        first.move(Location((12, 0, 0)))
        self.assertEqual(second.bounding_box().min.X, previous)
        self.assertEqual(captured, self.payloads)

    def test_resolve_and_each_poll_read_one_fresh_complete_closure(self):
        pending = PendingSurface()
        read = trees.read_verified_object
        with mock.patch.object(trees, "read_verified_object", wraps=read) as reads, \
             mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=pending) as submit:
            first = self.manager.resolve(json.dumps(self.request).encode())
            self.assertEqual(Counter(call.args[0] for call in reads.call_args_list), Counter(self.payloads.keys()))
            reads.reset_mock()
            polled = self.manager.resolve(json.dumps({**self.request, "job": first["job"]}).encode())
            self.assertEqual(polled["job"], first["job"])
            self.assertEqual(Counter(call.args[0] for call in reads.call_args_list), Counter(self.payloads.keys()))
            submit.assert_called_once()
        records = surfaces.derive(self.tree, [self.cid], producer=self.producer)
        pending.set_result(records)
        with mock.patch.object(trees, "read_verified_object", wraps=read) as reads:
            ready = self.manager.resolve(json.dumps({**self.request, "job": first["job"]}).encode())
            self.assertEqual(ready["components"][self.cid]["state"], "ready")
            self.assertEqual(Counter(call.args[0] for call in reads.call_args_list), Counter(self.payloads.keys()))
        self.assertEqual(trees.capture_tree(self.tree)[0], self.geometry)

    def test_metadata_entrypoints_read_once_before_producer_selection(self):
        from cadgen.store.view import descriptor_for_view

        read = trees.read_verified_object
        with mock.patch.object(trees, "read_verified_object", wraps=read) as reads:
            def selected(*args):
                self.assertEqual(Counter(call.args[0] for call in reads.call_args_list), Counter(self.payloads.keys()))
                return self.producer

            with mock.patch("cadgen.store.view._select_producer", side_effect=selected):
                view = descriptor_for_view(self.tree)
            self.assertEqual(view["viewId"], self.view["viewId"])
            self.assertEqual(Counter(call.args[0] for call in reads.call_args_list), Counter(self.payloads.keys()))
            reads.reset_mock()
            self.assertEqual(surfaces.request_view(self.tree, producer=self.producer), self.view)
            self.assertEqual(Counter(call.args[0] for call in reads.call_args_list), Counter(self.payloads.keys()))

    def test_missing_or_corrupt_unrequested_geometry_is_rejected_every_time(self):
        records = surfaces.derive(self.tree, [self.cid], producer=self.producer)
        other = next(entry for cid, entry in self.geometry["components"].items() if cid != self.cid)
        target = object_path(other["brep"])
        original = target.read_bytes()
        record = records[self.cid]
        for malformed in (None, b"corrupt geometry"):
            with self.subTest(missing=malformed is None):
                if malformed is None:
                    target.unlink()
                else:
                    target.write_bytes(malformed)
                try:
                    with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=AssertionError("damaged closure admitted")):
                        for call in (
                            lambda: trees.capture_tree(self.tree, retain_payloads=False),
                            lambda: surfaces.request_view(self.tree, producer=self.producer),
                            lambda: self.manager.resolve(json.dumps(self.request).encode()),
                            lambda: pinned_surface_object(self.tree, record["surfaceInput"], record["object"]),
                        ):
                            with self.assertRaises((OSError, ValueError)):
                                call()
                finally:
                    target.write_bytes(original)
        self.assertEqual(trees.capture_tree(self.tree), (self.geometry, self.payloads))


if __name__ == "__main__":
    unittest.main()
