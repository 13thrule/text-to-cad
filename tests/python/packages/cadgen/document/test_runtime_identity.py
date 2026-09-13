"""Loaded native dependency identity cannot be learned from authored callbacks."""
import os
import unittest
from unittest.mock import patch

from cadgen._document import Document
from cadgen._document.native import dependency_version
from cadgen._document.step_import import _runtime_identity as import_identity
from cadgen._document.step_product import _runtime_identity as product_identity


class RuntimeIdentityTests(unittest.TestCase):
    def test_dependency_metadata_is_captured_before_authored_python(self):
        expected = tuple(dependency_version(name) for name in ("cadquery-ocp", "build123d"))
        with patch("importlib.metadata.version", side_effect=AssertionError("authored metadata hook")):
            self.assertEqual(expected, tuple(dependency_version(name) for name in ("cadquery-ocp", "build123d")))
            first = product_identity(Document("first", runtime={"configuration": 1}))
            self.assertNotEqual(first, product_identity(Document("second", runtime={"configuration": 2})))
            with patch.dict(os.environ, {"CADGEN_STEP_STYLE_REORDER": "runtime-identity-test"}):
                self.assertNotEqual(first, product_identity(Document("third", runtime={"configuration": 1})))
            self.assertNotEqual(import_identity((1,)), import_identity((2,)))
        with self.assertRaisesRegex(ValueError, "unknown native document dependency"):
            dependency_version("unrelated-package")


if __name__ == "__main__":
    unittest.main()
