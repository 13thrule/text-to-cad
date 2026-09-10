"""Materialization memo hits preserve immutable bytes and private appearance."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


class MaterializeCacheTest(unittest.TestCase):
    def setUp(self):
        self.scratch = generated_cad_directory(prefix="materialize-recipes-")
        self.addCleanup(self.scratch.cleanup)
        patcher = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(Path(self.scratch.name) / "store")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.materialize = importlib.import_module("cadgen.store.materialize")
        self.materialize.reset_memo()
        self.addCleanup(self.materialize.reset_memo)

    def surf(self, faces, **extra):
        from cadgen._internal.surface_extract import SURF_VERSION
        from cadgen.store.objects import put_object

        body = json.dumps({"faces": faces, **extra}).encode("utf-8")
        payload = b"SURF" + struct.pack("<II", SURF_VERSION, len(body)) + body
        return put_object(payload), payload

    def test_recipe_hit_verifies_bytes_skips_json_and_returns_a_private_dictionary(self):
        from cadgen._internal import surface_extract

        digest, _ = self.surf([{"ord": 1, "color": [0.2, 0.3, 0.4, 1]}])
        with (
            mock.patch.object(surface_extract, "read_surf", wraps=surface_extract.read_surf) as parse,
            mock.patch.object(self.materialize, "read_verified_object", wraps=self.materialize.read_verified_object) as read,
        ):
            first = self.materialize._face_colors_for_object(digest)
            first[1] = (1, 0, 0, 1)
            second = self.materialize._face_colors_for_object(digest)
        self.assertEqual(second, {1: (0.2, 0.3, 0.4, 1.0)})
        self.assertIsNot(first, second)
        self.assertEqual(parse.call_count, 1)
        self.assertEqual(read.call_count, 2, "a hit bypassed current object verification")
        self.assertIsInstance(self.materialize._SURF_COLOR_MEMO[digest][1], tuple)

    def test_an_empty_face_color_recipe_is_a_real_hit(self):
        from cadgen._internal import surface_extract

        digest, _ = self.surf([{"ord": 1}, {"ord": 2, "color": None}])
        with mock.patch.object(surface_extract, "read_surf", wraps=surface_extract.read_surf) as parse:
            first = self.materialize._face_colors_for_object(digest)
            second = self.materialize._face_colors_for_object(digest)
        self.assertEqual(first, {})
        self.assertEqual(second, {})
        self.assertIsNot(first, second)
        self.assertEqual(parse.call_count, 1)

    def test_large_payload_with_tiny_recipe_fits_the_retained_memory_budget(self):
        from cadgen._internal import surface_extract

        digest, payload = self.surf([{"ord": 1}], padding="x" * 2048)
        with (
            mock.patch.object(self.materialize, "_SURF_COLOR_MEMO_CAPACITY", 1024),
            mock.patch.object(surface_extract, "read_surf", wraps=surface_extract.read_surf) as parse,
        ):
            self.assertEqual(self.materialize._face_colors_for_object(digest), {})
            self.assertEqual(self.materialize._face_colors_for_object(digest), {})
        self.assertGreater(len(payload), 1024)
        self.assertLessEqual(self.materialize._SURF_COLOR_MEMO_SIZE, 1024)
        self.assertIn(digest, self.materialize._SURF_COLOR_MEMO)
        self.assertEqual(parse.call_count, 1)

    def test_hit_cannot_mask_deletion_or_corruption_and_recovers_after_atomic_repair(self):
        from cadgen._internal import surface_extract
        from cadgen.store.objects import object_path, put_object

        digest, payload = self.surf([{"ord": 2, "color": [0.1, 0.2, 0.3, 1]}])
        expected = self.materialize._face_colors_for_object(digest)
        target = object_path(digest)
        target.unlink()
        with self.assertRaises(FileNotFoundError):
            self.materialize._face_colors_for_object(digest)
        target.write_bytes(payload + b"corrupt")
        with self.assertRaises(ValueError):
            self.materialize._face_colors_for_object(digest)
        self.assertEqual(put_object(payload, repair=True), digest)
        with mock.patch.object(surface_extract, "read_surf", wraps=surface_extract.read_surf) as parse:
            self.assertEqual(self.materialize._face_colors_for_object(digest), expected)
        self.assertEqual(parse.call_count, 0, "repair invalidated a still-correct immutable recipe")

    def test_invalid_colors_never_enter_the_recipe_cache(self):
        cases = [
            [{"ord": 0, "color": [1, 0, 0, 1]}],
            [{"ord": 1, "color": [float("nan"), 0, 0, 1]}],
            [{"ord": 1, "color": [1, 0, 0, 1]}, {"ord": 1, "color": [0, 0, 1, 1]}],
        ]
        for faces in cases:
            with self.subTest(faces=faces):
                digest, _ = self.surf(faces)
                with self.assertRaises(ValueError):
                    self.materialize._face_colors_for_object(digest)
                self.assertNotIn(digest, self.materialize._SURF_COLOR_MEMO)

    def test_recipe_lru_has_byte_and_entry_bounds(self):
        digests = [self.surf([{"ord": ordinal, "color": [0.1, 0.2, 0.3, 1]}])[0] for ordinal in (1, 2, 3)]
        with mock.patch.object(self.materialize, "_SURF_COLOR_MEMO_MAX_ENTRIES", 2):
            for digest in digests[:2]:
                self.materialize._face_colors_for_object(digest)
            self.materialize._face_colors_for_object(digests[0])
            self.materialize._face_colors_for_object(digests[2])
        self.assertEqual(list(self.materialize._SURF_COLOR_MEMO), [digests[0], digests[2]])
        self.materialize.reset_memo()
        with mock.patch.object(self.materialize, "_SURF_COLOR_MEMO_CAPACITY", 2000):
            for digest in digests:
                self.materialize._face_colors_for_object(digest)
            self.assertLessEqual(self.materialize._SURF_COLOR_MEMO_SIZE, 2000)
            self.assertEqual(list(self.materialize._SURF_COLOR_MEMO), digests[1:])
        self.materialize.reset_memo()
        with mock.patch.object(self.materialize, "_SURF_COLOR_MEMO_CAPACITY", 1):
            self.assertTrue(self.materialize._face_colors_for_object(digests[0]))
        self.assertEqual(self.materialize._SURF_COLOR_MEMO_SIZE, 0)
        self.assertEqual(len(self.materialize._SURF_COLOR_MEMO), 0)

    def test_recipe_charge_covers_retained_values_including_large_ordinals(self):
        digest, _ = self.surf([
            {"ord": 1, "color": [0.1, 0.2, 0.3, 1]},
            {"ord": 10 ** 1000, "color": [0.4, 0.5, 0.6, 1]},
        ])
        empty_memo_bytes = sys.getsizeof(self.materialize._SURF_COLOR_MEMO)
        self.materialize._face_colors_for_object(digest)
        charge, _ = self.materialize._SURF_COLOR_MEMO[digest]
        seen = set()

        def retained_size(value):
            if id(value) in seen:
                return 0
            seen.add(id(value))
            return sys.getsizeof(value) + (
                sum(retained_size(item) for item in value) if isinstance(value, tuple) else 0
            )

        retained = (
            sys.getsizeof(self.materialize._SURF_COLOR_MEMO) - empty_memo_bytes
            + retained_size(digest) + retained_size(self.materialize._SURF_COLOR_MEMO[digest])
        )
        self.assertGreaterEqual(charge, retained)

    def test_reset_releases_both_memos_without_changing_exposed_values(self):
        from cadgen.store.objects import put_object

        digest, _ = self.surf([{"ord": 1, "color": [0.4, 0.3, 0.2, 1]}])
        exposed = self.materialize._face_colors_for_object(digest)
        brep = put_object(b"immutable bytes")
        self.materialize._bytes_for_object(brep)
        self.materialize.reset_memo()
        self.assertEqual(self.materialize._BREP_BYTES_MEMO_SIZE, 0)
        self.assertEqual(self.materialize._SURF_COLOR_MEMO_SIZE, 0)
        self.assertFalse(self.materialize._BREP_BYTES_MEMO)
        self.assertFalse(self.materialize._SURF_COLOR_MEMO)
        self.assertEqual(exposed, {1: (0.4, 0.3, 0.2, 1.0)})

    def test_corrupt_brep_miss_cannot_poison_materialization_after_atomic_repair(self):
        from build123d import Solid
        from cadgen._internal.component_package import _shape_brep_bytes
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.objects import object_path, put_object
        from cadgen.store.trees import flatten

        tree, _, _ = build_tree_from_compound(Solid.make_box(8, 6, 4), root_name="box")
        brep = next(iter(flatten(tree)["components"].values()))["brep"]
        target = object_path(brep)
        original = target.read_bytes()
        # Both an unreadable payload and a readable but different native shape
        # must be rejected before memo admission, not just on failed decoding.
        cases = ((False, b"not a BREP"), (True, _shape_brep_bytes(Solid.make_box(1, 2, 3))))
        for readable, corrupt in cases:
            with self.subTest(readable=readable):
                self.materialize.reset_memo()
                target.write_bytes(corrupt)
                with self.assertRaises(ValueError):
                    self.materialize.materialize(tree)
                self.assertNotIn(brep, self.materialize._BREP_BYTES_MEMO)
                self.assertEqual(put_object(original, repair=True), brep)
                recovered = self.materialize.materialize(tree)
                self.assertAlmostEqual(recovered.volume, 8 * 6 * 4)
                self.assertEqual(self.materialize._BREP_BYTES_MEMO[brep], original)


if __name__ == "__main__":
    unittest.main()
