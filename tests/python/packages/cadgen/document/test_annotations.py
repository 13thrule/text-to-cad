"""Durable annotations use actual independent STEP paths and exact byte binding."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from cadgen._document.annotations import (companion_path, prepare_annotations,
                                          read_annotations, paths_from_product)


class AnnotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.python.packages.cadgen.document.test_appearance import AppearanceNativeTests
        from tests.python.support.tmp_root import generated_cad_directory
        from cadgen._document.step_product import StepProductSession
        temporary = generated_cad_directory(prefix="document-annotations-")
        cls.addClassCleanup(temporary.cleanup)
        cls.directory = Path(temporary.name).resolve()
        document, revision = AppearanceNativeTests._styled_cut(None)
        moved = list(revision.root.transform); moved[3] = 50.
        with document.begin() as tx:
            tx.bind_root(replace(revision.root, transform=tuple(moved)), unrepresented_metadata=())
            revision = tx.commit()
        with StepProductSession(document, revision.revision_id, work_directory=cls.directory) as session:
            cls.step = session.prepare("part.step")
        cls.paths = tuple(node.path for node in cls.step.returned_root.children)
        cls.inventory = paths_from_product(cls.step)

    def prepare(self, rows):
        return prepare_annotations(self.step.payload, self.inventory, rows)

    def read(self, payload, *, step=None):
        return read_annotations(self.step.payload if step is None else step,
                                self.inventory, payload)

    def value(self):
        return json.loads(self.prepare([{"path": self.paths[0], "pbr": {"roughness": .2},
                                        "material": "brushed steel"}]).payload)

    def test_saved_envelope_paths_and_deterministic_value_only_readback(self):
        self.assertEqual((1, 1), self.step.returned_root_path)
        self.assertEqual(((1, 1, 1), (1, 1, 2)), self.paths)
        first = {"path": self.paths[0], "pbr": {"roughness": .2}, "material": "brushed steel"}
        second = {"path": self.paths[1], "pbr": {"metalness": .7, "opacity": .4}}
        product = self.prepare([second, first])
        self.assertEqual(product.payload, self.prepare([first, second]).payload)
        first["pbr"]["roughness"] = .9
        self.assertEqual(.2, product.occurrences[0].appearance["pbr"]["roughness"])
        path = companion_path(self.directory / self.step.basename)
        path.write_bytes(product.payload)
        # No source document or native value participates in this read.
        actual = self.read(path.read_bytes())
        self.assertEqual(product, actual)
        with self.assertRaises(TypeError):
            actual.occurrences[0].appearance["pbr"]["roughness"] = .8
        self.assertEqual("part.step.json", path.name)

    def test_empty_product_requires_companion_deletion(self):
        self.assertIsNone(self.prepare([]).payload)
        empty = self.prepare([{"path": self.paths[0], "pbr": {}, "material": ""}])
        self.assertIsNone(empty.payload)
        self.assertEqual((), self.read(None).occurrences)
        value = self.value(); value["occurrences"] = []
        with self.assertRaisesRegex(ValueError, "removed"):
            self.read(json.dumps(value).encode())

    def test_step_byte_and_size_drift_rejected(self):
        payload = json.dumps(self.value()).encode()
        for step in (self.step.payload + b" ", self.step.payload[:-1] + b" "):
            with self.subTest(size=len(step)), self.assertRaisesRegex(ValueError, "binding"):
                self.read(payload, step=step)
        for size in (True, len(self.step.payload) + 1):
            value = self.value(); value["step"]["bytes"] = size
            with self.assertRaisesRegex(ValueError, "binding"):
                self.read(json.dumps(value).encode())

    def test_unknown_duplicate_group_and_source_paths_rejected(self):
        for path in ((1,), (1, 1), (1, 1, 9), ("root", "red"), (True, 1, 1)):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.prepare([{"path": path, "pbr": {"roughness": .2}}])
        row = {"path": self.paths[0], "material": "steel"}
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.prepare([row, row])
        wrong = replace(self.step.saved_roots[0], path=(2,))
        with self.assertRaisesRegex(ValueError, "actual saved hierarchy"):
            paths_from_product(replace(self.step, saved_roots=(wrong,)))

    def test_old_unknown_and_duplicate_schema_fields_rejected(self):
        for change in ({"version": 0}, {"version": True}, {"schema": "old"}, {"source": "part.py"}):
            value = {**self.value(), **change}
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "schema"):
                self.read(json.dumps(value).encode())
        payload = json.dumps(self.value()).encode()
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            self.read(payload.replace(b'{', b'{"version":1,', 1))

    def test_native_fields_and_unsupported_pbr_rejected(self):
        for fields in ({"face_colors": []}, {"color": [1, 0, 0, 1]},
                       {"physical_material": {}}, {"pbr": {"texture": "image"}},
                       {"pbr": {"opacity": True}}, {"pbr": {"roughness": float("nan")}},
                       {"material": "x" * 4097}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.prepare([{"path": self.paths[0], **fields}])

    def test_byte_and_hierarchy_limits_precede_large_products(self):
        payload = json.dumps(self.value()).encode()
        with patch("cadgen._document.annotations.MAX_BYTES", 32):
            with self.assertRaisesRegex(ValueError, "limit"):
                self.read(payload)
            with self.assertRaisesRegex(ValueError, "limit"):
                self.prepare([{"path": self.paths[0], "material": "steel"}])
        with patch("cadgen._document.annotations.MAX_NODES", 1):
            with self.assertRaisesRegex(ValueError, "limit"):
                self.read(None)
