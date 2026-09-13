"""Explicit-build lifecycle must not mistake native readiness for saved output."""

from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cadgen._document.service import DocumentService, current_attempt, current_service
from cadgen._document.sources import CapturedInput


class _Document:
    def __init__(self, identity):
        self.identity = identity
        self.exports = []
        self.failed = []

    def complete_exports(self, revision, paths):
        self.exports.append((revision, paths))

    def fail(self, revision):
        self.failed.append(revision)

    def collect(self, *, keep_revisions):
        pass


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.source = Path(self.folder.name) / "part.py"
        self.source.write_text("VALUE = 1\n")
        self.service = DocumentService(max_documents=2, document_factory=_Document)

    def _ready(self, attempt):
        attempt.revision = SimpleNamespace(revision_id="native-1")
        attempt.state = "geometry_ready"

    def test_source_buffer_survives_same_length_edit(self):
        captured = CapturedInput.read(self.source)
        self.source.write_text("VALUE = 2\n")
        self.assertEqual(b"VALUE = 1\n", captured.data)
        self.assertNotEqual(captured.digest, CapturedInput.read(self.source).digest)

    def test_activation_is_scoped_and_exceptions_restore_context(self):
        self.assertIsNone(current_service())
        with self.assertRaisesRegex(ValueError, "stop"):
            with self.service.activate():
                self.assertIs(self.service, current_service())
                with self.assertRaisesRegex(RuntimeError, "already active"):
                    with self.service.activate():
                        pass
                raise ValueError("stop")
        self.assertIsNone(current_service())

    def test_geometry_ready_is_not_success_after_export_failure(self):
        with self.assertRaisesRegex(OSError, "disk full"):
            with self.service.build(CapturedInput.read(self.source), "part") as attempt:
                self._ready(attempt)
                self.assertIs(current_attempt(), attempt)
                raise OSError("disk full")
        self.assertEqual("failed", attempt.state)
        self.assertIsNotNone(attempt.revision)
        self.assertEqual([], attempt.document.exports)
        self.assertEqual(["native-1"], attempt.document.failed)
        self.assertIsNone(current_attempt())

    def test_success_requires_native_revision_and_declared_files(self):
        with self.assertRaisesRegex(RuntimeError, "before document geometry"):
            with self.service.build(CapturedInput.read(self.source), "part"):
                pass
        missing = str(self.source.with_suffix(".step"))
        with self.assertRaisesRegex(RuntimeError, "without declared exports"):
            with self.service.build(CapturedInput.read(self.source), "part", required_exports=(missing,)) as attempt:
                self._ready(attempt)
        self.assertEqual("failed", attempt.state)
        # A non-CAD stand-in exercises lifecycle acknowledgement without
        # creating an exchange artifact outside the model fixture area.
        with self.service.build(CapturedInput.read(self.source), "part", required_exports=(str(self.source),)) as attempt:
            self._ready(attempt)
        self.assertEqual("exports_complete", attempt.state)
        self.assertEqual([("native-1", (str(self.source),))], attempt.document.exports)

    def test_reuses_document_across_source_edits_but_separates_functions(self):
        with self.service.build(CapturedInput.read(self.source), "part") as first:
            self._ready(first)
        self.source.write_text("VALUE = 2\n")
        with self.service.build(CapturedInput.read(self.source), "part") as second:
            self._ready(second)
        self.assertIs(first.document, second.document)
        self.assertNotEqual(first.source.digest, second.source.digest)
        with self.service.build(CapturedInput.read(self.source), "other") as other:
            self._ready(other)
        self.assertIsNot(first.document, other.document)

    def test_registry_evicts_finished_documents_and_rejects_recursion(self):
        service = DocumentService(max_documents=1, document_factory=_Document)
        with service.build(CapturedInput.read(self.source), "part") as first:
            self._ready(first)
            with self.assertRaisesRegex(RuntimeError, "recursive"):
                with service.build(CapturedInput.read(self.source), "part"):
                    pass
            with self.assertRaisesRegex(RuntimeError, "capacity"):
                with service.build(CapturedInput.read(self.source), "other"):
                    pass
            self.assertIs(current_attempt(), first)
        with service.build(CapturedInput.read(self.source), "other") as other:
            self._ready(other)
        self.assertEqual(1, len(service._documents))
        self.assertIsNot(first.document, other.document)

    def test_service_is_thread_affine(self):
        errors = []

        def other_thread():
            try:
                with self.service.activate():
                    pass
            except RuntimeError as error:
                errors.append(str(error))

        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(["native document service must run in its owning thread"], errors)

    def test_collection_failure_marks_late_error_and_restores_admission(self):
        prior = object()
        borrowed = object()
        document = _Document("collection")
        document.admission = prior
        service = DocumentService(document_factory=lambda _identity: document)
        job = SimpleNamespace(admission=borrowed)
        with patch.object(document, "collect", side_effect=OSError("collection failed")):
            with self.assertRaisesRegex(OSError, "collection failed"):
                with service.build(CapturedInput.read(self.source), "part", job=job) as attempt:
                    self.assertIs(borrowed, document.admission)
                    self._ready(attempt)
        self.assertIs(prior, document.admission)
        self.assertEqual("failed", attempt.state)
        self.assertEqual("collection failed", attempt.error)
        self.assertEqual(["native-1"], document.failed)
        self.assertIs(service.last_attempt, attempt)
        self.assertIsNone(current_attempt())
        self.assertEqual(set(), service._active)

    def test_collection_failure_does_not_mask_body_error_or_retain_borrowed_admission(self):
        document = _Document("collection-after-error")
        service = DocumentService(document_factory=lambda _identity: document)
        job = SimpleNamespace(admission=object())
        with patch.object(document, "collect", side_effect=OSError("collection failed")):
            with self.assertRaisesRegex(ValueError, "source failed") as failure:
                with service.build(CapturedInput.read(self.source), "part", job=job) as attempt:
                    self._ready(attempt)
                    raise ValueError("source failed")
        self.assertFalse(hasattr(document, "admission"))
        self.assertEqual("source failed", attempt.error)
        self.assertEqual(["native-1"], document.failed)
        self.assertTrue(any("collection failed" in note for note in failure.exception.__notes__))
        self.assertEqual(set(), service._active)
        self.assertIsNone(current_attempt())


if __name__ == "__main__":
    unittest.main()
