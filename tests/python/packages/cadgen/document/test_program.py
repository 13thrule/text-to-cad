"""New source-to-STEP execution must not enter the previous result pipeline."""
from __future__ import annotations

from contextlib import ExitStack
import gc
from pathlib import Path
import unittest
from unittest.mock import patch
import weakref

from cadgen._document.service import DocumentService
from cadgen._document.program import UnsupportedProgram, current_program
from tests.python.support.tmp_root import generated_cad_directory


SOURCE = '''from pathlib import Path
from cadgen import build123d as bd, step
RADIUS = {radius}
SHIFT = {shift}
COUNT = {count}
@step
def model():
    counter = Path(__file__).with_suffix('.runs')
    counter.write_text(counter.read_text() + 'run\\n' if counter.exists() else 'run\\n')
    shape = bd.Box(30, 20, 6) - bd.Cylinder(RADIUS, 10)
    if COUNT == 1:
        return shape
    parts = []
    for i in range(COUNT):
        part = bd.Pos((i % 6) * 40, (i // 6) * 30 + SHIFT, 0) * shape
        part.label = 'plate-' + str(i)
        parts.append(part)
    return bd.Compound(children=parts, label='assembly')
if __name__ == '__main__':
    model()
'''


class ProgramTests(unittest.TestCase):
    def setUp(self):
        from cadgen._internal import op_memo
        installed = op_memo._installed
        if installed:
            op_memo.uninstall()
        self.addCleanup(op_memo.install if installed else lambda: None)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(generated_cad_directory(prefix="document-program-"))).resolve()
        self.source = self.root / "model.py"
        self.service = DocumentService()

    def write(self, radius=2, shift=0, count=1):
        self.source.write_text(SOURCE.format(radius=radius, shift=shift, count=count), encoding="utf-8")

    def test_replays_python_and_reuses_geometry_and_verified_step_bytes(self):
        self.write()
        with patch("cadgen._internal.generation._generate_step_outputs", side_effect=AssertionError("old pipeline")), \
             patch("cadgen.step_export.build_build123d_step_scene", side_effect=AssertionError("old scene")), \
             patch("cadgen.store.build.build_tree_from_compound", side_effect=AssertionError("old store")):
            first = self.service.generate(self.source)
            payload = self.source.with_suffix(".step").read_bytes()
            second = self.service.generate(self.source)
        self.assertEqual(payload, self.source.with_suffix(".step").read_bytes())
        self.assertEqual("run\nrun\n", self.source.with_suffix(".runs").read_text())
        self.assertEqual("exports_complete", self.service.last_attempt.state)
        self.assertEqual(0, self.service.last_attempt.stats.computed)
        self.assertEqual(1, second.product_metrics.reused)
        self.assertEqual(0, second.product_metrics.prototype_copies)
        self.assertEqual("verified-existing", second.outputs[0].action)
        self.assertIs(first.document, second.document)
        self.assertNotEqual(first.revision_id, second.revision_id)
        self.assertEqual(self.source, second.inputs[0].path)

    def test_geometry_and_placement_edits_saved_file_matches_revision(self):
        from build123d import import_step
        self.write(count=24)
        first = self.service.generate(self.source)
        original = import_step(self.source.with_suffix(".step"))
        self.write(count=24, shift=7)
        placed = self.service.generate(self.source)
        shifted = import_step(self.source.with_suffix(".step"))
        self.assertEqual(24, len(shifted.solids()))
        self.assertTrue(shifted.is_valid)
        self.assertAlmostEqual(original.volume, shifted.volume, places=6)
        self.assertAlmostEqual(7, shifted.bounding_box().min.Y - original.bounding_box().min.Y, places=6)
        self.assertEqual(0, self.service.last_attempt.stats.computed)
        self.assertEqual(1, placed.product_metrics.prototype_copies)
        self.assertNotEqual(first.outputs[0].sha256, placed.outputs[0].sha256)
        self.write(count=24, shift=7, radius=3)
        edited = self.service.generate(self.source)
        self.assertLess(import_step(self.source.with_suffix(".step")).volume, shifted.volume)
        self.assertNotEqual(placed.outputs[0].sha256, edited.outputs[0].sha256)

    def test_restores_deleted_and_modified_outputs_with_fresh_receipts(self):
        self.write()
        first = self.service.generate(self.source)
        destination = self.source.with_suffix(".step")
        destination.unlink()
        restored = self.service.generate(self.source)
        self.assertEqual(first.outputs[0].sha256, restored.outputs[0].sha256)
        self.assertEqual("written", restored.outputs[0].action)
        destination.write_bytes(b"external edit")
        replaced = self.service.generate(self.source)
        self.assertEqual(first.outputs[0].sha256, replaced.outputs[0].sha256)
        self.assertEqual("exports_complete", self.service.last_attempt.state)

    def test_deleted_definition_cannot_come_from_old_registry(self):
        self.write()
        self.service.generate(self.source, "model")
        self.source.write_text("from cadgen import step\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not declare"):
            self.service.generate(self.source, "model")
        self.assertEqual("failed", self.service.last_attempt.state)
        self.assertIsNone(current_program())

    def test_unimplemented_declarations_never_use_old_runtime(self):
        self.source.write_text('''from cadgen import step, glb, build123d as bd
@glb
@step
def model():
    raise AssertionError('body must not run')
''', encoding="utf-8")
        with self.assertRaisesRegex(UnsupportedProgram, "STEP-only"):
            self.service.generate(self.source)
        self.assertEqual("failed", self.service.last_attempt.state)
        self.assertIsNone(current_program())

    def test_children_share_native_execution_replay_bodies_and_finish_discarded_calls(self):
        from build123d import import_step
        self.source.write_text('''from pathlib import Path
from cadgen import step, build123d as bd
@step(out='child.step')
def child():
    counter = Path(__file__).with_suffix('.calls')
    counter.write_text(counter.read_text() + 'run\\n' if counter.exists() else 'run\\n')
    return bd.Box(3, 4, 5)
@step(out='model.step')
def model():
    first = child()
    child()  # Still owes its declared output and ordinary Python effects.
    second = child().moved(bd.Pos(10, 0, 0))
    return bd.Compound(children=[first, second], label='parent')
''', encoding="utf-8")
        with patch("cadgen.authoring._compose_child", side_effect=AssertionError("old child runtime")):
            result = self.service.generate(self.source, "model")
            first_bytes = (self.root / "model.step").read_bytes()
            repeated = self.service.generate(self.source, "model")
        self.assertEqual(4, len(result.outputs))
        self.assertEqual(4, len(repeated.outputs))
        self.assertEqual(6, len(self.source.with_suffix(".calls").read_text().splitlines()))
        self.assertEqual(first_bytes, (self.root / "model.step").read_bytes())
        self.assertEqual(0, self.service.last_attempt.stats.computed)
        self.assertEqual(2, len(import_step(self.root / "model.step").solids()))
        self.assertAlmostEqual(60, import_step(self.root / "child.step").volume)

    def test_completed_grandchild_survives_parent_failure(self):
        self.source.write_text('''from cadgen import step, build123d as bd
@step(out='grandchild.step')
def grandchild():
    return bd.Box(3, 4, 5)
@step(out='child.step')
def child():
    grandchild()
    raise ValueError('child body failed')
@step(out='model.step')
def model():
    return child()
''', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "child body failed"):
            self.service.generate(self.source, "model")
        self.assertTrue((self.root / "grandchild.step").is_file())
        self.assertFalse((self.root / "child.step").exists())
        self.assertFalse((self.root / "model.step").exists())
        self.assertEqual("failed", self.service.last_attempt.state)
        document = self.service.last_attempt.document
        grandchild = document.entry_head(f"{self.source}::grandchild")
        self.assertIsNotNone(grandchild)
        self.assertEqual("exports_complete", document.state(grandchild.revision_id).value)

    def test_caught_child_failure_cannot_claim_successful_declared_build(self):
        self.source.write_text('''from cadgen import step, build123d as bd
@step(out='child.step')
def child():
    raise ValueError('child failed')
@step(out='model.step')
def model():
    try:
        child()
    except ValueError:
        pass
    return bd.Box(3, 4, 5)
''', encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "child model did not complete"):
            self.service.generate(self.source, "model")
        self.assertFalse((self.root / "model.step").exists())

    def test_recursive_child_is_reported_without_native_nested_sessions(self):
        self.source.write_text('''from cadgen import step
@step
def model():
    return model()
''', encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "recursive document model"):
            self.service.generate(self.source, "model")

    def test_publication_failure_keeps_previous_output_and_failed_build(self):
        self.write()
        self.service.generate(self.source)
        old = self.source.with_suffix(".step").read_bytes()
        self.write(radius=3)
        with patch("cadgen._document.step_product.StepProductSession.publish", side_effect=OSError("disk failed")), \
             self.assertRaisesRegex(OSError, "disk failed"):
            self.service.generate(self.source)
        self.assertEqual(old, self.source.with_suffix(".step").read_bytes())
        self.assertEqual("failed", self.service.last_attempt.state)
        self.assertEqual("failed", self.service.last_attempt.document.state(self.service.last_attempt.revision.revision_id).value)

    def shared_destination_source(self, *, external_gap=False):
        self.source.write_text('''from pathlib import Path
from cadgen import step, build123d as bd
@step(out='shared.step')
def grandchild():
    return bd.Box(2, 3, 4)
@step(out='shared.step')
def child():
    grandchild()
    return bd.Box(4, 5, 6)
@step(out='shared.step')
def model():
''' + ("    Path(__file__).with_name('shared.step').write_bytes(b'external edit')\n" if external_gap else "") + '''    child()
    return bd.Box(6, 7, 8)
''', encoding="utf-8")

    def test_grandchild_child_parent_share_destination_through_verified_receipt_chain(self):
        from build123d import import_step
        self.shared_destination_source()
        previous = None
        for _ in range(2):
            result = self.service.generate(self.source, "model")
            self.assertEqual(3, len(result.outputs))
            for receipt in result.outputs:
                self.assertEqual(previous, receipt.previous_sha256)
                previous = receipt.sha256
            self.assertAlmostEqual(336, import_step(self.root / "shared.step").volume)
            request = self.service.last_request
            self.assertEqual("exports_complete", request.state.value)
            self.assertEqual((2, 1, 0), tuple(receipt.sequence for receipt in request.receipts))
            self.assertEqual((1, 2, 3), tuple(receipt.publication_sequence for receipt in request.receipts))
            self.assertEqual((0, 1, 2), request.completed_invocations)
            self.assertTrue(all(receipt.ticket == request.request.ticket for receipt in request.receipts))
            self.assertEqual(tuple(receipt.sha256 for receipt in result.outputs),
                             tuple(receipt.digest for receipt in request.receipts))

    def test_external_gap_cannot_be_adopted_as_an_authorized_child_publication(self):
        from cadgen._document.core import ExportConflict
        from build123d import import_step
        self.shared_destination_source(external_gap=True)
        with self.assertRaisesRegex(ExportConflict, "outside this family's verified publications"):
            self.service.generate(self.source, "model")
        # Both children completed against their own prior bytes. The parent
        # rejects the noncontiguous chain from its earlier expected destination.
        self.assertAlmostEqual(120, import_step(self.root / "shared.step").volume)
        request = self.service.last_request
        self.assertEqual("failed", request.state.value)
        self.assertEqual((2, 1), tuple(receipt.sequence for receipt in request.receipts))
        self.assertEqual((1, 2), request.completed_invocations)
        self.assertFalse(request.exports_complete)
        self.assertEqual("failed", self.service.last_attempt.state)
        self.assertIn("verified publications", self.service.last_attempt.error)

    def test_entry_executes_accepted_bytes_without_a_second_disk_read(self):
        from cadgen._document.sources import CapturedInput
        from build123d import import_step
        self.source.write_text('''from cadgen import step, build123d as bd
@step
def model():
    return bd.Box(2, 3, 4)
''', encoding="utf-8")
        original_read = CapturedInput.read
        captured_reads = []
        def read_once(path):
            captured = original_read(path)
            captured_reads.append(captured)
            if captured.path == self.source:
                self.source.write_text("raise AssertionError('later disk revision executed')\n", encoding="utf-8")
            return captured
        with patch.object(CapturedInput, "read", side_effect=read_once):
            result = self.service.generate(self.source, "model")
        self.assertEqual(1, len(captured_reads))
        self.assertEqual(captured_reads[0], result.inputs[0])
        self.assertEqual(captured_reads[0], self.service.last_request.request.source)
        self.assertEqual(captured_reads[0], self.service.last_attempt.source)
        self.assertAlmostEqual(24, import_step(self.root / "model.step").volume)

    def test_pull_failure_cancels_and_forgets_only_its_accepted_request(self):
        self.write()
        with patch.object(self.service.coordinator, "pull", side_effect=OSError("dispatch failed")):
            with self.assertRaisesRegex(OSError, "dispatch failed"):
                self.service.generate(self.source)
        self.assertEqual("cancelled", self.service.last_request.state.value)
        self.assertTrue(self.service.last_request.finished)
        self.assertEqual((0, 0, 0), self.service.coordinator.admission.used)
        with self.assertRaises(KeyError):
            self.service.coordinator.snapshot(self.service.last_request.request.ticket)
        self.assertFalse(self.source.with_suffix(".runs").exists())

    def test_dispatch_error_does_not_mark_the_previous_completed_attempt_failed(self):
        self.write()
        self.service.generate(self.source)
        previous = self.service.last_attempt
        with patch.object(self.service.coordinator, "pull", side_effect=OSError("dispatch failed")):
            with self.assertRaisesRegex(OSError, "dispatch failed"):
                self.service.generate(self.source)
        self.assertIs(previous, self.service.last_attempt)
        self.assertEqual("exports_complete", previous.state)
        self.assertIsNone(previous.error)
        self.assertEqual("cancelled", self.service.last_request.state.value)

    def test_synchronous_generate_does_not_steal_an_older_queued_family_request(self):
        from cadgen._document.resources import AdmissionDenied
        from cadgen._document.sources import CapturedInput
        self.write()
        coordinator = self.service.coordinator
        captured = CapturedInput.read(self.source)
        older = coordinator.accept(str(self.source), "older", captured, "older-function")
        with self.assertRaises(AdmissionDenied):
            self.service.generate(self.source, "model")
        self.assertEqual("queued", coordinator.snapshot(older.ticket).state.value)
        self.assertEqual("cancelled", self.service.last_request.state.value)
        self.assertFalse(self.source.with_suffix(".runs").exists())
        self.assertEqual((0, 0, 0), coordinator.admission.used)
        coordinator.cancel(older.ticket)
        coordinator.forget(older.ticket)

    def test_later_claim_after_step_completion_marks_attempt_failed_with_error(self):
        from cadgen._document import Document
        from cadgen._document.scheduler import PublicationConflict
        from cadgen._document.service import current_attempt
        self.write()
        original_collect = Document.collect
        later = []
        def collect(document, *, keep_revisions):
            attempt = current_attempt()
            later.append(self.service.coordinator.accept(
                "different-family", "later", attempt.source, "later",
                outputs=(self.source.with_suffix(".step"),)))
            return original_collect(document, keep_revisions=keep_revisions)
        with patch.object(Document, "collect", collect):
            with self.assertRaises(PublicationConflict):
                self.service.generate(self.source)
        attempt = self.service.last_attempt
        self.assertEqual("failed", attempt.state)
        self.assertIn("later accepted", attempt.error)
        self.assertEqual("failed", self.service.last_request.state.value)
        self.assertEqual(1, len(self.service.last_request.receipts))
        self.assertEqual("failed", attempt.document.state(attempt.revision.revision_id).value)
        self.assertIsNot(attempt.job.admission, attempt.document.admission)
        self.assertEqual((0, 0, 0), self.service.coordinator.admission.used)
        self.service.coordinator.cancel(later[0].ticket)
        self.service.coordinator.forget(later[0].ticket)

    def test_collection_failure_after_export_restores_admission_and_records_failure(self):
        from cadgen._document import Document
        self.write()
        with patch.object(Document, "collect", side_effect=OSError("collection failed")):
            with self.assertRaisesRegex(OSError, "collection failed"):
                self.service.generate(self.source)
        attempt = self.service.last_attempt
        self.assertEqual("failed", attempt.state)
        self.assertEqual("collection failed", attempt.error)
        self.assertIsNot(attempt.job.admission, attempt.document.admission)
        self.assertEqual("failed", self.service.last_request.state.value)
        self.assertEqual(1, len(self.service.last_request.receipts))
        self.assertEqual((0, 0, 0), self.service.coordinator.admission.used)

    def test_registry_restores_owned_definitions_and_keeps_unrelated_changes(self):
        from cadgen import authoring
        from cadgen._document import program
        registry = authoring._REGISTRY
        before = dict(registry)
        def declare(path, name):
            namespace = {"__file__": str(path)}
            exec(compile(f"from cadgen import step\n@step\ndef {name}():\n    return None\n", str(path), "exec"), namespace)
            return namespace[name].__cadgen_model__
        own = declare(self.source, "model")
        deleted = declare(self.source, "deleted")
        unrelated_path = self.root.parent / (self.root.name + "-outside.py")
        unrelated = declare(unrelated_path, "unrelated")
        added = declare(unrelated_path, "added")
        registry.pop(added.ref)
        replacement = declare(unrelated_path, "unrelated")
        registry[unrelated.ref] = unrelated
        self.source.write_text('''from cadgen import step, build123d as bd
@step
def transient():
    return bd.Box(1, 2, 3)
@step
def model():
    return bd.Box(2, 3, 4)
''', encoding="utf-8")
        selected = program._definition
        def choose(*args):
            registry[unrelated.ref] = replacement
            registry[added.ref] = added
            return selected(*args)
        touched = (own.ref, deleted.ref, unrelated.ref, added.ref, f"{self.source}::transient")
        try:
            with patch.object(program, "_definition", side_effect=choose):
                self.service.generate(self.source, "model")
            self.assertIs(own, registry[own.ref])
            self.assertIs(deleted, registry[deleted.ref])
            self.assertIs(replacement, registry[unrelated.ref])
            self.assertIs(added, registry[added.ref])
            self.assertNotIn(f"{self.source}::transient", registry)
        finally:
            for key in touched:
                if key in before:
                    registry[key] = before[key]
                else:
                    registry.pop(key, None)

    def test_registry_releases_captured_helper_namespaces_after_execution(self):
        from cadgen import authoring
        from cadgen._document import program
        helper = self.root / "captured_child.py"
        helper.write_text('''from cadgen import step, build123d as bd
@step(out='child.step')
def child():
    return bd.Box(2, 3, 4)
''', encoding="utf-8")
        self.source.write_text('''from captured_child import child
from cadgen import step
@step(out='model.step')
def model():
    return child()
''', encoding="utf-8")
        references = []
        original = program._definition
        def selected(*args):
            references.extend(weakref.ref(definition.func)
                              for definition in authoring._REGISTRY.values()
                              if definition.script_path in (self.source, helper))
            return original(*args)
        with patch.object(program, "_definition", side_effect=selected):
            self.service.generate(self.source, "model")
        self.assertEqual(2, len(references))
        self.assertNotIn(f"{self.source}::model", authoring._REGISTRY)
        self.assertNotIn(f"{helper}::child", authoring._REGISTRY)
        gc.collect()
        self.assertTrue(all(reference() is None for reference in references))

    def test_registry_is_cleaned_when_captured_module_execution_fails(self):
        from cadgen import authoring
        self.source.write_text('''from cadgen import step
@step
def partial():
    return None
raise ValueError('module execution failed')
''', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "module execution failed"):
            self.service.generate(self.source)
        self.assertNotIn(f"{self.source}::partial", authoring._REGISTRY)
        self.assertEqual("failed", self.service.last_attempt.state)
        self.assertEqual("failed", self.service.last_request.state.value)
        self.assertIsNone(current_program())


if __name__ == "__main__":
    unittest.main()
