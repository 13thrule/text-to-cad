"""Retained source execution through the real declared-output pipeline.

The probe has its own interpreter because legacy interception tests may have
patched build123d in the test runner. A document worker must own a clean native
runtime; the prototype intentionally rejects a mixed interception stack.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


SOURCE = '''from cadgen import build123d as bd, step
from pathlib import Path

RADIUS = {radius}
SHIFT = {shift}
COUNT = {count}

def plate():
    shape = bd.Box(30, 20, 6)
    for x in (-8, 8):
        shape = shape - bd.Pos(x, 0, 0) * bd.Cylinder(RADIUS, 10)
    return shape

@step
def fixture():
    counter = Path(__file__).with_suffix('.runs')
    counter.write_text(counter.read_text() + 'run\\n' if counter.exists() else 'run\\n')
    shape = plate()
    if COUNT == 1:
        return shape
    parts = []
    for i in range(COUNT):
        part = bd.Pos((i % 6) * 40, (i // 6) * 30 + SHIFT, 0) * shape
        part.label = 'plate-' + str(i)
        parts.append(part)
    return bd.Compound(children=parts, label='fixture')

if __name__ == '__main__':
    fixture()
'''


def _probe():
    from cadgen._document.service import DocumentService
    from cadgen.cli._run_model import run_model_argv
    from tests.python.support.tmp_root import generated_cad_directory
    from build123d import import_step

    def occurrence_labels(path):
        # build123d.import_step reads the prototype name for every reference.
        # Read instance labels directly so shared prototypes cannot mask a
        # dropped assembly occurrence name in the export bridge.
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPCAFControl import STEPCAFControl_Reader
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDataStd import TDataStd_Name
        from OCP.TDF import TDF_LabelSequence
        from OCP.TDocStd import TDocStd_Document
        from OCP.XCAFDoc import XCAFDoc_DocumentTool
        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)
        check.assertEqual(IFSelect_RetDone, reader.ReadFile(str(path)))
        document = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
        check.assertTrue(reader.Transfer(document))
        shapes = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
        roots = TDF_LabelSequence()
        shapes.GetFreeShapes(roots)
        check.assertEqual(1, roots.Length())
        children = TDF_LabelSequence()
        shapes.GetComponents_s(roots.Value(1), children)
        labels = []
        for index in range(1, children.Length() + 1):
            label = children.Value(index)
            check.assertTrue(label.IsAttribute(TDataStd_Name.GetID_s()))
            name = TDataStd_Name()
            check.assertTrue(label.FindAttribute(TDataStd_Name.GetID_s(), name))
            labels.append(name.Get().ToExtString())
        return labels

    check = unittest.TestCase()
    with generated_cad_directory(prefix="document-pipeline-") as folder:
        root = Path(folder).resolve()
        os.environ.update({
            "CADGEN_CACHE_DIR": str(root / "store"), "CADGEN_DAEMON": "0",
            "CADGEN_OP_MEMO": "0", "CADGEN_MEMO_CACHE": "0", "CADGEN_DETERMINISM": "0",
        })
        source = root / "fixture.py"
        service = DocumentService()
        records = []

        def build(radius, shift, count, *, managed=True):
            source.write_text(SOURCE.format(radius=radius, shift=shift, count=count))
            stream = io.StringIO()
            with (service.activate() if managed else contextlib.nullcontext()), contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                code = run_model_argv([str(source), *([] if managed else ["--force"]), "--verbose"])
            check.assertEqual(0, code, stream.getvalue())
            document = root / "fixture.step"
            check.assertTrue(document.is_file(), stream.getvalue())
            native = import_step(document)
            check.assertTrue(native.is_valid)
            check.assertEqual(count, len(native.solids()))
            if count > 1:
                check.assertEqual(count, len(native.children))
                check.assertEqual({f"plate-{i}" for i in range(count)}, set(occurrence_labels(document)))
            bounds = native.bounding_box()
            facts = {
                "volume": native.volume,
                "min": tuple(bounds.min), "max": tuple(bounds.max),
                "faces": len(native.faces()), "solids": len(native.solids()),
            }
            if managed:
                attempt = service.last_attempt
                check.assertEqual("exports_complete", attempt.state, attempt.error)
                records.append({"radius": radius, "shift": shift, "count": count,
                                "source_seconds": attempt.source_seconds,
                                "stats": vars(attempt.stats) if hasattr(attempt.stats, "__dict__") else repr(attempt.stats)})
            return facts

        original = build(1.5, 0, 1)
        repeated = build(1.5, 0, 1)
        check.assertEqual(original, repeated)
        edited = build(2.0, 0, 1)
        check.assertLess(edited["volume"], original["volume"])
        assembly = build(2.0, 0, 24)
        moved = build(2.0, 5, 24)
        check.assertAlmostEqual(assembly["volume"], moved["volume"], places=6)
        check.assertAlmostEqual(5, moved["min"][1] - assembly["min"][1], places=6)
        check.assertEqual(5, len(source.with_suffix(".runs").read_text().splitlines()))
        # The native source and its saved STEP may legitimately differ after
        # translation. Resident source geometry must never impersonate the
        # file's bytes in either warm or cache-free saved-file readers.
        from tests.python.packages.cadgen.test_tree_reflects_written_step import _ROT_CAP
        from cadgen import read_step
        cap_source = root / "rot_cap.py"
        cap_source.write_text(_ROT_CAP)
        capture = io.StringIO()
        with service.activate(), contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
            code = run_model_argv([str(cap_source), "--verbose"])
        check.assertEqual(0, code, capture.getvalue())
        cap_file = cap_source.with_suffix(".step")
        saved_volume = import_step(cap_file).volume
        check.assertAlmostEqual(saved_volume, read_step(cap_file).volume, places=6)
        cap_source.unlink()
        shutil.rmtree(root / "store")
        check.assertAlmostEqual(saved_volume, read_step(cap_file).volume, places=6)
        # Run the legacy control last: that runner installs its interception
        # stack even when operation reuse is disabled. Managed workers reject
        # coexistence with that stack rather than silently changing it.
        plain = build(2.0, 5, 24, managed=False)
        check.assertEqual(moved["faces"], plain["faces"])
        check.assertEqual(moved["solids"], plain["solids"])
        check.assertAlmostEqual(moved["volume"], plain["volume"], places=6)
        for key in ("min", "max"):
            for left, right in zip(moved[key], plain[key]):
                check.assertAlmostEqual(left, right, places=6)
        print(json.dumps({"ok": True, "attempts": records}))


class SourcePipelineTest(unittest.TestCase):
    def test_retained_edits_complete_step_and_match_independent_import(self):
        result = subprocess.run(
            [sys.executable, "-m", "tests.python.packages.cadgen.document.test_source_pipeline", "--probe"],
            env={**os.environ, "CADGEN_DAEMON": "0", "CADGEN_OP_MEMO": "0"},
            capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(0, result.returncode, result.stdout[-3000:] + result.stderr[-9000:])
        report = json.loads(result.stdout.splitlines()[-1])
        self.assertTrue(report["ok"])
        self.assertEqual(5, len(report["attempts"]))


if __name__ == "__main__":
    if "--probe" in sys.argv:
        _probe()
    else:
        unittest.main()
