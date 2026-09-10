"""Source ownership is by file; result dependencies name exact model calls."""

from __future__ import annotations

import os
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


FAMILY = """
from cadgen import step
from cadgen import build123d as bd

WIDTH = 4

def helper():
    return WIDTH

@step
def left():
    return bd.Box(1, 1, 1)

@step
def right():
    return bd.Box(2, 2, 2)
"""


class ModelClosureBoundaries(unittest.TestCase):
    def setUp(self):
        from cadgen.store.closure import forget_model_files

        scratch = generated_cad_directory(prefix="closure-model-boundaries-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        env.start()
        self.addCleanup(env.stop)
        forget_model_files()
        self.addCleanup(forget_model_files)
        self.family = self.write("family.py", FAMILY)

    def write(self, name, source):
        path = self.root / name
        path.write_text(textwrap.dedent(source).strip() + "\n", encoding="utf-8")
        return path

    def parent(self, imports="", body="return left()"):
        return self.write(
            "parent.py",
            "from cadgen import step\n" + imports + "\n\n@step\ndef parent():\n"
            + textwrap.indent(body, "    "),
        )

    def executed(self, *paths):
        from cadgen._internal.source_hash import _semantic_source_hash

        return {str(path.resolve()): _semantic_source_hash(path) for path in paths}

    def record(self, script, function, *, tree, children=()):
        from cadgen.store.closure import build_closure
        from cadgen.store.index import model_ref
        from cadgen.store.records import write_record

        closure = build_closure(script, executed={}, children=[child for child, _pin in children])
        reference = model_ref(script, function)
        write_record(reference, {
            "entryKind": "part", "sourceKind": "python", "tree": tree,
            "closure": closure.as_json(), "constants": closure.constants,
            "children": [{"model": child, "tree": pin} for child, pin in children],
            "outputs": {},
        })
        return reference

    def test_imported_model_names_from_a_multi_model_file_are_result_edges(self):
        from cadgen.store.closure import is_model_file, static_closure

        cases = (
            ("from family import left", "return left()"),
            ("from family import left, right", "return left()"),
            ("from family import left as selected", "return selected()"),
            ("import family as parts", "return parts.left()"),
        )
        # Result-only classification is AST work and must not import the model
        # merely to choose one of its declarations.
        with mock.patch("cadgen.metadata.imported_model", side_effect=AssertionError("model imported")):
            self.assertTrue(is_model_file(self.family))
            for imports, body in cases:
                with self.subTest(imports=imports):
                    closure = static_closure(self.parent(imports, body))
                    self.assertEqual(closure.child_models, (self.family,))
                    self.assertEqual(closure.source_files, ())
                    self.assertEqual(closure.constants, {})

    def test_a_later_helper_import_promotes_the_whole_file_to_source(self):
        from cadgen.store.closure import static_closure

        for imports in (
            "from family import left\nfrom family import helper",
            "from family import helper\nfrom family import left",
            "from family import left, helper",
            "from family import left\nfrom family import *",
        ):
            with self.subTest(imports=imports):
                closure = static_closure(self.parent(imports))
                self.assertEqual(closure.source_files, (self.family,))
                self.assertEqual(closure.child_models, ())
                self.assertEqual(closure.constants, {})

    def test_an_unrelated_plain_helper_remains_a_source_dependency(self):
        from cadgen.store.closure import build_closure, static_closure

        helper = self.write("utility.py", "def helper():\n    return 1\n")
        parent = self.parent("from family import left\nfrom utility import helper")
        statics = static_closure(parent)
        self.assertEqual(statics.child_models, (self.family,))
        self.assertEqual(statics.source_files, (helper,))
        closure = build_closure(parent, executed=self.executed(parent, self.family, helper),
                                children=[str(self.family) + "::left"])
        self.assertEqual(closure.files, ("parent.py", "utility.py"))

    def test_multi_model_constants_keep_value_dependencies(self):
        from cadgen.store.closure import build_closure, changed_constant

        parent = self.parent("from family import left, WIDTH")
        closure = build_closure(parent, executed={})
        self.assertEqual(closure.files, ("parent.py",))
        self.assertEqual(set(closure.constants), {"family.py"})
        self.assertEqual(set(closure.constants["family.py"]), {"WIDTH"})
        self.family.write_text(FAMILY.replace("WIDTH = 4", "WIDTH = 5"), encoding="utf-8")
        self.assertEqual(changed_constant(parent, closure.constants), "family.py:WIDTH")

    def test_named_runtime_child_refs_retain_unproven_dynamic_source(self):
        from cadgen.store.closure import build_closure, static_closure

        helper = self.write("utility.py", "def helper():\n    return 1\n")
        self.family.write_text("from utility import helper\n" + FAMILY, encoding="utf-8")
        parent = self.parent(body="import importlib\nreturn importlib.import_module('family').left()")
        self.assertEqual(static_closure(parent).child_models, ())
        closure = build_closure(parent, executed=self.executed(parent, self.family, helper),
                                children=[str(self.family) + "::left"])
        self.assertEqual(closure.files, ("family.py", "parent.py", "utility.py"))
        # A helper reached directly by the parent belongs to both closures.
        parent = self.parent("from utility import helper", body="import importlib\nreturn importlib.import_module('family').left()")
        closure = build_closure(parent, executed=self.executed(parent, self.family, helper),
                                children=[str(self.family) + "::left"])
        self.assertEqual(closure.files, ("family.py", "parent.py", "utility.py"))

    def test_dynamic_helper_edit_is_stale_even_after_the_child_rebuilds_identically(self):
        from cadgen.store.gate import stale
        from cadgen.store.records import read_record
        from cadgen.store.trees import put_tree

        child_tree = put_tree({"label": "child", "components": {}, "links": []})
        left = self.record(self.family, "left", tree=child_tree)
        parent_script = self.parent(
            "from cadgen import build123d as bd",
            body="import importlib\nparts = importlib.import_module('family')\n"
                 "return bd.Compound(children=[parts.left(), bd.Box(parts.helper(), 1, 1)])",
        )
        parent = self.record(parent_script, "parent", tree=child_tree, children=[(left, child_tree)])
        self.assertIn("family.py", read_record(parent)["closure"]["files"])
        self.assertFalse(stale(parent).stale)
        self.family.write_text(FAMILY.replace("WIDTH = 4", "WIDTH = 5"), encoding="utf-8")
        # left() does not read WIDTH, so its newly current result is identical.
        self.record(self.family, "left", tree=child_tree)
        self.assertFalse(stale(left).stale)
        verdict = stale(parent)
        self.assertTrue(verdict.stale, "an identical child pin must not hide the parent's direct helper input")
        self.assertTrue(any(clause["clause"] == 2 and clause["stale"] for clause in verdict.clauses))

    def test_nested_model_imports_do_not_hide_nested_helper_dependencies(self):
        from cadgen.store.closure import build_closure, static_closure

        parent = self.parent(body="from family import left\nreturn left()")
        self.assertEqual(static_closure(parent).child_models, (self.family,))
        parent = self.parent("from family import left", body="from family import helper\nreturn left()")
        closure = build_closure(parent, executed=self.executed(parent, self.family),
                                children=[str(self.family) + "::left"])
        self.assertEqual(closure.files, ("family.py", "parent.py"))

    def test_exact_function_pins_and_whole_file_sibling_invalidation_remain(self):
        from cadgen.store.closure import build_closure
        from cadgen.store.gate import stale
        from cadgen.store.index import model_ref
        from cadgen.store.records import read_record
        from cadgen.store.trees import put_tree

        own = build_closure(self.family, executed=self.executed(self.family),
                            children=[str(self.family) + "::left"])
        self.assertEqual(own.files, ("family.py",), "a same-file child cannot remove the caller's own source")
        # Empty artifact graphs suffice for a gate/closure test; no CAD body or
        # kernel operation runs. Tree identity distinguishes the two results.
        left_tree = put_tree({"label": "left", "components": {}, "links": []})
        right_tree = put_tree({"label": "right", "components": {}, "links": []})
        left = self.record(self.family, "left", tree=left_tree)
        right = self.record(self.family, "right", tree=right_tree)
        parent_script = self.parent("from family import left")
        parent = self.record(parent_script, "parent", tree=left_tree, children=[(left, left_tree)])
        self.assertEqual(read_record(parent)["children"], [{"model": model_ref(self.family, "left"), "tree": left_tree}])
        self.assertFalse(stale(parent).stale)
        # The uncalled sibling's result does not enter the parent's pins.
        self.record(self.family, "right", tree=left_tree)
        self.assertFalse(stale(parent).stale)
        self.family.write_text(FAMILY.replace("def right():\n    return bd.Box(2, 2, 2)", "def right():\n    return bd.Box(3, 3, 3)"), encoding="utf-8")
        self.assertTrue(stale(left).stale, "sibling source edits still invalidate the whole file")
        self.assertTrue(stale(right).stale)
        self.assertTrue(stale(parent).stale, "the exact called child's stale source must still reach its parent")


if __name__ == "__main__":
    unittest.main()
