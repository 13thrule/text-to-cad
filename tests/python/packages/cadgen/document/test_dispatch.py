"""Synthetic dispatch races plus a separately runnable real-owner integration."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

from cadgen._document import dispatch
from cadgen._document.dispatch import DocumentDispatcher, DispatchFull, DispatcherClosed, StaleLease
from cadgen._document.worker import WorkerError, WorkerCancelled, WorkerTimeout

CONTEXT = {"cwd": "/captured", "environment": {"EXACT": "original"}}


class _FakeWorker:
    instances = []
    startup_delay = 0.
    constructed = threading.Event()

    def __init__(self, root, *, startup_timeout, cancellation):
        self.thread = threading.get_ident()
        self.number = len(self.instances) + 1
        self.instances.append(self)
        self._closed = False
        self.calls = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.received = threading.Event()
        self.close_calls = 0
        self.leases = {}
        self.constructed.set()
        start = time.monotonic()
        while time.monotonic() - start < self.startup_delay:
            if cancellation.is_set():
                self.close(force=True)
                raise WorkerCancelled("startup cancelled")
            if time.monotonic() - start >= startup_timeout:
                self.close(force=True)
                raise WorkerTimeout("startup timed out")
            time.sleep(.001)

    def request(self, operation, *, payloads, timeout, cancellation_grace, cancellation, context, **params):
        assert self.thread == threading.get_ident()
        assert not self._closed
        if cancellation.is_set():
            raise WorkerCancelled("pre-send cancellation")
        self.calls.append((operation, params, payloads, context, timeout))
        mode = params.get("path", "")
        if mode == "block":
            self.started.set()
            deadline = time.monotonic() + timeout
            while not self.release.wait(.002):
                if cancellation.is_set() or time.monotonic() >= deadline:
                    self.close(force=True)
                    raise WorkerCancelled("active cancelled") if cancellation.is_set() else WorkerTimeout("active timed out")
        if mode == "crash":
            self.close(force=True)
            raise WorkerError("owner lost")
        if mode == "failure":
            raise WorkerError("authored failure", details={"error": "authored"})
        if operation in {"generate", "open_step"}:
            revision = {"lease": f"lease-{self.number}-{len(self.calls)}", "owner": f"owner-{self.number}",
                        "revision": len(self.calls), "document": "document"}
            self.leases[revision["lease"]] = revision
            result = {"revision": revision}
        elif operation == "release":
            self.leases.pop(params["lease"])
            result = {"released": True}
        else:
            assert params["lease"] in self.leases
            result = {"lease": params["lease"], "context": context, "parameters": params}
        if mode == "late":
            self.received.set()
            self.release.wait(2)  # successful native result already owns a lease
        return {"result": result, "ok": True}, ()

    def close(self, *, force):
        assert self.thread == threading.get_ident()
        self.close_calls += 1
        self._closed = True
        self.leases.clear()


def generate(dispatcher, path="normal", **kwargs):
    return dispatcher.submit("generate", path=path, digest=hashlib.sha256(b"source").hexdigest(),
                             payloads=(b"source",), context=CONTEXT, **kwargs)


def lease(ticket):
    return ticket.result()[0]["result"]["revision"]


class DispatchTests(unittest.TestCase):
    def setUp(self):
        _FakeWorker.instances = []
        _FakeWorker.startup_delay = 0.
        _FakeWorker.constructed = threading.Event()
        self.mock = patch.object(dispatch, "DocumentWorker", _FakeWorker)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def dispatcher(self, **kwargs):
        result = DocumentDispatcher(Path("/tmp/document-dispatch-synthetic"), **kwargs)
        self.addCleanup(result.shutdown)
        return result

    def test_thread_owner_exact_context_params_and_payload_snapshot(self):
        dispatcher = self.dispatcher()
        revision = lease(generate(dispatcher))
        active = generate(dispatcher, "block")
        worker = _FakeWorker.instances[0]
        self.assertTrue(worker.started.wait(1))
        context = {"cwd": "/before", "environment": {"TOKEN": "before"}}
        known, options = ["a" * 64], {"relative_chord": .01}
        queued = dispatcher.submit("display", lease=revision, options=options, known=known, context=context)
        context["cwd"] = "/after"; context["environment"]["TOKEN"] = "after"
        known[0] = "b" * 64; options["relative_chord"] = .5
        payloads = [b"captured"]
        source = dispatcher.submit("open_step", annotations=None, path="another", digest="c" * 64, payloads=payloads, context=CONTEXT)
        payloads[0] = b"changed"
        worker.release.set(); active.result(); queued.result(); source.result()
        _, params, _, captured, _ = worker.calls[2]
        self.assertEqual({"cwd": "/before", "environment": {"TOKEN": "before"}}, captured)
        self.assertEqual(["a" * 64], params["known"])
        self.assertEqual(.01, params["options"]["relative_chord"])
        self.assertEqual((b"captured",), worker.calls[3][2])
        self.assertNotEqual(threading.get_ident(), worker.thread)
        self.assertEqual(b"", source._request.metadata)
        self.assertEqual((), source._request.payloads)

    def test_concurrent_submitters_are_serial_and_share_an_exact_lease(self):
        dispatcher = self.dispatcher()
        revision = lease(generate(dispatcher))
        def submit(_):
            ticket = dispatcher.submit("display", lease=revision, context=CONTEXT)
            return ticket.sequence, ticket.result()[0]["result"]["lease"]
        with ThreadPoolExecutor(max_workers=8) as callers:
            results = list(callers.map(submit, range(8)))
        self.assertEqual(8, len({sequence for sequence, _ in results}))
        self.assertEqual({revision["lease"]}, {value for _, value in results})
        self.assertEqual(1, len(_FakeWorker.instances))
        self.assertEqual(9, len(_FakeWorker.instances[0].calls))

    def test_count_bytes_and_pending_cancel_reclaim_admission(self):
        dispatcher = self.dispatcher(max_pending=2, max_buffered_bytes=1500)
        active = generate(dispatcher, "block")
        # Worker construction/request occurs only on its dispatcher thread.
        self.assertTrue(_FakeWorker.constructed.wait(1))
        worker = _FakeWorker.instances[0]
        self.assertTrue(worker.started.wait(1))
        pending = generate(dispatcher)
        with self.assertRaises(DispatchFull):
            generate(dispatcher)
        self.assertTrue(pending.cancel())
        self.assertFalse(pending.cancel())
        with self.assertRaises(WorkerCancelled):
            pending.result()
        with self.assertRaises(DispatchFull):
            dispatcher.submit("open_step", annotations=None, path="oversized", digest="a" * 64,
                              payloads=(b"x" * 1500,), context=CONTEXT)
        replacement = generate(dispatcher)
        worker.release.set(); active.result(); replacement.result()
        self.assertEqual(2, len(worker.calls))
        self.assertEqual(0, dispatcher._bytes)
        self.assertFalse(dispatcher._pending)

    def test_queued_deadline_is_prompt_and_does_not_destroy_healthy_owner(self):
        dispatcher = self.dispatcher()
        revision = lease(generate(dispatcher))
        active = generate(dispatcher, "block")
        worker = _FakeWorker.instances[0]
        self.assertTrue(worker.started.wait(1))
        queued = generate(dispatcher, timeout=.03)
        with self.assertRaises(WorkerTimeout):
            queued.result()
        self.assertFalse(worker._closed)
        self.assertEqual(2, len(worker.calls))
        worker.release.set(); active.result()
        dispatcher.submit("display", lease=revision, context=CONTEXT).result()
        self.assertEqual(1, len(_FakeWorker.instances))

    def test_queue_startup_and_request_consume_one_deadline(self):
        dispatcher = self.dispatcher()
        _FakeWorker.startup_delay = .06
        started = time.monotonic()
        with self.assertRaises(WorkerTimeout):
            generate(dispatcher, "block", timeout=.09).result()
        self.assertLess(time.monotonic() - started, .3)
        self.assertLess(_FakeWorker.instances[0].calls[0][-1], .05)
        self.assertTrue(_FakeWorker.instances[0]._closed)

    def test_startup_cancel_or_timeout_reclaims_capacity_without_executing_source(self):
        for expired in (False, True):
            with self.subTest(expired=expired):
                dispatcher = self.dispatcher(max_pending=1)
                _FakeWorker.constructed.clear()
                _FakeWorker.startup_delay = .5
                active = generate(dispatcher, timeout=.03 if expired else 1)
                self.assertTrue(_FakeWorker.constructed.wait(1))
                worker = _FakeWorker.instances[-1]
                if not expired:
                    self.assertTrue(active.cancel())
                with self.assertRaises(WorkerTimeout if expired else WorkerCancelled):
                    active.result()
                self.assertTrue(worker._closed)
                self.assertEqual([], worker.calls)
                self.assertEqual(0, dispatcher._bytes)
                _FakeWorker.startup_delay = 0.
                lease(generate(dispatcher))

    def test_late_result_expires_without_a_waiter_and_releases_unreported_lease(self):
        dispatcher = self.dispatcher()
        revision = lease(generate(dispatcher))
        active = generate(dispatcher, "late", timeout=.03)
        worker = _FakeWorker.instances[0]
        self.assertTrue(worker.received.wait(1))
        time.sleep(.04)
        worker.release.set()
        # Waiting on the private Future bypasses Ticket.result's expiry check.
        with self.assertRaises(WorkerTimeout):
            active._request.future.result(timeout=1)
        self.assertTrue(worker._closed)
        self.assertFalse(worker.leases)
        with self.assertRaises(StaleLease):
            dispatcher.submit("display", lease=revision, context=CONTEXT)

    def test_pre_send_cancel_preserves_existing_owner_and_revision(self):
        dispatcher = self.dispatcher()
        revision = lease(generate(dispatcher))
        worker = _FakeWorker.instances[0]
        original = worker.request
        entered, proceed = threading.Event(), threading.Event()
        def delayed(*args, **kwargs):
            entered.set()
            if not proceed.wait(1):
                raise AssertionError("test did not release pre-send request")
            return original(*args, **kwargs)
        with patch.object(worker, "request", delayed):
            active = generate(dispatcher)
            self.assertTrue(entered.wait(1))
            self.assertTrue(active.cancel())
            proceed.set()
            with self.assertRaises(WorkerCancelled):
                active.result()
        self.assertFalse(worker._closed)
        dispatcher.submit("display", lease=revision, context=CONTEXT).result()
        self.assertEqual(2, len(worker.calls))

    def test_implicit_caller_context_is_captured_before_queueing(self):
        dispatcher = self.dispatcher()
        active = generate(dispatcher, "block")
        self.assertTrue(_FakeWorker.constructed.wait(1))
        worker = _FakeWorker.instances[0]
        self.assertTrue(worker.started.wait(1))
        with patch.object(dispatch.os, "getcwd", return_value="/caller"), patch.dict(os.environ, {"EXACT": "captured"}, clear=True):
            queued = dispatcher.submit("open_step", annotations=None, path="part.step", digest="a" * 64, payloads=(b"step",))
        worker.release.set(); active.result(); queued.result()
        self.assertEqual({"cwd": "/caller", "environment": {"EXACT": "captured"}}, worker.calls[1][3])

    def test_cancel_active_and_late_success_destroy_owner_and_expire_all_leases(self):
        for mode in ("block", "late"):
            with self.subTest(mode=mode):
                dispatcher = self.dispatcher()
                revision = lease(generate(dispatcher))
                active = generate(dispatcher, mode)
                worker = _FakeWorker.instances[-1]
                self.assertTrue((worker.started if mode == "block" else worker.received).wait(1))
                queued_old = dispatcher.submit("display", lease=revision, context=CONTEXT)
                self.assertTrue(active.cancel())
                worker.release.set() if mode == "late" else None
                with self.assertRaises(WorkerCancelled):
                    active.result()
                self.assertTrue(worker._closed)
                self.assertFalse(worker.leases)
                with self.assertRaises(StaleLease):
                    queued_old.result()
                with self.assertRaises(StaleLease):
                    dispatcher.submit("display", lease=revision, context=CONTEXT)
                fresh = lease(generate(dispatcher))
                self.assertNotEqual(revision["owner"], fresh["owner"])
                self.assertEqual(2, len(worker.calls), "cancelled source was not automatically retried")
                self.assertFalse(active.cancel())

    def test_authored_failure_retains_owner_but_crash_invalidates_lease(self):
        dispatcher = self.dispatcher()
        revision = lease(generate(dispatcher))
        failure = generate(dispatcher, "failure")
        # Retrieving, rather than raising, the stored error must not retain
        # request execution frames after admission has been released.
        stored = failure._request.future.exception(timeout=1)
        self.assertIsNone(stored.__traceback__)
        self.assertIsNone(stored.__context__)
        self.assertEqual({"error": "authored"}, stored.details)
        with self.assertRaisesRegex(WorkerError, "authored failure"):
            failure.result()
        dispatcher.submit("display", lease=revision, context=CONTEXT).result()
        self.assertEqual(1, len(_FakeWorker.instances))
        with self.assertRaisesRegex(WorkerError, "owner lost"):
            generate(dispatcher, "crash").result()
        with self.assertRaises(StaleLease):
            dispatcher.submit("display", lease=revision, context=CONTEXT)
        self.assertEqual(0, dispatcher._bytes)

    def test_release_invalidates_all_consumers_and_scope_forgery_is_rejected(self):
        dispatcher = self.dispatcher()
        revision = lease(generate(dispatcher))
        for modified in ({**revision, "owner": "forged"}, {**revision, "revision": True}, revision["lease"]):
            with self.assertRaises(StaleLease):
                dispatcher.submit("display", lease=modified, context=CONTEXT)
        dispatcher.submit("release", lease=revision, context=CONTEXT).result()
        with self.assertRaises(StaleLease):
            dispatcher.submit("display", lease=revision, context=CONTEXT)

    def test_uncertain_release_failure_or_acknowledgement_invalidates_owner(self):
        for malformed in (False, True):
            with self.subTest(malformed=malformed):
                dispatcher = self.dispatcher()
                revision = lease(generate(dispatcher))
                worker = _FakeWorker.instances[-1]
                original = worker.request
                def partial_release(*args, **kwargs):
                    original(*args, **kwargs)
                    if malformed:
                        return {"result": {"released": False}}, ()
                    raise WorkerError("cleanup failed after native release")
                with patch.object(worker, "request", partial_release):
                    with self.assertRaises(WorkerError):
                        dispatcher.submit("release", lease=revision, context=CONTEXT).result()
                self.assertTrue(worker._closed)
                self.assertFalse(worker.leases)
                with self.assertRaises(StaleLease):
                    dispatcher.submit("display", lease=revision, context=CONTEXT)
                self.assertEqual(0, dispatcher._bytes)

    def test_wait_timeout_does_not_cancel_and_submission_rejects_mutable_or_open_values(self):
        dispatcher = self.dispatcher()
        active = generate(dispatcher, "block")
        self.assertTrue(_FakeWorker.constructed.wait(1))
        worker = _FakeWorker.instances[0]
        self.assertTrue(worker.started.wait(1))
        with self.assertRaises(FutureTimeout):
            active.result(wait_timeout=.01)
        self.assertFalse(active._request.cancellation.is_set())
        for invalid in (bytearray(b"x"), memoryview(b"x")):
            with self.assertRaises(TypeError):
                dispatcher.submit("open_step", annotations=None, path="invalid", digest="a" * 64, payloads=(invalid,))
        with self.assertRaises(ValueError):
            dispatcher.submit(lambda: None)
        with self.assertRaises(ValueError):
            dispatcher.submit("generate", path=object(), digest="a" * 64, payloads=(b"x",))
        worker.release.set(); active.result()

    def test_shutdown_cancels_and_joins_owner_thread_with_no_stranded_handles(self):
        dispatcher = self.dispatcher()
        active = generate(dispatcher, "block")
        self.assertTrue(_FakeWorker.constructed.wait(1))
        worker = _FakeWorker.instances[0]
        self.assertTrue(worker.started.wait(1))
        pending = generate(dispatcher)
        dispatcher.shutdown(timeout=1)
        for ticket in (active, pending):
            with self.assertRaises(WorkerCancelled):
                ticket.result()
        self.assertFalse(dispatcher._thread.is_alive())
        self.assertTrue(worker._closed)
        self.assertFalse(dispatcher._leases)
        self.assertEqual(0, dispatcher._bytes)
        with self.assertRaises(DispatcherClosed):
            generate(dispatcher)


class DispatchNativeTests(unittest.TestCase):
    def test_concurrent_callers_retain_one_real_owner_and_share_display_assets(self):
        from tests.python.support.tmp_root import generated_cad_directory
        with generated_cad_directory(prefix="document-dispatch-") as directory:
            root = Path(directory).resolve()
            source = b"from cadgen import step, build123d as bd\n@step\ndef part():\n    return bd.Box(2,3,4)\n"
            path = root / "part.py"
            path.write_bytes(b"raise AssertionError('entry was reread after capture')\n")
            with DocumentDispatcher(root / "catalog") as dispatcher:
                revision = lease(dispatcher.submit("generate", path=str(path),
                    digest=hashlib.sha256(source).hexdigest(), payloads=(source,), timeout=60))
                def display(_):
                    return dispatcher.submit("display", lease=revision,
                        options={"relative_chord": .01, "angular": .5, "edges": True}, timeout=60).result()
                with ThreadPoolExecutor(max_workers=3) as callers:
                    results = list(callers.map(display, range(3)))
                manifests = [json.loads(buffers[0]) for _, buffers in results]
                self.assertEqual({revision["owner"]}, {manifest["owner"] for manifest in manifests})
                self.assertEqual({revision["revision"]}, {manifest["revision"] for manifest in manifests})
                assets = [[row["identity"] for row in response["result"]["assets"]] for response, _ in results]
                self.assertEqual(assets[0], assets[1]); self.assertEqual(assets[1], assets[2])
                response, buffers = dispatcher.submit("display", lease=revision,
                    options={"relative_chord": .01, "angular": .5, "edges": True}, known=assets[0]).result()
                self.assertEqual([], response["result"]["assets"])
                self.assertEqual(1, len(buffers))
                occurrence = manifests[0]["occurrences"][0]
                reference = {"version": 1, "owner": revision["owner"], "revision": revision["revision"],
                             "path": occurrence["path"], "prototype": occurrence["prototype"],
                             "kind": "component", "ordinal": None}
                inspected, query_buffers = dispatcher.submit("query", lease=revision, references=[reference]).result()
                self.assertEqual((), query_buffers)
                self.assertAlmostEqual(24., inspected["result"]["facts"][0]["volume"])
                dispatcher.submit("release", lease=revision).result()
