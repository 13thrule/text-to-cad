"""Synthetic owner-process scheduler, receipts and resource contracts."""
from dataclasses import FrozenInstanceError
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from cadgen._document.resources import AdmissionDenied, Cancelled, ResourceAdmission, ResourceRequest
from cadgen._document.scheduler import Coordinator, PublicationConflict, QueueFull, RequestStateError, State
from cadgen._document.sources import CapturedInput


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="document-scheduler-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = CapturedInput(self.root / "model.py", b"captured source", hashlib.sha256(b"captured source").hexdigest())

    def accept(self, coordinator, family="family", document="document", **kwargs):
        return coordinator.accept(family, document, self.source, "part", **kwargs)

    def publish(self, job, path, payload=b"completed output"):
        with job.publication(path) as publication:
            publication.path.write_bytes(payload)
            publication.acknowledge(hashlib.sha256(payload).hexdigest())

    def test_acceptance_captures_values_before_execution_and_separates_facts(self):
        coordinator = Coordinator()
        paths = [self.root / "artifact.bin"]
        request = self.accept(coordinator, outputs=paths)
        paths.clear()
        self.source.path.write_bytes(b"later source edit")
        self.assertEqual(1, request.ticket)
        self.assertEqual(b"captured source", request.source.data)
        self.assertEqual((self.root / "artifact.bin",), request.outputs)
        with self.assertRaises(FrozenInstanceError):
            request.function = "changed"
        self.assertEqual(State.QUEUED, coordinator.snapshot(request.ticket).state)
        with coordinator.pull("family") as job:
            self.assertEqual(State.RUNNING, coordinator.snapshot(request.ticket).state)
            job.geometry_ready("revision-1")
            facts = coordinator.snapshot(request.ticket)
            self.assertEqual(State.GEOMETRY_READY, facts.state)
            self.assertFalse(facts.exports_complete)
            self.assertFalse(facts.finished)
            self.publish(job, request.outputs[0])
        facts = coordinator.snapshot(request.ticket)
        self.assertEqual(State.EXPORTS_COMPLETE, facts.state)
        self.assertTrue(facts.exports_complete)
        self.assertEqual("revision-1", facts.geometry_id)
        self.assertEqual((0,), facts.completed_invocations)

    def test_only_queued_previews_coalesce_and_explicit_jobs_remain_fifo(self):
        coordinator = Coordinator()
        first = self.accept(coordinator, preview=True)
        running = coordinator.pull("family")
        second = self.accept(coordinator, preview=True)
        explicit = self.accept(coordinator)
        third = self.accept(coordinator, preview=True)
        self.assertEqual(State.RUNNING, coordinator.snapshot(first.ticket).state)
        self.assertEqual(State.SUPERSEDED, coordinator.snapshot(second.ticket).state)
        self.assertEqual(State.QUEUED, coordinator.snapshot(explicit.ticket).state)
        self.assertIsNone(coordinator.pull("family"))
        with running:
            running.geometry_ready("preview")
        self.assertEqual(State.GEOMETRY_READY, coordinator.snapshot(first.ticket).state)
        self.assertTrue(coordinator.snapshot(first.ticket).finished)
        for request in (explicit, third):
            with coordinator.pull("family") as job:
                self.assertIs(job.request, request)
                job.geometry_ready("revision")

    def test_cross_family_reordered_completion_cannot_overwrite_newer_claim(self):
        coordinator = Coordinator(admission=ResourceAdmission(cpu_slots=2))
        path = self.root / "shared.bin"
        old = self.accept(coordinator, "slow", outputs=(path,))
        slow = coordinator.pull("slow")
        new = self.accept(coordinator, "fast", outputs=(path.parent / "unused" / ".." / path.name,))
        with coordinator.pull("fast") as fast:
            fast.geometry_ready("new")
            self.publish(fast, path, b"new")
        with self.assertRaises(PublicationConflict):
            with slow:
                slow.geometry_ready("old")
                self.publish(slow, path, b"old")
        self.assertEqual(b"new", path.read_bytes())
        self.assertEqual(State.FAILED, coordinator.snapshot(old.ticket).state)
        self.assertFalse(coordinator.snapshot(old.ticket).exports_complete)
        self.assertEqual(State.EXPORTS_COMPLETE, coordinator.snapshot(new.ticket).state)
        self.assertEqual((0, 0, 0), coordinator.admission.used)

    def test_exact_dispatch_does_not_steal_or_reorder_queued_work(self):
        coordinator = Coordinator()
        first = self.accept(coordinator)
        second = self.accept(coordinator)
        self.assertIsNone(coordinator.pull("family", ticket=second.ticket))
        self.assertEqual(State.QUEUED, coordinator.snapshot(first.ticket).state)
        self.assertEqual(State.QUEUED, coordinator.snapshot(second.ticket).state)
        self.assertEqual((0, 0, 0), coordinator.admission.used)
        for request in (first, second):
            with coordinator.pull("family", ticket=request.ticket) as job:
                self.assertIs(job.request, request)
                job.geometry_ready("revision")
        self.assertIsNone(coordinator.pull("family", ticket=second.ticket))
        for invalid in (True, 0, -1, "1"):
            with self.assertRaises(ValueError):
                coordinator.pull("family", ticket=invalid)

    def test_late_output_binding_retains_original_acceptance_ticket(self):
        coordinator = Coordinator(admission=ResourceAdmission(cpu_slots=2))
        old = self.accept(coordinator, "slow")
        slow = coordinator.pull("slow")
        path = self.root / "late.bin"
        new = self.accept(coordinator, "fast", outputs=(path,))
        with self.assertRaises(PublicationConflict):
            with slow:
                slow.bind_outputs((path,))
        self.assertEqual(((0, path),), coordinator.snapshot(old.ticket).required_outputs)
        with coordinator.pull("fast") as fast:
            fast.geometry_ready("new")
            self.publish(fast, path)
        self.assertGreater(new.ticket, old.ticket)

    def test_cancelled_newer_request_does_not_restore_older_path_claim(self):
        coordinator = Coordinator()
        path = self.root / "claimed.bin"
        old = self.accept(coordinator, outputs=(path,))
        new = self.accept(coordinator, outputs=(path,))
        coordinator.cancel(new.ticket)
        coordinator.forget(new.ticket)
        with self.assertRaises(PublicationConflict):
            with coordinator.pull("family") as job:
                job.geometry_ready("old")
                self.publish(job, path)
        self.assertEqual(State.FAILED, coordinator.snapshot(old.ticket).state)

    def test_preview_publication_conflict_is_superseded_not_export_success(self):
        coordinator = Coordinator()
        path = self.root / "preview.bin"
        old = self.accept(coordinator, outputs=(path,), preview=True)
        running = coordinator.pull("family")
        newer = self.accept(coordinator, outputs=(path,))
        with self.assertRaises(PublicationConflict):
            with running:
                running.geometry_ready("old")
                self.publish(running, path)
        self.assertEqual(State.SUPERSEDED, coordinator.snapshot(old.ticket).state)
        self.assertEqual(State.QUEUED, coordinator.snapshot(newer.ticket).state)

    def test_cancellation_before_and_during_publication_keeps_receipts_honest(self):
        for during in (False, True):
            with self.subTest(during=during):
                coordinator = Coordinator()
                path = self.root / f"cancel-{during}.bin"
                request = self.accept(coordinator, outputs=(path,))
                with self.assertRaises(Cancelled):
                    with coordinator.pull("family") as job:
                        job.geometry_ready("ready")
                        if not during:
                            coordinator.cancel(request.ticket)
                        with job.publication(path) as publication:
                            publication.path.write_bytes(b"written")
                            job.cancellation.set()
                            publication.acknowledge(hashlib.sha256(b"written").hexdigest())
                facts = coordinator.snapshot(request.ticket)
                self.assertEqual(State.CANCELLED, facts.state)
                self.assertEqual("ready", facts.geometry_id)
                self.assertFalse(facts.exports_complete)
                self.assertEqual(int(during), len(facts.receipts))
                self.assertEqual(during, path.exists())
                self.assertEqual((0, 0, 0), coordinator.admission.used)

    def test_cancel_before_entering_dispatch_scope_releases_resources(self):
        coordinator = Coordinator()
        request = self.accept(coordinator)
        job = coordinator.pull("family")
        coordinator.cancel(request.ticket)
        with self.assertRaises(Cancelled):
            with job:
                self.fail("cancelled source must not run")
        self.assertEqual((0, 0, 0), coordinator.admission.used)
        self.assertEqual(State.CANCELLED, coordinator.snapshot(request.ticket).state)

    def test_missing_acknowledgement_and_missing_explicit_output_fail(self):
        for scope in (False, True):
            coordinator = Coordinator()
            path = self.root / "missing.bin"
            request = self.accept(coordinator, outputs=(path,))
            with self.assertRaises(RequestStateError):
                with coordinator.pull("family") as job:
                    job.geometry_ready("ready")
                    if scope:
                        with job.publication(path):
                            pass
            facts = coordinator.snapshot(request.ticket)
            self.assertEqual(State.FAILED, facts.state)
            self.assertFalse(facts.exports_complete)
            self.assertEqual((), facts.receipts)

    def test_synchronous_children_keep_invocation_order_and_shared_admission(self):
        coordinator = Coordinator(admission=ResourceAdmission(cpu_slots=1, native_bytes=20, derived_bytes=10))
        request = self.accept(coordinator, resources=ResourceRequest(native_bytes=20, derived_bytes=10))
        path = self.root / "child.bin"
        with coordinator.pull("family") as job:
            for sequence in (1, 2):
                with job.child(self.source, "child", outputs=(path,)) as invocation:
                    self.assertEqual(sequence, invocation.sequence)
                    self.assertEqual(request.ticket, invocation.ticket)
                    with job.admission.admit(ResourceRequest(native_bytes=20, derived_bytes=10)):
                        self.assertEqual((1, 20, 10), coordinator.admission.used)
                    job.geometry_ready(f"child-{sequence}")
                    self.publish(job, path, str(sequence).encode())
            job.geometry_ready("root")
        facts = coordinator.snapshot(request.ticket)
        self.assertEqual(b"2", path.read_bytes())
        self.assertEqual((0, 1, 2), facts.completed_invocations)
        self.assertEqual((1, 2), tuple(receipt.sequence for receipt in facts.receipts))
        self.assertEqual((0, 0, 0), coordinator.admission.used)

    def test_child_exports_remain_facts_when_root_fails(self):
        coordinator = Coordinator()
        request = self.accept(coordinator)
        path = self.root / "child-before-error.bin"
        with self.assertRaisesRegex(ValueError, "root failed"):
            with coordinator.pull("family") as job:
                with job.child(self.source, "child", outputs=(path,)):
                    job.geometry_ready("child")
                    self.publish(job, path)
                raise ValueError("root failed")
        facts = coordinator.snapshot(request.ticket)
        self.assertEqual(State.FAILED, facts.state)
        self.assertEqual((1,), facts.completed_invocations)
        self.assertEqual(1, len(facts.receipts))
        self.assertIsNone(facts.geometry_id)
        self.assertFalse(facts.exports_complete)

    def test_caught_child_export_failure_cannot_become_root_success(self):
        coordinator = Coordinator()
        request = self.accept(coordinator)
        path = self.root / "child-missing.bin"
        with self.assertRaises(RequestStateError):
            with coordinator.pull("family") as job:
                try:
                    with job.child(self.source, "child", outputs=(path,)):
                        job.geometry_ready("child")
                except RequestStateError:
                    pass
                # Catching the child error cannot erase its explicit output.
        facts = coordinator.snapshot(request.ticket)
        self.assertEqual(State.FAILED, facts.state)
        self.assertEqual(((1, path),), facts.required_outputs)
        self.assertEqual((), facts.receipts)
        self.assertEqual((0, 0, 0), coordinator.admission.used)

    def test_nested_children_are_synchronous_and_keep_the_parent_ticket(self):
        coordinator = Coordinator()
        request = self.accept(coordinator)
        events = []
        with coordinator.pull("family") as job:
            with job.child(self.source, "child") as child:
                events.append(child.sequence)
                with job.child(self.source, "grandchild") as grandchild:
                    events.append(grandchild.sequence)
                    self.assertEqual(request.ticket, grandchild.ticket)
                    job.geometry_ready("grandchild")
                self.assertIs(child, job.invocation)
                job.geometry_ready("child")
            self.assertEqual(0, job.invocation.sequence)
            job.geometry_ready("root")
        self.assertEqual([1, 2], events)
        self.assertEqual((0, 1, 2), coordinator.snapshot(request.ticket).completed_invocations)

    def test_grandchild_child_root_share_path_in_actual_publication_order(self):
        coordinator = Coordinator()
        path = self.root / "nested-shared.bin"
        request = self.accept(coordinator, outputs=(path,))
        with coordinator.pull("family") as job:
            with job.child(self.source, "child", outputs=(path,)):
                with job.child(self.source, "grandchild", outputs=(path,)):
                    job.geometry_ready("grandchild")
                    self.publish(job, path, b"grandchild")
                job.geometry_ready("child")
                self.publish(job, path, b"child")
            job.geometry_ready("root")
            self.publish(job, path, b"root")
        facts = coordinator.snapshot(request.ticket)
        self.assertEqual(State.EXPORTS_COMPLETE, facts.state)
        self.assertEqual(b"root", path.read_bytes())
        self.assertEqual((2, 1, 0), tuple(receipt.sequence for receipt in facts.receipts))
        self.assertEqual((1, 2, 3), tuple(receipt.publication_sequence for receipt in facts.receipts))

    def test_child_same_request_write_does_not_bypass_a_newer_request_claim(self):
        coordinator = Coordinator()
        path = self.root / "nested-conflict.bin"
        request = self.accept(coordinator, outputs=(path,))
        with self.assertRaises(PublicationConflict):
            with coordinator.pull("family") as job:
                with job.child(self.source, "child", outputs=(path,)):
                    job.geometry_ready("child")
                    self.publish(job, path, b"child")
                later = self.accept(coordinator, outputs=(path,))
                job.geometry_ready("root")
                self.publish(job, path, b"root")
        facts = coordinator.snapshot(request.ticket)
        self.assertEqual(State.FAILED, facts.state)
        self.assertEqual(1, len(facts.receipts))
        self.assertEqual(b"child", path.read_bytes())
        self.assertGreater(later.ticket, request.ticket)

    def test_repeated_same_invocation_publications_retain_every_receipt(self):
        coordinator = Coordinator()
        path = self.root / "repeated.bin"
        request = self.accept(coordinator, outputs=(path,))
        with coordinator.pull("family") as job:
            job.geometry_ready("root")
            self.publish(job, path, b"first")
            self.publish(job, path, b"second")
        receipts = coordinator.snapshot(request.ticket).receipts
        self.assertEqual((0, 0), tuple(receipt.sequence for receipt in receipts))
        self.assertEqual((1, 2), tuple(receipt.publication_sequence for receipt in receipts))
        self.assertEqual(b"second", path.read_bytes())

    def test_two_jobs_share_global_bounds_and_children_cannot_exceed_reservation(self):
        coordinator = Coordinator(admission=ResourceAdmission(cpu_slots=2, native_bytes=30, derived_bytes=20))
        demand = ResourceRequest(cpu_slots=1, native_bytes=15, derived_bytes=10)
        first = self.accept(coordinator, "one", resources=demand)
        second = self.accept(coordinator, "two", resources=demand)
        third = self.accept(coordinator, "three", resources=demand)
        one, two = coordinator.pull("one"), coordinator.pull("two")
        self.assertEqual((2, 30, 20), coordinator.admission.used)
        self.assertIsNone(coordinator.pull("three"))
        self.assertEqual(State.QUEUED, coordinator.snapshot(third.ticket).state)
        for oversized in (ResourceRequest(cpu_slots=2), ResourceRequest(native_bytes=16),
                          ResourceRequest(derived_bytes=11)):
            with self.assertRaises(AdmissionDenied):
                with one.admission.admit(oversized):
                    self.fail("borrower exceeded its reservation")
        with self.assertRaisesRegex(ValueError, "operator failed"):
            with one:
                with one.admission.admit(demand):
                    raise ValueError("operator failed")
        self.assertEqual((1, 15, 10), coordinator.admission.used)
        self.assertEqual(State.FAILED, coordinator.snapshot(first.ticket).state)
        with two:
            two.geometry_ready("two")
        with coordinator.pull("three") as three:
            three.geometry_ready("three")
        self.assertEqual(State.EXPORTS_COMPLETE, coordinator.snapshot(second.ticket).state)
        self.assertEqual((0, 0, 0), coordinator.admission.used)

    def test_outstanding_borrower_prevents_early_global_reservation_release(self):
        coordinator = Coordinator()
        self.accept(coordinator)
        job = coordinator.pull("family")
        job.geometry_ready("ready")
        borrower = job.admission.admit(ResourceRequest())
        borrower.__enter__()
        with self.assertRaises(RequestStateError):
            job.finish()
        self.assertEqual((1, 0, 0), coordinator.admission.used)
        self.assertIsNone(coordinator.pull("family"))
        borrower.__exit__(None, None, None)
        job.finish()
        self.assertEqual((0, 0, 0), coordinator.admission.used)

    def test_owner_thread_is_required_for_native_dispatch_operations(self):
        coordinator = Coordinator()
        self.accept(coordinator)
        job = coordinator.pull("family")
        errors = []
        def wrong_thread():
            try:
                job.geometry_ready("wrong")
            except RequestStateError as error:
                errors.append(str(error))
        thread = threading.Thread(target=wrong_thread)
        thread.start()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(1, len(errors))
        with job:
            job.geometry_ready("owner")

    def test_capacity_rejects_new_work_without_dropping_accepted_explicit_jobs(self):
        coordinator = Coordinator(max_queued=1, max_records=2)
        first = self.accept(coordinator)
        with self.assertRaises(QueueFull):
            self.accept(coordinator)
        with self.assertRaises(RequestStateError):
            coordinator.forget(first.ticket)
        coordinator.cancel(first.ticket)
        second = self.accept(coordinator)
        coordinator.cancel(second.ticket)
        with self.assertRaises(QueueFull):
            self.accept(coordinator)
        coordinator.forget(first.ticket)
        third = self.accept(coordinator)
        self.assertEqual(3, third.ticket)
        with self.assertRaises(AdmissionDenied):
            self.accept(coordinator, resources=ResourceRequest(cpu_slots=2))

    def test_publication_lock_linearizes_acceptance_and_rejects_reentrancy(self):
        coordinator = Coordinator()
        path = self.root / "serialized.bin"
        request = self.accept(coordinator, outputs=(path,))
        started, accepted = threading.Event(), threading.Event()
        results = []
        def accept_later():
            started.set()
            results.append(self.accept(coordinator, outputs=(path,)))
            accepted.set()
        job = coordinator.pull("family")
        job.geometry_ready("old")
        with job.publication(path) as publication:
            thread = threading.Thread(target=accept_later)
            thread.start()
            self.assertTrue(started.wait(2))
            self.assertFalse(accepted.is_set())
            with self.assertRaises(RequestStateError):
                self.accept(coordinator, outputs=(path,))
            with self.assertRaises(RequestStateError):
                job.finish()
            path.write_bytes(b"first")
            publication.acknowledge(hashlib.sha256(b"first").hexdigest())
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertTrue(accepted.is_set())
        with self.assertRaises(PublicationConflict):
            job.finish()
        self.assertEqual(State.FAILED, coordinator.snapshot(request.ticket).state)
        self.assertGreater(results[0].ticket, request.ticket)

    def test_authority_is_process_local(self):
        coordinator = Coordinator()
        with patch("cadgen._document.scheduler.os.getpid", return_value=os.getpid() + 1):
            with self.assertRaisesRegex(RequestStateError, "another process"):
                self.accept(coordinator)


if __name__ == "__main__":
    unittest.main()
