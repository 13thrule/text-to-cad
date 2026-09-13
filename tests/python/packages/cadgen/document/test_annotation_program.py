"""STEP and its sole annotation companion finish as explicit paired outputs."""
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from cadgen._document.annotations import companion_path
from cadgen._document.service import DocumentService
from cadgen._document.sources import CapturedInput
from tests.python.support.tmp_root import generated_cad_directory


SOURCE = '''from cadgen import step, build123d as bd
@step
def model():
    base = bd.Box({length}, 3, 4)
    base.cad_material = {pbr}
    base.material = {material!r}
    other = bd.Pos(10, 0, 0) * base
    other.cad_material = {{'metalness': .7}}
    root = bd.Compound(children=[base, other], label='assembly')
    root.cad_material = {{'opacity': .8}}
    return bd.Pos(20, 0, 0) * root
'''


class AnnotationProgramTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(
            generated_cad_directory(prefix="document-annotation-program-"))).resolve()
        self.source = self.directory / "model.py"
        self.step_path = self.source.with_suffix(".step")
        self.annotation_path = companion_path(self.step_path)
        self.service = DocumentService()

    def write(self, *, roughness=.2, material="steel", length=2, located=True, after_placement=False):
        source = SOURCE if located else SOURCE.replace("return bd.Pos(20, 0, 0) * root", "return root")
        if after_placement:
            source = source.replace("    base.cad_material = {pbr}\n    base.material = {material!r}\n", "")
            source = source.replace("    other.cad_material =", "    base.cad_material = {pbr}\n"
                "    base.material = {material!r}\n    other.material = {material!r}\n    other.cad_material =")
        self.source.write_text(source.format(length=length,
            pbr=repr({"roughness": roughness}), material=material))

    def test_appearance_only_edit_reuses_step_and_finishes_both_outputs(self):
        self.write(located=False, after_placement=True)
        first = self.service.generate(self.source)
        native = self.step_path.read_bytes()
        previous = self.annotation_path.read_bytes()
        self.write(roughness=.6, material="paint", located=False, after_placement=True)
        second = self.service.generate(self.source)
        self.assertEqual(native, self.step_path.read_bytes())
        self.assertNotEqual(previous, self.annotation_path.read_bytes())
        self.assertEqual(0, self.service.last_attempt.stats.computed)
        self.assertEqual(1, second.product_metrics.reused)
        self.assertEqual(2, len(second.outputs))
        self.assertEqual((str(self.step_path), str(self.annotation_path)),
                         tuple(receipt.destination for receipt in second.outputs))
        self.assertEqual("verified-existing", second.outputs[0].action)
        self.assertEqual("exports_complete", self.service.last_request.state.value)
        self.assertEqual(2, len(self.service.last_request.receipts))
        value = json.loads(self.annotation_path.read_bytes())
        self.assertEqual(first.outputs[0].sha256, value["step"]["sha256"])
        self.assertEqual([1, 1], value["occurrences"][0]["path"])
        self.assertEqual({"roughness": .6, "opacity": .8}, value["occurrences"][0]["pbr"])
        self.assertEqual("paint", value["occurrences"][0]["material"])

    def test_located_assembly_reuses_step_and_preserves_actual_saved_paths(self):
        self.write()
        self.service.generate(self.source)
        native = self.step_path.read_bytes()
        self.write(roughness=.6)
        result = self.service.generate(self.source)
        self.assertEqual(0, self.service.last_attempt.stats.computed)
        self.assertEqual(1, result.product_metrics.reused)
        self.assertEqual(native, self.step_path.read_bytes())
        value = json.loads(self.annotation_path.read_bytes())
        self.assertEqual([1, 1, 1], value["occurrences"][0]["path"])
        self.assertEqual(.6, value["occurrences"][0]["pbr"]["roughness"])

    def test_pbr_before_leaf_placement_reuses_step_and_preserves_saved_values(self):
        self.write(located=False)
        self.service.generate(self.source)
        native = self.step_path.read_bytes()
        self.write(roughness=.6, located=False)
        result = self.service.generate(self.source)
        self.assertEqual(0, self.service.last_attempt.stats.computed)
        self.assertEqual(1, result.product_metrics.reused)
        self.assertEqual(native, self.step_path.read_bytes())
        saved = self.service.load_step(CapturedInput.read(self.step_path), work_directory=self.directory)
        root = saved.document._revisions[saved.revision_id].root
        self.assertEqual(.6, root.children[0].appearance["pbr"]["roughness"])
        self.assertEqual("steel", root.children[0].appearance["material"])

    def test_warm_matching_pair_publishes_without_temporary_staging(self):
        self.write(located=False, after_placement=True)
        self.service.generate(self.source)
        with patch("cadgen._document.step_product.tempfile.NamedTemporaryFile",
                   side_effect=AssertionError("unchanged output was staged")):
            repeated = self.service.generate(self.source)
        self.assertEqual(("verified-existing", "verified-existing"),
                         tuple(receipt.action for receipt in repeated.outputs))
        self.assertEqual(0, repeated.product_metrics.writes)
        self.assertEqual(0, repeated.product_metrics.annotation_writes)
        self.assertEqual(2, len(self.service.last_request.receipts))

    def test_unstaged_pair_drift_is_rejected_before_any_receipt(self):
        from contextlib import contextmanager
        from cadgen._document.core import ExportConflict
        from cadgen._document.step_product import StepProductSession
        self.write(located=False, after_placement=True)
        self.service.generate(self.source)
        original = StepProductSession.stage_outputs
        @contextmanager
        def drift(session, destinations):
            with original(session, destinations) as staged:
                self.assertIsNone(staged[0].staged_path)
                self.assertIsNone(staged[1].staged_path)
                self.step_path.write_bytes(b"external replacement after preparation")
                yield staged
        with patch.object(StepProductSession, "stage_outputs", drift):
            with self.assertRaises(ExportConflict):
                self.service.generate(self.source)
        self.assertEqual((), self.service.last_request.receipts)
        self.assertEqual("failed", self.service.last_request.state.value)
        self.assertEqual(b"external replacement after preparation", self.step_path.read_bytes())

    def test_removing_metadata_deletes_stale_companion_and_attests_absence(self):
        self.write()
        self.service.generate(self.source)
        self.source.write_text("from cadgen import step, build123d as bd\n"
                               "@step\ndef model():\n    return bd.Box(2, 3, 4)\n")
        result = self.service.generate(self.source)
        self.assertFalse(self.annotation_path.exists())
        self.assertEqual("deleted", result.outputs[1].action)
        self.assertIsNone(result.outputs[1].sha256)
        self.assertIsNone(self.service.last_request.receipts[1].digest)
        repeated = self.service.generate(self.source)
        self.assertEqual("verified-absent", repeated.outputs[1].action)
        self.assertEqual("exports_complete", self.service.last_attempt.state)

    def test_saved_load_uses_captured_companion_and_separate_native_owner(self):
        from cadgen._document.roots import GeometryLeaf, walk_root
        from cadgen._document.step_import import StepImportSession
        self.write()
        source_result = self.service.generate(self.source)
        captured = CapturedInput.read(self.step_path)
        annotations = CapturedInput.read(self.annotation_path)
        self.source.unlink()
        self.annotation_path.write_bytes(b"replaced after capture")
        first = self.service.load_step(captured, annotations=annotations,
                                       work_directory=self.directory)
        self.assertNotEqual(source_result.document.owner_id, first.document.owner_id)
        leaves = [node for _, node in walk_root(first.document._revisions[first.revision_id].root)
                  if type(node) is GeometryLeaf]
        self.assertEqual({"roughness": .2, "opacity": .8}, leaves[0].appearance["pbr"])
        self.assertEqual("steel", leaves[0].appearance["material"])
        with patch.object(StepImportSession, "_parse_capture", side_effect=AssertionError("native reparse")):
            repeated = self.service.load_step(captured, annotations=annotations,
                                              work_directory=self.directory)
            native = self.service.load_step(captured, annotations=None,
                                            work_directory=self.directory)
        self.assertEqual(first.revision_id, repeated.revision_id)
        self.assertIs(first.document, native.document)
        self.assertNotEqual(first.revision_id, native.revision_id)
        native_leaves = [node for _, node in walk_root(native.document._revisions[native.revision_id].root)
                         if type(node) is GeometryLeaf]
        self.assertNotIn("pbr", native_leaves[0].appearance)
        self.assertEqual(leaves[0].geometry, native_leaves[0].geometry)

    def test_sidecar_replacement_during_source_execution_conflicts_before_writes(self):
        from cadgen._document.core import ExportConflict
        self.write()
        self.service.generate(self.source)
        prior_step = self.step_path.read_bytes()
        self.source.write_text("from pathlib import Path\nfrom cadgen import step, build123d as bd\n"
            "@step\ndef model():\n"
            "    Path(__file__).with_suffix('.step.json').write_bytes(b'external replacement')\n"
            "    return bd.Box(5, 3, 4)\n")
        with self.assertRaises(ExportConflict):
            self.service.generate(self.source)
        self.assertEqual(prior_step, self.step_path.read_bytes())
        self.assertEqual(b"external replacement", self.annotation_path.read_bytes())
        self.assertEqual((), self.service.last_request.receipts)
        self.assertEqual("failed", self.service.last_attempt.state)

    def test_second_output_failure_retains_truthful_step_receipt_and_never_success(self):
        import os
        self.write()
        self.service.generate(self.source)
        old_annotations = self.annotation_path.read_bytes()
        self.write(length=5)
        replace_file = os.replace
        def fail_companion(source, destination):
            if Path(destination) == self.annotation_path:
                raise OSError("annotation disk failure")
            return replace_file(source, destination)
        with patch("cadgen._document.step_product.os.replace", side_effect=fail_companion):
            with self.assertRaisesRegex(OSError, "annotation disk failure"):
                self.service.generate(self.source)
        self.assertEqual("failed", self.service.last_attempt.state)
        self.assertEqual("failed", self.service.last_request.state.value)
        self.assertEqual(1, len(self.service.last_request.receipts))
        self.assertEqual(self.step_path, self.service.last_request.receipts[0].path)
        self.assertEqual(old_annotations, self.annotation_path.read_bytes())
        with self.assertRaisesRegex(ValueError, "binding"):
            self.service.load_step(CapturedInput.read(self.step_path), work_directory=self.directory)

    def test_child_companion_failure_cannot_be_hidden_by_parent(self):
        import os
        self.source.write_text("from cadgen import step, build123d as bd\n"
            "@step(out='child.step')\ndef child():\n"
            "    shape = bd.Box(2, 3, 4)\n    shape.cad_material = {'roughness': .2}\n    return shape\n"
            "@step\ndef model():\n    try:\n        child()\n    except OSError:\n        pass\n"
            "    return bd.Box(6, 3, 4)\n")
        replace_file = os.replace
        child_companion = self.directory / "child.step.json"
        def fail_companion(source, destination):
            if Path(destination) == child_companion:
                raise OSError("child annotation failure")
            return replace_file(source, destination)
        with patch("cadgen._document.step_product.os.replace", side_effect=fail_companion):
            with self.assertRaisesRegex(RuntimeError, "child model did not complete"):
                self.service.generate(self.source, "model")
        self.assertTrue((self.directory / "child.step").exists())
        self.assertFalse(self.step_path.exists())
        self.assertEqual("failed", self.service.last_request.state.value)
        self.assertEqual(1, len(self.service.last_request.receipts))

    def test_post_replace_read_failure_keeps_both_completed_effect_receipts(self):
        import os
        from cadgen._document.step_product import destination_digest
        self.write()
        self.service.generate(self.source)
        self.write(roughness=.6)
        replaced = False
        replace_file = os.replace
        def observe_replace(source, destination):
            nonlocal replaced
            result = replace_file(source, destination)
            if Path(destination) == self.annotation_path:
                replaced = True
            return result
        def fail_after_replace(path):
            if replaced and Path(path) == self.annotation_path:
                raise OSError("post-replace read failed")
            return destination_digest(path)
        with patch("cadgen._document.step_product.os.replace", side_effect=observe_replace), \
             patch("cadgen._document.step_product.destination_digest", side_effect=fail_after_replace):
            with self.assertRaisesRegex(OSError, "post-replace read failed"):
                self.service.generate(self.source)
        self.assertTrue(replaced)
        self.assertEqual("failed", self.service.last_request.state.value)
        self.assertEqual(2, len(self.service.last_request.receipts))
        self.assertEqual(.6, json.loads(self.annotation_path.read_bytes())["occurrences"][0]["pbr"]["roughness"])
