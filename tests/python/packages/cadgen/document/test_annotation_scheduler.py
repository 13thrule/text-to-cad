"""One publication group checks every output claim and records absence facts."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from cadgen._document.resources import ResourceAdmission
from cadgen._document.scheduler import Coordinator, PublicationConflict, RequestStateError
from cadgen._document.sources import CapturedInput


class AnnotationSchedulerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="annotation-scheduler-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        payload = b"captured source"
        self.source = CapturedInput(self.root / "model.py", payload, hashlib.sha256(payload).hexdigest())
        self.paths = (self.root / "artifact.bin", self.root / "artifact.bin.json")

    def test_group_owns_two_outputs_and_records_absence(self):
        coordinator = Coordinator()
        request = coordinator.accept("family", "model", self.source, "model", outputs=self.paths)
        with coordinator.pull("family") as job:
            job.geometry_ready("revision")
            with job.publications(self.paths) as publications:
                self.assertEqual(self.paths, tuple(value.path for value in publications))
                self.paths[0].write_bytes(b"saved")
                publications[0].acknowledge(hashlib.sha256(b"saved").hexdigest())
                publications[1].acknowledge(None)
        facts = coordinator.snapshot(request.ticket)
        self.assertTrue(facts.exports_complete)
        self.assertEqual(2, len(facts.receipts))
        self.assertIsNone(facts.receipts[1].digest)
        self.assertFalse(self.paths[1].exists())

    def test_later_claim_to_second_output_refuses_group_before_any_write(self):
        coordinator = Coordinator(admission=ResourceAdmission(cpu_slots=2))
        request = coordinator.accept("old", "model", self.source, "model", outputs=self.paths)
        old = coordinator.pull("old")
        newer = coordinator.accept("new", "model", self.source, "model", outputs=(self.paths[1],))
        with self.assertRaises(PublicationConflict), old:
            old.geometry_ready("revision")
            with old.publications(self.paths):
                self.fail("a stale group acquired only its first claim")
        self.assertEqual((), coordinator.snapshot(request.ticket).receipts)
        self.assertFalse(self.paths[0].exists())
        coordinator.cancel(newer.ticket)

    def test_second_output_failure_preserves_first_receipt(self):
        coordinator = Coordinator()
        request = coordinator.accept("family", "model", self.source, "model", outputs=self.paths)
        with self.assertRaisesRegex(OSError, "second output"):
            with coordinator.pull("family") as job:
                job.geometry_ready("revision")
                with job.publications(self.paths) as publications:
                    self.paths[0].write_bytes(b"saved")
                    publications[0].acknowledge(hashlib.sha256(b"saved").hexdigest())
                    raise OSError("second output")
        facts = coordinator.snapshot(request.ticket)
        self.assertFalse(facts.exports_complete)
        self.assertEqual("failed", facts.state.value)
        self.assertEqual(1, len(facts.receipts))

    def test_group_requires_every_acknowledgement(self):
        coordinator = Coordinator()
        request = coordinator.accept("family", "model", self.source, "model", outputs=self.paths)
        with self.assertRaisesRegex(RequestStateError, "acknowledge"):
            with coordinator.pull("family") as job:
                job.geometry_ready("revision")
                with job.publications(self.paths) as publications:
                    publications[0].acknowledge(None)
        self.assertFalse(coordinator.snapshot(request.ticket).exports_complete)
