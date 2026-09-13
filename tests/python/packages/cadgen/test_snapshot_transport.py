"""Closed snapshot transport, admission and receipts without Chromium or a kernel."""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
import json
from pathlib import Path
import queue
import threading
import time
import unittest
from unittest.mock import Mock, patch

from cadgen.assets import runtime_root
from cadgen.daemon import snapshot
from cadgen.results import SnapshotResult, SnapshotTimings
from cadgen.snapshot_core import SnapshotError
from cadgen.snapshot_operation import capture_operation, operation_key, normalize_operation, result_value
from cadgen.snapshot_service import current_snapshot_service


def operation(name="one"):
    return capture_operation({"single": True, "jobs": [{"input": name, "mode": "list", "outputs": [],
                                                       "resolved": {"rootPath": f"/tmp/{name}"}}]},
                             runtime_dir=runtime_root() / "browser", cache_root="/tmp/snapshot-store")


def request(op):
    return {"tool": "snapshot-render", "argv": [], "snapshot": op, "request": operation_key(op), "token": "token"}


class Wire:
    def __init__(self):
        self.incoming = queue.Queue()
        self.outgoing = queue.Queue()
        self.closed = False

    def recv(self, timeout=None, *, max_bytes=None):
        try:
            value = self.incoming.get(timeout=timeout)
            if max_bytes is not None and len(value) > max_bytes:
                return b""
            return value
        except queue.Empty:
            return None

    def send(self, value):
        if self.closed:
            raise OSError("closed")
        self.outgoing.put(value)

    def close(self):
        self.closed = True
        self.outgoing.put(b"")

    def stop_receiving(self):
        self.incoming.put(b"")

    def stop_sending(self):
        self.closed = True

    def peer(self):
        peer = Wire()
        peer.incoming, peer.outgoing = self.outgoing, self.incoming
        return peer

    def read(self, timeout=2):
        return json.loads(self.outgoing.get(timeout=timeout))


class FakeWorker:
    def __init__(self):
        self.requests = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.cancelled = threading.Event()
        self.reaped = threading.Event()
        self.allow_reap = threading.Event()
        self.allow_reap.set()
        self.ack_shutdown = True
        self.living = True

    def send(self, value):
        self.requests.append(value)
        self.output = queue.Queue()
        def pump():
            try:
                for frame in self.frames():
                    self.output.put(frame)
            finally:
                self.output.put(None)
        self.pump = threading.Thread(target=pump, daemon=True)
        self.pump.start()

    def next_frame(self, *, timeout):
        from cadgen.daemon.pool import WorkerGone
        try:
            value = self.output.get(timeout=timeout)
        except queue.Empty:
            return None
        if value is None:
            raise WorkerGone("fake worker output ended")
        return value

    def frames(self, **kwargs):
        key = self.requests[-1]["request"]
        self.entered.set()
        yield {"snapshotProgress": {"request": key, "method": "detail", "args": ["rendering"], "kwargs": {}}}
        while not self.release.wait(.001) and not self.cancelled.is_set():
            pass
        if self.cancelled.is_set():
            yield {"snapshotOutcome": {"request": key, "result": None, "error": "cancelled", "clean": True}}
            if self.ack_shutdown:
                yield {"snapshotShutdown": {"request": key, "closed": True}}
            yield {"exit": 1}
        else:
            yield {"snapshotOutcome": {"request": key, "result": result_value(SnapshotResult(True, timings=SnapshotTimings(1))), "error": None, "clean": True}}
            yield {"exit": 0}

    def reclaim(self, deadline):
        self.cancelled.set()
        if not self.allow_reap.wait(max(0, deadline - time.monotonic())):
            return False
        self.living = False
        self.reaped.set()
        return True

    def alive(self):
        return self.living


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(0, snapshot._count)
        self.assertEqual(0, snapshot._bytes)
        self.enterContext(patch.object(snapshot, "_poison", None))
        self.enterContext(patch.object(snapshot, "_failed_writers", []))
        self.worker = FakeWorker()
        self.pool = Mock(acquire=Mock(return_value=self.worker))
        self.jobs = Mock(start=Mock(return_value={"id": "job"}))
        self.threads = []

    def tearDown(self):
        self.worker.release.set()
        self.worker.allow_reap.set()
        for thread in self.threads:
            thread.join(3)
            self.assertFalse(thread.is_alive())
        self.assertEqual(0, snapshot._count)
        self.assertEqual(0, snapshot._bytes)

    def serve(self, op=None, wire=None):
        op = op or operation()
        wire = wire or Wire()
        thread = threading.Thread(target=snapshot.serve_render, args=(wire, request(op)),
                                  kwargs={"pool": self.pool, "jobs": self.jobs})
        thread.start()
        self.threads.append(thread)
        return wire, thread

    def receipt(self, wire):
        while True:
            value = wire.read()
            if "snapshotReceipt" in value:
                return value["snapshotReceipt"]

    def test_two_packets_reuse_one_worker_affinity_and_return_one_final_receipt(self):
        self.worker.release.set()
        for name in ("one", "two"):
            op = operation(name)
            wire, thread = self.serve(op)
            receipt = self.receipt(wire)
            thread.join(2)
            self.assertTrue(snapshot.read_receipt(op, receipt).ok)
            self.assertTrue(wire.outgoing.empty())
        self.assertEqual(2, self.pool.acquire.call_count)
        self.assertTrue(all(call.args == ("cadgen:snapshot-render",) for call in self.pool.acquire.call_args_list))
        self.assertTrue(all(call.kwargs["healthy"] for call in self.pool.release.call_args_list))
        self.assertEqual(["one", "two"], [r["snapshot"]["packet"]["jobs"][0]["input"] for r in self.worker.requests])
        self.assertTrue(all("env" not in r and "cwd" not in r and r["argv"] == [] for r in self.worker.requests))

    def test_queued_cancel_releases_capacity_without_assigning_worker(self):
        with patch.object(snapshot, "MAX_REQUESTS", 2):
            first, _ = self.serve()
            self.assertTrue(self.worker.entered.wait(2))
            op = operation("queued")
            queued, thread = self.serve(op)
            deadline = time.monotonic() + 2
            while snapshot._count != 2 and time.monotonic() < deadline:
                time.sleep(.001)
            full, _ = self.serve(operation("full"))
            self.assertIn("capacity", self.receipt(full)["error"])
            queued.incoming.put(json.dumps({"snapshotCancel": operation_key(op)}).encode())
            receipt = self.receipt(queued)
            self.assertEqual("cancelled", receipt["status"])
            self.assertFalse(receipt["cleanup"]["workerUsed"])
            thread.join(2)
            self.assertEqual(1, snapshot._count)
            self.assertEqual(1, self.pool.acquire.call_count)
            self.worker.release.set()
            self.receipt(first)

    def test_active_cancel_receipt_waits_for_supervisor_reap_and_preserves_browser_ack(self):
        self.enterContext(patch.object(snapshot, "CONTROL_JOIN_SECONDS", .01))
        self.worker.allow_reap.clear()
        op = operation()
        wire, _ = self.serve(op)
        self.assertTrue(self.worker.entered.wait(2))
        wire.incoming.put(json.dumps({"snapshotCancel": operation_key(op)}).encode())
        self.assertTrue(self.worker.cancelled.wait(2))
        time.sleep(.03)
        frames = []
        while not wire.outgoing.empty():
            frames.append(wire.read())
        self.assertFalse(any("snapshotReceipt" in frame for frame in frames))
        self.worker.allow_reap.set()
        receipt = self.receipt(wire)
        self.assertEqual("cancelled", receipt["status"])
        self.assertEqual({"job": True, "owner": True, "workerReaped": True, "workerUsed": True}, receipt["cleanup"])
        with self.assertRaises(snapshot._RenderCancelled):
            snapshot.read_receipt(op, receipt)
        self.assertIsNone(snapshot._poison)
        self.pool.release.assert_called_once_with(self.worker, healthy=False)

    def test_hard_reap_without_browser_ack_poison_prevents_new_launch(self):
        self.worker.ack_shutdown = False
        op = operation()
        wire, _ = self.serve(op)
        self.assertTrue(self.worker.entered.wait(2))
        wire.incoming.put(json.dumps({"snapshotCancel": operation_key(op)}).encode())
        self.assertTrue(self.receipt(wire)["cleanup"]["workerReaped"])
        following, _ = self.serve(operation("following"))
        self.assertIn("shutdown acknowledgement", self.receipt(following)["error"])
        self.assertEqual(1, self.pool.acquire.call_count)

    def test_late_shutdown_after_normal_exit_is_drained_before_cancellation_receipt(self):
        class LateShutdown(FakeWorker):
            def frames(self, **kwargs):
                key = self.requests[-1]["request"]
                self.entered.set()
                self.cancelled.wait(2)
                yield {"snapshotOutcome": {"request": key, "result": result_value(SnapshotResult(True)), "error": None, "clean": True}}
                yield {"exit": 0}
                yield {"snapshotShutdown": {"request": key, "closed": True}}
        self.worker = LateShutdown()
        self.pool.acquire.return_value = self.worker
        op = operation()
        wire, _ = self.serve(op)
        self.assertTrue(self.worker.entered.wait(2))
        wire.incoming.put(json.dumps({"snapshotCancel": operation_key(op)}).encode())
        receipt = self.receipt(wire)
        self.assertEqual("cancelled", receipt["status"])
        self.assertTrue(receipt["cleanup"]["owner"])
        self.assertTrue(receipt["cleanup"]["workerReaped"])
        self.assertIsNone(snapshot._poison)
        self.pool.release.assert_called_once_with(self.worker, healthy=False)

    def test_deadline_does_not_restart_at_admission(self):
        op = operation()
        op["deadline"] = time.monotonic() + snapshot.CLEANUP_SECONDS - .1
        wire, _ = self.serve(op)
        self.assertIn("timed out during admission", self.receipt(wire)["error"])
        self.pool.acquire.assert_not_called()

    def test_cancel_during_worker_acquisition_releases_undispatched_lease_healthy(self):
        entered, acquired = threading.Event(), threading.Event()
        self.addCleanup(acquired.set)
        def acquire(*args, **kwargs):
            entered.set()
            self.assertTrue(acquired.wait(2))
            return self.worker
        self.pool.acquire.side_effect = acquire
        consumed = threading.Event()
        wire = Wire()
        original_recv = wire.recv
        def recv(*args, **kwargs):
            value = original_recv(*args, **kwargs)
            if value:
                consumed.set()
            return value
        wire.recv = recv
        op = operation()
        wire, thread = self.serve(op, wire)
        self.assertTrue(entered.wait(2))
        wire.incoming.put(json.dumps({"snapshotCancel": operation_key(op)}).encode())
        self.assertTrue(consumed.wait(2))
        # Let the reader leave its recv call and record the cancellation before
        # handing the still-unclaimed worker to the request thread.
        deadline = time.monotonic() + 2
        while any(t.name == "cadgen-snapshot-control" and t.is_alive() for t in threading.enumerate()):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.001)
        acquired.set()
        receipt = self.receipt(wire)
        thread.join(2)
        self.assertEqual("cancelled", receipt["status"])
        self.assertFalse(receipt["cleanup"]["workerUsed"])
        self.assertFalse(receipt["cleanup"]["workerReaped"])
        self.assertEqual([], self.worker.requests)
        self.pool.release.assert_called_once_with(self.worker, healthy=True)
        self.assertIsNone(snapshot._poison)

    def test_deadline_during_worker_acquisition_never_dispatches_render(self):
        op = operation()
        with patch.object(snapshot, "CLEANUP_SECONDS", .1):
            op["deadline"] = time.monotonic() + .2
            def acquire(*args, **kwargs):
                while time.monotonic() < kwargs["deadline"]:
                    time.sleep(.001)
                return self.worker
            self.pool.acquire.side_effect = acquire
            wire, thread = self.serve(op)
            receipt = self.receipt(wire)
            thread.join(2)
        self.assertIn("timed out during worker acquisition", receipt["error"])
        self.assertFalse(receipt["cleanup"]["workerUsed"])
        self.assertEqual([], self.worker.requests)
        self.pool.release.assert_called_once_with(self.worker, healthy=True)
        self.assertIsNone(snapshot._poison)

    def test_blocked_worker_upload_is_reaped_and_joined_before_receipt(self):
        from cadgen.daemon.pool import WorkerGone
        class BlockedUpload(FakeWorker):
            def send(self, value):
                self.requests.append(value)
                self.entered.set()
                self.cancelled.wait(2)
                raise OSError("worker upload pipe closed")
            def next_frame(self, **kwargs):
                raise WorkerGone("worker reaped before parsing its request")
        self.worker = BlockedUpload()
        self.pool.acquire.return_value = self.worker
        op = operation()
        wire, thread = self.serve(op)
        self.assertTrue(self.worker.entered.wait(2))
        wire.incoming.put(json.dumps({"snapshotCancel": operation_key(op)}).encode())
        receipt = self.receipt(wire)
        thread.join(2)
        self.assertEqual("cancelled", receipt["status"])
        self.assertTrue(receipt["cleanup"]["workerReaped"])
        self.assertFalse(receipt["cleanup"]["owner"])
        self.assertFalse(any(t.name == "cadgen-snapshot-upload" and t.is_alive() for t in threading.enumerate()))
        self.pool.release.assert_called_once_with(self.worker, healthy=False)
        self.assertIn("shutdown acknowledgement", snapshot._poison)

    @unittest.skipIf(__import__("os").name == "nt", "POSIX socket backpressure")
    def test_nonreading_client_progress_is_aborted_and_worker_reaped_before_deadline(self):
        import multiprocessing.connection as connection
        import socket
        from cadgen.daemon.transport import Channel

        class Verbose(FakeWorker):
            def frames(self, **kwargs):
                yield {"stream": "stdout", "data": "x" * (1024 * 1024)}
                yield from super().frames(**kwargs)
        self.worker = Verbose()
        self.pool.acquire.return_value = self.worker
        server_socket, client_socket = socket.socketpair()
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        server = Channel(connection.Connection(server_socket.detach()))
        self.addCleanup(server.close)
        self.addCleanup(client_socket.close)
        op = operation()
        with patch.object(snapshot, "CLEANUP_SECONDS", .2), self.assertLogs(snapshot.__name__, level="WARNING") as logs:
            op["deadline"] = time.monotonic() + .5
            _, thread = self.serve(op, server)
            thread.join(.8)
            self.assertFalse(thread.is_alive(), "outgoing backpressure cannot extend the request deadline")
        self.assertTrue(self.worker.reaped.is_set())
        self.pool.release.assert_called_once_with(self.worker, healthy=False)
        self.assertEqual(0, snapshot._count)
        self.assertIsNone(snapshot._poison)
        self.assertTrue(any("completion receipt delivery failed" in item for item in logs.output))
        self.assertFalse(any(t.name.startswith("cadgen-snapshot-") and t.is_alive() for t in threading.enumerate()))

    def test_blocked_terminal_receipt_has_bounded_failure_without_reaping_healthy_worker(self):
        class BlockedReceipt(Wire):
            def __init__(self):
                super().__init__()
                self.aborted = threading.Event()
            def send(self, value):
                if "snapshotReceipt" in json.loads(value):
                    self.aborted.wait(2)
                    raise OSError("response send aborted")
                super().send(value)
            def stop_sending(self):
                self.aborted.set()
                super().stop_sending()
        wire = BlockedReceipt()
        self.worker.release.set()
        op = operation()
        with patch.object(snapshot, "CLEANUP_SECONDS", .2), self.assertLogs(snapshot.__name__, level="WARNING") as logs:
            op["deadline"] = time.monotonic() + .4
            _, thread = self.serve(op, wire)
            thread.join(.7)
            self.assertFalse(thread.is_alive())
        self.assertTrue(wire.aborted.is_set())
        self.assertFalse(self.worker.reaped.is_set())
        self.pool.release.assert_called_once_with(self.worker, healthy=True)
        self.assertIsNone(snapshot._poison)
        self.assertEqual(0, snapshot._count)
        self.assertTrue(any("completion receipt delivery failed" in item for item in logs.output))
        self.assertFalse(any(t.name == "cadgen-snapshot-response" and t.is_alive() for t in threading.enumerate()))

    def test_unstoppable_response_writer_retains_charged_owner_and_refuses_new_admission(self):
        finished = threading.Event()
        class StuckReceipt(Wire):
            def send(self, value):
                if "snapshotReceipt" in json.loads(value):
                    finished.wait(2)
                    return
                super().send(value)
        self.worker.release.set()
        op = operation()
        retained = None
        try:
            with patch.object(snapshot, "CLEANUP_SECONDS", .1), self.assertLogs(snapshot.__name__, level="WARNING"):
                op["deadline"] = time.monotonic() + .2
                _, thread = self.serve(op, StuckReceipt())
                thread.join(.5)
                self.assertFalse(thread.is_alive())
            self.assertIn("response writer teardown", snapshot._poison)
            self.assertEqual(1, snapshot._count)
            self.assertGreater(snapshot._bytes, 0)
            self.assertEqual(1, len(snapshot._failed_writers))
            retained = snapshot._failed_writers[0][0]
            self.assertTrue(retained.thread.is_alive())
            following, _ = self.serve(operation("following"))
            self.assertIn("response writer teardown", self.receipt(following)["error"])
            self.pool.acquire.assert_called_once()
            self.pool.release.assert_called_once_with(self.worker, healthy=True)
        finally:
            finished.set()
            if retained is None and snapshot._failed_writers:
                retained = snapshot._failed_writers[0][0]
            if retained is not None:
                self.assertTrue(retained.close(time.monotonic() + 1))
                # Simulate retiring the poisoned test host only after proving
                # its deliberately uninterruptible writer finally stopped.
                with snapshot._guard:
                    snapshot._count -= 1
                    snapshot._bytes -= snapshot.packet_size_bound(request(op))

    @unittest.skipIf(__import__("os").name == "nt", "POSIX partial stream frame; named pipes are message oriented")
    def test_partial_control_frame_while_queued_obeys_deadline_and_releases_admission(self):
        import multiprocessing.connection as connection
        import socket
        import struct
        from cadgen.daemon.transport import Channel

        server_socket, client_socket = socket.socketpair()
        server = Channel(connection.Connection(server_socket.detach()))
        self.addCleanup(server.close)
        self.addCleanup(client_socket.close)
        op = operation("queued-prefix")
        with patch.object(snapshot, "CLEANUP_SECONDS", .1):
            op["deadline"] = time.monotonic() + .3
            control = json.dumps({"snapshotCancel": operation_key(op)}).encode()
            client_socket.sendall(struct.pack("!i", len(control)) + control[:1])
            with snapshot._serial:
                _, thread = self.serve(op, server)
                thread.join(.6)
                self.assertFalse(thread.is_alive(), "an incomplete control body must not extend admission")
                self.pool.acquire.assert_not_called()
                self.assertEqual(0, snapshot._count)
                self.assertEqual(0, snapshot._bytes)
                self.assertIsNone(snapshot._poison)
                self.assertFalse(any(t.name == "cadgen-snapshot-control" and t.is_alive() for t in threading.enumerate()))

    @unittest.skipIf(__import__("os").name == "nt", "POSIX partial stream frame; named pipes are message oriented")
    def test_partial_control_frame_is_interrupted_and_reader_joined_before_worker_reuse(self):
        import multiprocessing.connection as connection
        import socket
        import struct
        from cadgen.daemon.transport import Channel

        server_socket, client_socket = socket.socketpair()
        native = connection.Connection(server_socket.detach())
        entered = threading.Event()
        class Tracked:
            def poll(self, *args): return native.poll(*args)
            def fileno(self): return native.fileno()
            def close(self): native.close()
            def recv_bytes(self, *args, **kwargs):
                entered.set()
                return native.recv_bytes(*args, **kwargs)
            def send_bytes(self, *args): return native.send_bytes(*args)
        server = Channel(Tracked())
        self.addCleanup(server.close)
        self.addCleanup(client_socket.close)
        op = operation()
        _, thread = self.serve(op, server)
        self.assertTrue(self.worker.entered.wait(2))
        control = json.dumps({"snapshotCancel": operation_key(op)}).encode()
        client_socket.sendall(struct.pack("!i", len(control)) + control[:4])
        self.assertTrue(entered.wait(2))
        def released(worker, *, healthy):
            self.assertTrue(healthy)
            self.assertFalse(any(item.name == "cadgen-snapshot-control" and item.is_alive() for item in threading.enumerate()))
        self.pool.release.side_effect = released
        self.worker.release.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertFalse(self.worker.reaped.is_set())
        self.pool.release.assert_called_once_with(self.worker, healthy=True)
        # Late completion of the abandoned control frame cannot target the
        # worker after its completed lease has returned to the pool.
        try:
            client_socket.sendall(control[4:])
        except OSError:
            pass
        self.assertFalse(self.worker.reaped.is_set())


class WorkerPollingTests(unittest.TestCase):
    def test_supervisor_does_not_close_a_channel_retained_by_unjoined_native_io(self):
        from cadgen.daemon import server
        conn = Mock()
        with patch.object(snapshot, "_failed_controls", []), patch.object(snapshot, "_failed_writers", [(object(), conn)]) as retained, \
             patch.object(server, "_handle_request"):
            server._serve_connection(conn, request(operation()))
            conn.close.assert_not_called()
            retained.clear()
            server._serve_connection(conn, request(operation()))
            conn.close.assert_called_once()

    def test_idle_poll_is_not_a_worker_failure_and_eof_keeps_exit_status(self):
        from cadgen.daemon.pool import Worker, WorkerGone, _TIMED_OUT
        worker = Worker.__new__(Worker)
        worker.proc = Mock(pid=123)
        worker.kill = Mock()
        worker._exit_status = Mock(return_value=-9)
        worker._read_frame = Mock(side_effect=[_TIMED_OUT, {"exit": 0}, None])
        self.assertIsNone(worker.next_frame(timeout=.01))
        self.assertEqual({"exit": 0}, worker.next_frame(timeout=.01))
        with self.assertRaises(WorkerGone) as raised:
            worker.next_frame(timeout=.01)
        self.assertEqual(-9, raised.exception.exit_status)
        worker.kill.assert_not_called()

    def test_response_writer_bounds_bytes_and_outstanding_frame_count(self):
        release = threading.Event()
        writer = snapshot._WriteOwner(lambda value: release.wait(2), name="test-snapshot-writer")
        try:
            with self.assertRaisesRegex(SnapshotError, "capacity"):
                writer.begin(b"x", size=snapshot.MAX_FRAME_BYTES + 1)
            self.assertIsNone(writer.thread)
            writer.begin(b"one", size=3)
            with self.assertRaisesRegex(SnapshotError, "capacity"):
                writer.begin(b"two", size=3)
        finally:
            release.set()
            self.assertTrue(writer.close(time.monotonic() + 1))


class SchemaTests(unittest.TestCase):
    def test_closed_packet_and_installed_runtime_authority(self):
        op = operation()
        captured = normalize_operation(op)
        op["packet"]["jobs"][0]["resolved"]["rootPath"] = "/tmp/mutated"
        self.assertEqual("/tmp/one", captured["packet"]["jobs"][0]["resolved"]["rootPath"])
        op["runtimeRoot"] = "/tmp/arbitrary-code"
        with self.assertRaisesRegex(SnapshotError, "installation"):
            normalize_operation(op)
        op = operation()
        op["packet"]["jobs"][0]["resolved"]["callback"] = object()
        with self.assertRaisesRegex(SnapshotError, "plain JSON"):
            normalize_operation(op)
        op = operation()
        op["source"] = "unwanted.py"
        with self.assertRaisesRegex(SnapshotError, "fields"):
            normalize_operation(op)

    def test_cancellation_cannot_claim_receipt_without_shutdown_or_reap(self):
        op = operation()
        receipt = snapshot._receipt(operation_key(op), "cancelled", error="cancelled", job=True, worker_used=True)["snapshotReceipt"]
        with self.assertRaisesRegex(SnapshotError, "not acknowledged shutdown or been reaped"):
            snapshot.read_receipt(op, receipt)

    def test_cli_binding_is_explicit_and_library_scope_stays_unbound(self):
        self.assertIsNone(current_snapshot_service())
        with patch.dict("os.environ", {}, clear=True), snapshot.cli_snapshot_service():
            self.assertIsInstance(current_snapshot_service(), snapshot.RemoteSnapshotService)
        self.assertIsNone(current_snapshot_service())
        for env in ({"CADGEN_DAEMON": "0"}, {"CADGEN_BROWSER_RUNTIME_DIR": "/tmp/dev"}, {"CADGEN_DAEMON_CHILD": "1"}):
            with patch.dict("os.environ", env, clear=True), snapshot.cli_snapshot_service():
                self.assertIsNone(current_snapshot_service())


class RemoteTests(unittest.IsolatedAsyncioTestCase):
    async def test_transport_progress_returns_to_caller_context_and_cancel_awaits_receipt(self):
        caller = threading.get_ident()
        context = ContextVar("snapshot_transport_test", default="empty")
        context.set("caller")
        remote = Wire()
        server = remote.peer()
        worker = FakeWorker()
        worker.allow_reap.clear()
        pool = Mock(acquire=Mock(return_value=worker))
        jobs = Mock(start=Mock(return_value={"id": "job"}))
        threads = []
        def dispatch():
            payload = json.loads(server.recv(2))
            snapshot.serve_render(server, payload, pool=pool, jobs=jobs)
        def connect(*args, **kwargs):
            thread = threading.Thread(target=dispatch)
            thread.start()
            threads.append(thread)
            return remote
        seen = []
        progress = Mock(detail=lambda text: seen.append((threading.get_ident(), context.get(), text)))
        op = operation()
        async def local_transport(payload, cancel, relay):
            stopped = threading.Event()
            async def stop():
                await cancel.wait()
                stopped.set()
            control = asyncio.create_task(stop())
            try:
                receipt = await asyncio.to_thread(snapshot._run_remote, payload, stopped, relay)
                return snapshot.read_receipt(payload["snapshot"], receipt)
            finally:
                control.cancel()
                try:
                    await control
                except asyncio.CancelledError:
                    pass
        with patch("cadgen.daemon.client._connect_or_spawn", connect), patch("cadgen.daemon.client.compute_version_token", return_value="token"), patch.object(snapshot, "_poison", None), patch("cadgen.daemon.snapshot_transport.transport_request", local_transport):
            task = asyncio.create_task(snapshot.RemoteSnapshotService().render(op["packet"], runtime_dir=Path(op["runtimeRoot"]), progress=progress))
            self.assertTrue(await asyncio.to_thread(worker.entered.wait, 2))
            await asyncio.sleep(.01)
            self.assertEqual([(caller, "caller", "rendering")], seen)
            task.cancel()
            self.assertTrue(await asyncio.to_thread(worker.cancelled.wait, 2))
            self.assertFalse(task.done())
            task.cancel()
            worker.allow_reap.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())


class FakeProcess:
    def __init__(self, lines=(), *, hang=False):
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.stderr.feed_eof()
        for line in lines:
            self.stdout.feed_data(json.dumps(line).encode() + b"\n")
        if not hang:
            self.stdout.feed_eof()
        self.returncode = None if hang else 0
        self.finished = asyncio.Event()
        if not hang:
            self.finished.set()
        self.writes = []
        self.stdin = Mock(write=self.writes.append, drain=self.drain)
        self.killed = False

    async def drain(self):
        return None

    async def wait(self):
        await self.finished.wait()
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9
        self.stdout.feed_eof()
        self.finished.set()


class TransportProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_transport_child_is_reaped_and_distinguished_from_worker_cleanup(self):
        from cadgen.daemon.snapshot_transport import transport_request
        op = operation()
        op["deadline"] = time.monotonic() + 1.05
        proc = FakeProcess(hang=True)
        async def create(*args, **kwargs):
            self.assertEqual("cadgen.daemon.snapshot_transport", args[3])
            self.assertEqual(str(Path(snapshot.__file__).resolve().parents[2]), kwargs["env"]["PYTHONPATH"])
            return proc
        started = time.monotonic()
        with patch("asyncio.create_subprocess_exec", create):
            with self.assertRaisesRegex(SnapshotError, "transport process reaped; worker/browser cleanup was not confirmed"):
                await transport_request(request(op), asyncio.Event(), Mock())
        self.assertTrue(proc.killed)
        self.assertLess(time.monotonic() - started, .5)

    async def test_supervisor_receipt_is_preserved_and_no_late_progress_is_accepted(self):
        from cadgen.daemon.snapshot_transport import transport_request
        op = operation()
        receipt = snapshot._receipt(operation_key(op), "ok", result=result_value(SnapshotResult(True)), job=True, worker_used=True)["snapshotReceipt"]
        for late in (False, True):
            with self.subTest(late=late):
                lines = [{"receipt": receipt}]
                if late:
                    lines.append({"progress": {"method": "detail", "args": ["late"], "kwargs": {}}})
                proc = FakeProcess(lines)
                async def create(*args, **kwargs):
                    return proc
                with patch("asyncio.create_subprocess_exec", create):
                    if late:
                        with self.assertRaisesRegex(SnapshotError, "after its completion receipt"):
                            await transport_request(request(op), asyncio.Event(), Mock())
                    else:
                        self.assertTrue((await transport_request(request(op), asyncio.Event(), Mock())).ok)
