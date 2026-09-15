"""A leftover ``<name>.step.js`` fails the build, naming what replaced it.

Animation used to be a companion ES module discovered by convention beside the
document. It is now ``@step(animation=...)``, embedded in the document's
sidecar, and nothing looks for the file any more. So a project carrying one
across the cutover gets exactly the failure law 10 forbids: a model that used
to articulate renders inert, at exit 0, with no message anywhere.

Law 8 says a retired surface fails loudly and names its replacement, which is
what these pin -- including on the run that rebuilds NOTHING, because a model
whose tree is already current takes the no-op path and would otherwise sail
past the check.

The viewer's half is the opposite by law 1 (a door never refuses a document):
it warns and renders. That is ``viewer/test_artifact_status.py``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

CADGEN_SRC = add_repo_path("packages/cadgen/src")

MODEL = """\
from cadgen import step


@step(out="part.step")
def model():
    from build123d.topology import Solid

    block = Solid.make_box(4, 4, 4)
    block.label = "block"
    return block


if __name__ == "__main__":
    model()
"""

RETIRED_MODULE = "export const clips = { spin: { duration: 1, update() {} } };\n"


class RetiredRenderModuleFailsTheBuild(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="retired-render-module-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.script = self.root / "part.py"
        self.script.write_text(MODEL, encoding="utf-8")
        self.document = self.root / "part.step"
        self.companion = self.root / "part.step.js"
        self.env = dict(os.environ)
        self.env.update({
            "CADGEN_DAEMON": "0",
            "CADGEN_COMPONENT_WORKERS": "1",
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "PYTHONPATH": str(CADGEN_SRC),
        })

    def _build(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.script)],
            cwd=str(self.root), env=self.env,
            capture_output=True, text=True, timeout=600,
        )

    def test_the_build_refuses_and_names_the_decorator_and_the_reference(self) -> None:
        self.companion.write_text(RETIRED_MODULE, encoding="utf-8")
        refused = self._build()
        output = refused.stdout + refused.stderr

        self.assertNotEqual(0, refused.returncode, output)
        self.assertIn("part.step.js", output)
        self.assertIn("@step(animation=...)", output)
        self.assertIn("kinematics", output)
        # Loud, and nothing half-written behind it.
        self.assertFalse(self.document.exists(), "the refused build wrote its document")

    def test_removing_it_builds_and_putting_it_back_refuses_the_no_op_run(self) -> None:
        clean = self._build()
        self.assertEqual(0, clean.returncode, clean.stdout + clean.stderr)
        self.assertTrue(self.document.is_file())

        # Nothing about the model changed, so this run rebuilds nothing at all.
        # The refusal still has to land: a check that only ran when geometry
        # was recomputed would let the stale file survive every later run.
        self.companion.write_text(RETIRED_MODULE, encoding="utf-8")
        refused = self._build()
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("part.step.js", refused.stdout + refused.stderr)


if __name__ == "__main__":
    unittest.main()
