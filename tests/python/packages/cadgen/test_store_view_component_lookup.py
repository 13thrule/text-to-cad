"""A virtual component lookup walks object trees without composing occurrences."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")


class ComponentLookup(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = generated_cad_directory(prefix="store-view-component-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = self.root / "store"
        self._environment = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store)})
        self._environment.start()
        self.addCleanup(self._environment.stop)

    def _object(self, payload: bytes = b"SURF") -> str:
        from cadgen.store.objects import put_object

        return put_object(payload)

    def _tree(self, *, components=None, links=None, occurrences=None) -> str:
        from cadgen.store.trees import put_tree

        stored_links = []
        for index, link in enumerate(links or [], start=1):
            stored = dict(link)
            stored.setdefault("id", f"o1.{index}")
            stored_links.append(stored)
        return put_tree({
            "components": components or {},
            "occurrences": occurrences or [],
            "links": stored_links,
            "assembly": {"root": {
                "id": "o1",
                "nodeType": "assembly",
                "children": [
                    {"id": link["id"], "nodeType": "link", "tree": link.get("tree"), "children": []}
                    for link in stored_links
                ],
            }},
        })

    def test_root_component_lookup_does_not_flatten_or_read_producer_indexes(self) -> None:
        from cadgen.store import records, view

        digest = self._object()
        tree = self._tree(components={"c0": {"surf": digest}})
        with mock.patch.object(view, "descriptor_for_view", side_effect=AssertionError("flattened")), \
                mock.patch.object(records, "read_record", side_effect=AssertionError("record read")), \
                mock.patch.object(records, "model_for_output", side_effect=AssertionError("output read")):
            payload, content_type = view.virtual_path(f"{tree}/components/c0.surf")
        self.assertEqual(Path(payload).read_bytes(), b"SURF")
        self.assertEqual(content_type, "application/octet-stream")

    def test_linked_component_lookup_ignores_occurrence_placement_and_reuse(self) -> None:
        from cadgen.store import view

        digest = self._object()
        child = self._tree(
            components={"linked": {"surf": digest}},
            occurrences=[{"id": "o1", "component": "linked", "transform": [99] * 16}],
        )
        parent = self._tree(links=[
            {"id": "o1.1", "tree": child, "transform": [1] * 16},
            {"id": "o1.2", "tree": child, "transform": [2] * 16},
        ])
        with mock.patch.object(view, "flatten", side_effect=AssertionError("composed occurrences")):
            payload, _content_type = view.virtual_path(f"{parent}/components/linked.surf")
        self.assertEqual(Path(payload).read_bytes(), b"SURF")

    def test_same_cid_must_resolve_to_one_exact_object(self) -> None:
        from cadgen.store.view import virtual_path

        first = self._object(b"first")
        second = self._object(b"second")
        child_a = self._tree(components={"shared": {"surf": first}})
        child_b = self._tree(
            components={"shared": {"surf": first}},
            occurrences=[{"id": "o1", "component": "shared", "transform": [7] * 16}],
        )
        coherent = self._tree(links=[{"tree": child_a}, {"tree": child_b}])
        payload, _ = virtual_path(f"{coherent}/components/shared.surf")
        self.assertEqual(Path(payload).read_bytes(), b"first")

        conflicting = self._tree(links=[
            {"tree": child_a},
            {"tree": self._tree(components={"shared": {"surf": second}})},
        ])
        self.assertEqual(virtual_path(f"{conflicting}/components/shared.surf"), (None, ""))

    def test_full_hash_fallback_is_confined_to_the_named_tree(self) -> None:
        from cadgen.store.view import virtual_path

        referenced = self._object(b"inside")
        unreferenced = self._object(b"outside")
        tree = self._tree(components={"short-cid": {"surf": referenced}})
        payload, _ = virtual_path(f"{tree}/components/{referenced}.surf")
        self.assertEqual(Path(payload).read_bytes(), b"inside")
        upper_payload, _ = virtual_path(f"{tree}/components/{referenced.upper()}.surf")
        self.assertEqual(Path(upper_payload).read_bytes(), b"inside")
        self.assertEqual(virtual_path(f"{tree}/components/{unreferenced}.surf"), (None, ""))

    def test_missing_root_link_or_target_fails_the_whole_lookup(self) -> None:
        from cadgen.store.objects import object_path
        from cadgen.store.view import virtual_path

        digest = self._object()
        child = self._tree(components={"c0": {"surf": digest}})
        parent = self._tree(links=[{"tree": child}])
        object_path(child).unlink()
        self.assertEqual(virtual_path(f"{parent}/components/c0.surf"), (None, ""))
        self.assertEqual(virtual_path(f"{parent}/assembly.json"), (None, ""))

        target = self._object(b"target")
        target_tree = self._tree(components={"c0": {"surf": target}})
        object_path(target).unlink()
        self.assertEqual(virtual_path(f"{target_tree}/components/c0.surf"), (None, ""))

        live_target = self._object(b"live target")
        missing_root = self._tree(components={"c0": {"surf": live_target}})
        object_path(missing_root).unlink()
        self.assertEqual(virtual_path(f"{missing_root}/components/c0.surf"), (None, ""))

    def test_cycle_and_corrupt_link_are_rejected(self) -> None:
        from cadgen.store import view

        first, second = "a" * 64, "b" * 64
        trees = {
            first: {"kind": "tree", "components": {}, "links": [{"tree": second}]},
            second: {"kind": "tree", "components": {}, "links": [{"tree": first}]},
        }
        with mock.patch.object(view, "get_tree", side_effect=lambda digest: trees.get(digest)):
            self.assertIsNone(view.component_object_for_tree(first, "c0.surf"))
        digest = self._object()
        broken = self._tree(
            components={"c0": {"surf": digest}},
            links=[{"tree": "not-a-hash"}],
        )
        self.assertEqual(view.virtual_path(f"{broken}/components/c0.surf"), (None, ""))

    def test_lookup_follows_the_current_store_environment(self) -> None:
        from cadgen.store.view import virtual_path

        digest = self._object()
        tree = self._tree(components={"c0": {"surf": digest}})
        payload, _ = virtual_path(f"{tree}/components/c0.surf")
        self.assertEqual(Path(payload).read_bytes(), b"SURF")
        os.environ["CADGEN_CACHE_DIR"] = str(self.root / "different-store")
        self.assertEqual(virtual_path(f"{tree}/components/c0.surf"), (None, ""))

    def test_descriptor_path_keeps_flattened_output(self) -> None:
        from cadgen.store.view import virtual_path

        digest = self._object()
        tree = self._tree(components={"c0": {"surf": digest}})
        body, content_type = virtual_path(f"{tree}/assembly.json")
        self.assertEqual(content_type, "application/json")
        self.assertIn(b'"kind": "assembly-package"', body)
        self.assertIn(b'"surfObject"', body)


if __name__ == "__main__":
    unittest.main()
