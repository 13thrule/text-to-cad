"""Captured source sessions isolate exact authored inputs from process imports."""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
import py_compile
import sys
import tempfile
from types import ModuleType
import unittest

from cadgen._document.sources import CapturedInput, SourceSession


REPO = Path(__file__).resolve().parents[5]
MODEL_TMP = REPO / "models/tmp"


class SourceSessionTest(unittest.TestCase):
    def setUp(self):
        MODEL_TMP.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(prefix="document-sources-", dir=MODEL_TMP)
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def write(self, relative: str, data: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
        return path

    def test_entry_executes_its_captured_buffer_even_if_it_rewrites_itself(self):
        entry = self.write(
            "self_edit.py",
            "from pathlib import Path\n"
            "VALUE = 'captured'\n"
            "Path(__file__).write_text(\"VALUE = 'later'\\n\", encoding='utf-8')\n",
        )
        captured = CapturedInput.read(entry)
        with SourceSession(captured) as session:
            module = session.load_entry()
            self.assertEqual("captured", module.VALUE)
            self.assertIs(module, session.load_entry())
            self.assertEqual((captured,), session.inputs)
        self.assertEqual("VALUE = 'later'\n", entry.read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(captured.data).hexdigest(), captured.digest)

    def test_package_and_circular_imports_execute_initializers_once(self):
        log = self.root / "initializers.log"
        self.write(
            "pkg/__init__.py",
            f"from pathlib import Path\nwith Path({str(log)!r}).open('a') as stream: stream.write('package\\n')\n"
            "from . import helper\n",
        )
        self.write(
            "pkg/helper.py",
            f"from pathlib import Path\nwith Path({str(log)!r}).open('a') as stream: stream.write('helper\\n')\n"
            "from . import main\n"
            "def seen(): return main.VALUE\n",
        )
        entry = self.write(
            "pkg/main.py",
            "VALUE = 'ready'\nfrom . import helper\nfrom . import helper as helper_again\n"
            "RESULT = helper.seen()\nSAME = helper is helper_again\n",
        )
        with SourceSession(CapturedInput.read(entry)) as session:
            module = session.load_entry()
            self.assertEqual("ready", module.RESULT)
            self.assertTrue(module.SAME)
            self.assertEqual(module, sys.modules["pkg.main"])
            names = [item.path.relative_to(self.root).as_posix() for item in session.inputs]
            self.assertEqual(["pkg/__init__.py", "pkg/helper.py", "pkg/main.py"], names)
        self.assertEqual(["package", "helper"], log.read_text().splitlines())
        self.assertNotIn("pkg", sys.modules)
        self.assertNotIn("pkg.main", sys.modules)

    def test_explicit_search_path_captures_helper_at_import_time(self):
        entry_dir = self.root / "entry"
        library = self.root / "library"
        entry_dir.mkdir()
        library.mkdir()
        entry = entry_dir / "main.py"
        helper = library / "shared_helper.py"
        entry.write_text("import shared_helper\nVALUE = shared_helper.VALUE\n")
        helper.write_text("VALUE = 'old!'\n")
        captured = CapturedInput.read(entry)
        helper.write_text("VALUE = 'new!'\n")
        cadgen_module = sys.modules["cadgen"]
        with SourceSession(captured, search_paths=(library,)) as session:
            self.assertEqual("new!", session.load_entry().VALUE)
            helper_input = next(item for item in session.inputs if item.path == helper)
            self.assertEqual(b"VALUE = 'new!'\n", helper_input.data)
            self.assertIs(cadgen_module, sys.modules["cadgen"])
        self.assertIs(cadgen_module, sys.modules["cadgen"])

    def test_regular_package_precedes_same_root_module(self):
        entry = self.write(
            "package_precedence/main.py",
            "import source_choice\nVALUE = source_choice.VALUE\n",
        )
        self.write("package_precedence/source_choice.py", "VALUE = 'module'\n")
        package = self.write(
            "package_precedence/source_choice/__init__.py",
            "VALUE = 'package'\n",
        )
        with SourceSession(CapturedInput.read(entry)) as session:
            self.assertEqual("package", session.load_entry().VALUE)
            captured_paths = {item.path for item in session.inputs}
            self.assertIn(package.resolve(), captured_paths)
            self.assertNotIn((entry.parent / "source_choice.py").resolve(), captured_paths)

    def test_empty_local_namespace_does_not_displace_cached_stdlib_module(self):
        fractions = importlib.import_module("fractions")
        entry = self.write(
            "namespace_fallthrough/main.py",
            "import fractions\nMODULE = fractions\nVALUE = fractions.Fraction(2, 3)\n",
        )
        (entry.parent / "fractions").mkdir()
        with SourceSession(CapturedInput.read(entry)) as session:
            module = session.load_entry()
            self.assertIs(fractions, module.MODULE)
            self.assertEqual((2, 3), (module.VALUE.numerator, module.VALUE.denominator))
            self.assertNotIn(entry.parent / "fractions", {item.path for item in session.inputs})
        self.assertIs(fractions, sys.modules["fractions"])

    def test_namespace_package_merges_multiple_managed_roots(self):
        entry = self.write(
            "namespace_roots/entry/main.py",
            "import shared.one\nimport shared.two\n"
            "VALUE = (shared.one.VALUE, shared.two.VALUE)\nPATHS = tuple(shared.__path__)\n",
        )
        first = self.write("namespace_roots/first/shared/one.py", "VALUE = 'one'\n")
        second = self.write("namespace_roots/second/shared/two.py", "VALUE = 'two'\n")
        search_paths = (first.parents[1], second.parents[1])
        with SourceSession(CapturedInput.read(entry), search_paths=search_paths) as session:
            module = session.load_entry()
            self.assertEqual(("one", "two"), module.VALUE)
            namespace_paths = tuple(Path(path).resolve() for path in module.PATHS)
            self.assertEqual(
                (first.parent.resolve(), second.parent.resolve()),
                tuple(path for path in namespace_paths
                      if path in {first.parent.resolve(), second.parent.resolve()}),
            )
            self.assertTrue({first.resolve(), second.resolve()} <= {
                item.path for item in session.inputs
            })

    def test_first_party_package_replaces_foreign_and_keeps_external_module(self):
        entry = self.write(
            "owned_package/main.py",
            "import owned_source_package\nimport fractions\n"
            "PACKAGE = owned_source_package\nEXTERNAL = fractions\n"
            "VALUE = owned_source_package.VALUE\n",
        )
        package = self.write(
            "owned_package/owned_source_package/__init__.py",
            "VALUE = 'captured'\n",
        )
        external = importlib.import_module("fractions")
        foreign = ModuleType("owned_source_package")
        foreign.VALUE = "foreign"
        foreign.__path__ = []
        previous = sys.modules.get("owned_source_package")
        sys.modules["owned_source_package"] = foreign
        try:
            with SourceSession(CapturedInput.read(entry)) as session:
                module = session.load_entry()
                self.assertEqual("captured", module.VALUE)
                self.assertIsNot(foreign, module.PACKAGE)
                self.assertIs(external, module.EXTERNAL)
                self.assertIn(package.resolve(), {item.path for item in session.inputs})
            self.assertIs(foreign, sys.modules["owned_source_package"])
            self.assertIs(external, sys.modules["fractions"])
        finally:
            if previous is None:
                sys.modules.pop("owned_source_package", None)
            else:
                sys.modules["owned_source_package"] = previous

    def test_helper_created_during_execution_is_captured_and_does_not_leak(self):
        previous = sys.modules.pop("created_helper", None)
        try:
            first = self.write(
                "created_one/main.py",
                "from pathlib import Path\nimport importlib\n"
                "Path(__file__).with_name('created_helper.py').write_text(\"VALUE = 'one'\\n\")\n"
                "importlib.invalidate_caches()\nimport created_helper\nVALUE = created_helper.VALUE\n",
            )
            with SourceSession(CapturedInput.read(first)) as session:
                self.assertEqual("one", session.load_entry().VALUE)
                self.assertIn(first.parent / "created_helper.py", {
                    item.path for item in session.inputs
                })
            self.assertNotIn("created_helper", sys.modules)

            second = self.write(
                "created_two/main.py",
                "import created_helper\nVALUE = created_helper.VALUE\n",
            )
            second_helper = self.write(
                "created_two/created_helper.py",
                "VALUE = 'two'\n",
            )
            with SourceSession(CapturedInput.read(second)) as session:
                self.assertEqual("two", session.load_entry().VALUE)
                captured = next(item for item in session.inputs
                                if item.path == second_helper.resolve())
                self.assertEqual(b"VALUE = 'two'\n", captured.data)
            self.assertNotIn("created_helper", sys.modules)
        finally:
            if previous is not None:
                sys.modules["created_helper"] = previous

    def test_function_provenance_survives_same_path_reload(self):
        entry = self.write(
            "reload_source/main.py",
            "import reload_helper\nOLD = reload_helper.value\nHELPER = reload_helper\n",
        )
        helper = self.write(
            "reload_source/reload_helper.py",
            "def value():\n    return 'old'\n",
        )
        with SourceSession(CapturedInput.read(entry)) as session:
            module = session.load_entry()
            old_function = module.OLD
            old_input = session.input_for_function(old_function)
            helper.write_text("def value():\n    return 'new'\n", encoding="utf-8")
            importlib.invalidate_caches()
            reloaded = importlib.reload(module.HELPER)
            new_function = reloaded.value
            new_input = session.input_for_function(new_function)
            self.assertEqual("old", old_function())
            self.assertEqual("new", new_function())
            self.assertEqual(helper.resolve(), old_input.path)
            self.assertEqual(helper.resolve(), new_input.path)
            self.assertNotEqual(old_input.digest, new_input.digest)
            self.assertEqual(b"def value():\n    return 'old'\n", old_input.data)
            self.assertEqual(b"def value():\n    return 'new'\n", new_input.data)

    def test_hyphenated_plain_entry_uses_a_private_import_name(self):
        entry = self.write("ordinary-model.py", "VALUE = 42\n")
        with SourceSession(CapturedInput.read(entry)) as session:
            module = session.load_entry()
            self.assertEqual(42, module.VALUE)
            self.assertTrue(module.__name__.startswith("_cadgen_source_"))

    def test_namespace_package_replaces_and_restores_same_prefix_foreign_modules(self):
        entry = self.write("namespace_case/main.py",
                           "from shared import helper\nVALUE = helper.VALUE\n")
        self.write("namespace_case/shared/helper.py", "VALUE = 'captured namespace'\n")
        foreign_package = ModuleType("shared")
        foreign_package.__path__ = []
        foreign_child = ModuleType("shared.foreign")
        before_package = sys.modules.get("shared")
        before_child = sys.modules.get("shared.foreign")
        sys.modules["shared"] = foreign_package
        sys.modules["shared.foreign"] = foreign_child
        try:
            with SourceSession(CapturedInput.read(entry)) as session:
                self.assertEqual("captured namespace", session.load_entry().VALUE)
                self.assertIsNot(foreign_package, sys.modules["shared"])
            self.assertIs(foreign_package, sys.modules["shared"])
            self.assertIs(foreign_child, sys.modules["shared.foreign"])
        finally:
            if before_package is None:
                sys.modules.pop("shared", None)
            else:
                sys.modules["shared"] = before_package
            if before_child is None:
                sys.modules.pop("shared.foreign", None)
            else:
                sys.modules["shared.foreign"] = before_child

    def test_unrelated_module_first_imported_by_source_remains_loaded(self):
        module_name = "fractions"
        previous = sys.modules.pop(module_name, None)
        entry = self.write("stdlib_import.py", f"import {module_name}\nVALUE = {module_name}.Fraction(1, 2)\n")
        try:
            with SourceSession(CapturedInput.read(entry)) as session:
                self.assertEqual((1, 2), (session.load_entry().VALUE.numerator,
                                          session.load_entry().VALUE.denominator))
            self.assertIn(module_name, sys.modules)
        finally:
            if previous is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous

    def test_same_name_foreign_module_and_sys_path_restore_between_projects(self):
        original_path = list(sys.path)
        foreign = ModuleType("helper")
        foreign.VALUE = "foreign"
        previous = sys.modules.get("helper")
        sys.modules["helper"] = foreign
        self.addCleanup(
            lambda: sys.modules.__setitem__("helper", previous)
            if previous is not None else sys.modules.pop("helper", None)
        )
        for project, value in (("one", "AAAA"), ("two", "BBBB"), ("one", "CCCC")):
            base = self.root / project
            base.mkdir(exist_ok=True)
            (base / "main.py").write_text("import helper\nVALUE = helper.VALUE\n")
            (base / "helper.py").write_text(f"VALUE = {value!r}\n")
            with SourceSession(CapturedInput.read(base / "main.py")) as session:
                self.assertEqual(value, session.load_entry().VALUE)
                self.assertIsNot(foreign, sys.modules["helper"])
            self.assertIs(foreign, sys.modules["helper"])
            self.assertEqual(original_path, sys.path)

    def test_failure_restores_modules_and_managed_data_binds_read_bytes(self):
        foreign = ModuleType("helper")
        previous = sys.modules.get("helper")
        sys.modules["helper"] = foreign
        self.addCleanup(
            lambda: sys.modules.__setitem__("helper", previous)
            if previous is not None else sys.modules.pop("helper", None)
        )
        self.write("helper.py", "VALUE = 1\n")
        entry = self.write("main.py", "import helper\nraise RuntimeError('source failed')\n")
        data = self.write("values.dat", "AAAA")
        path_before = list(sys.path)
        with self.assertRaisesRegex(RuntimeError, "source failed"):
            with SourceSession(CapturedInput.read(entry)) as session:
                self.assertEqual(b"AAAA", session.read_data("values.dat"))
                data.write_text("BBBB")
                session.load_entry()
        self.assertIs(foreign, sys.modules["helper"])
        self.assertEqual(path_before, sys.path)
        consumed = next(item for item in session.inputs if item.path == data)
        self.assertEqual(b"AAAA", consumed.data)
        self.assertEqual(hashlib.sha256(b"AAAA").hexdigest(), consumed.digest)
        with self.assertRaisesRegex(RuntimeError, "not active"):
            session.read_data(data)

    def test_bytecode_only_first_party_import_is_rejected(self):
        helper = self.write("ghost.py", "VALUE = 1\n")
        py_compile.compile(str(helper), doraise=True)
        helper.unlink()
        entry = self.write("main.py", "import ghost\n")
        with self.assertRaisesRegex(ModuleNotFoundError, "bytecode ignored"):
            with SourceSession(CapturedInput.read(entry)) as session:
                session.load_entry()

    def test_rejects_tampered_capture_and_unmanaged_data(self):
        entry = self.write("main.py", "VALUE = 1\n")
        with self.assertRaisesRegex(ValueError, "digest"):
            CapturedInput(entry, b"VALUE = 1\n", "0" * 64)
        outside = self.root.parent / "outside-document-source.dat"
        outside.write_bytes(b"outside")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        with SourceSession(CapturedInput.read(entry)) as session:
            with self.assertRaisesRegex(ValueError, "outside source roots"):
                session.read_data(outside)


if __name__ == "__main__":
    unittest.main()
