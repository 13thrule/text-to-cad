"""Typed snapshot transport. Only resolved values reach the worker's renderer."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager, suppress
from contextvars import Context
import json
import logging
import os
import queue
import threading
import time

from cadgen.snapshot_core import SnapshotError, _capture_snapshot_job, _finish_snapshot_cleanup
from cadgen.snapshot_operation import (
    CLEANUP_SECONDS, MAX_FRAME_BYTES, MAX_PACKET_BYTES, capture_operation, normalize_operation,
    operation_key, packet_size_bound, progress_value, read_result,
)

MAX_REQUESTS = 4
CONTROL_POLL_SECONDS = .025
CONTROL_JOIN_SECONDS = 1.0
_guard = threading.Lock()
_serial = threading.Lock()
_count = 0
_bytes = 0
_poison = None
_failed_controls = []
_failed_writers = []
_AFFINITY = "cadgen:snapshot-render"


def retains_connection(conn):
    """A poisoned request still owns native I/O on this channel until host exit."""
    with _guard:
        return any(item[0] is conn for item in _failed_controls) or any(item[1] is conn for item in _failed_writers)


def _send(conn, value):
    conn.send(json.dumps(value, separators=(",", ":"), allow_nan=False).encode())


def _receive(conn, timeout, *, limit=MAX_FRAME_BYTES):
    raw = conn.recv(timeout, max_bytes=limit)
    if raw is None or raw == b"":
        return raw
    try:
        value = json.loads(raw)
        return _capture_snapshot_job(value)
    except (ValueError, TypeError, RecursionError) as exc:
        raise SnapshotError("invalid snapshot protocol frame") from exc


def _outcome(operation, value):
    if type(value) is not dict or set(value) != {"request", "result", "error", "clean"}:
        raise SnapshotError("invalid snapshot worker outcome")
    if value["request"] != operation_key(operation) or type(value["clean"]) is not bool:
        raise SnapshotError("snapshot worker outcome does not match its request")
    if value["error"] is not None and (type(value["error"]) is not str or len(value["error"]) > 8192):
        raise SnapshotError("invalid snapshot worker error")
    if value["result"] is not None:
        if value["error"] is not None or not value["clean"]:
            raise SnapshotError("snapshot success requires acknowledged job cleanup")
        result = read_result(value["result"])
        expected = [output["path"] for job in operation["packet"]["jobs"] for output in job["outputs"]]
        if [str(item.path) for item in result.files] != expected:
            raise SnapshotError("snapshot worker result does not match its declared outputs")
    elif value["error"] is None:
        raise SnapshotError("snapshot worker outcome has no result or error")
    return value


def _receipt(key, status, *, result=None, error=None, job=False, owner=False, reaped=False, worker_used=False):
    return {"snapshotReceipt": {"request": key, "status": status, "result": result, "error": error,
                                 "cleanup": {"job": job, "owner": owner, "workerReaped": reaped, "workerUsed": worker_used}}}


def read_receipt(operation, value, *, as_value=False):
    if type(value) is not dict or set(value) != {"request", "status", "result", "error", "cleanup"}:
        raise SnapshotError("invalid snapshot completion receipt")
    if value["request"] != operation_key(operation) or value["status"] not in {"ok", "error", "cancelled"}:
        raise SnapshotError("snapshot completion does not match its request")
    cleanup = value["cleanup"]
    if type(cleanup) is not dict or set(cleanup) != {"job", "owner", "workerReaped", "workerUsed"} or any(type(v) is not bool for v in cleanup.values()):
        raise SnapshotError("invalid snapshot cleanup receipt")
    if not cleanup["job"] and not cleanup["owner"] and not cleanup["workerReaped"]:
        raise SnapshotError("snapshot cleanup was not acknowledged; owning worker requires reclamation")
    if value["status"] == "ok":
        _outcome(operation, {"request": value["request"], "result": value["result"], "error": value["error"], "clean": cleanup["job"]})
        return value if as_value else read_result(value["result"])
    if value["result"] is not None or type(value["error"]) is not str:
        raise SnapshotError("invalid snapshot failure receipt")
    if value["status"] == "cancelled":
        if cleanup["workerUsed"] and not cleanup["owner"] and not cleanup["workerReaped"]:
            raise SnapshotError("cancelled snapshot worker has not acknowledged shutdown or been reaped")
        if not as_value:
            raise _RenderCancelled(value["error"])
        return value
    if as_value:
        return value
    raise SnapshotError(value["error"])


class _RenderCancelled(SnapshotError):
    """Cancellation with a supervisor cleanup receipt, not just a closed socket."""


def _control(conn, key, timeout):
    message = _receive(conn, timeout, limit=4096)
    if message is None:
        return None
    if message == b"":
        return "disconnected"
    if message == {"snapshotCancel": key}:
        return "cancelled"
    raise SnapshotError("invalid snapshot control frame")


class _WriteOwner:
    """One bounded writer, with at most one outstanding frame including upload.

    The request thread waits for each completion before submitting another.
    Neither this thread nor a queued value can act on a later worker lease.
    """
    def __init__(self, send, *, name):
        self.send = send
        self.name = name
        self.thread = None
        self.pending = queue.Queue(maxsize=1)
        self.stopped = threading.Event()
        self.ticket = None

    def begin(self, value, *, size):
        if self.stopped.is_set():
            raise SnapshotError("snapshot writer is closed")
        if size > MAX_FRAME_BYTES or self.ticket is not None and not self.ticket["done"].is_set():
            raise SnapshotError("snapshot response transfer capacity is full")
        ticket = {"value": value, "done": threading.Event(), "error": None}
        self.pending.put_nowait(ticket)
        self.ticket = ticket
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name=self.name, daemon=True)
            self.thread.start()
        return ticket

    def _run(self):
        while True:
            ticket = self.pending.get()
            if ticket is None:
                return
            try:
                if self.stopped.is_set():
                    raise SnapshotError("snapshot writer stopped before transfer")
                self.send(ticket["value"])
            except BaseException as exc:
                ticket["error"] = exc
            finally:
                ticket["value"] = None
                ticket["done"].set()

    def close(self, deadline, *, abort=None):
        self.stopped.set()
        if self.thread is None:
            return True
        with suppress(queue.Full):
            self.pending.put_nowait(None)
        while self.thread.is_alive() and time.monotonic() < deadline:
            with suppress(queue.Full):
                self.pending.put_nowait(None)
            if abort is not None:
                with suppress(OSError):
                    abort()
            self.thread.join(min(CONTROL_POLL_SECONDS, max(0, deadline - time.monotonic())))
        return not self.thread.is_alive()


def serve_render(conn, request, *, pool, jobs):
    """One bounded serial render admission, with one terminal supervisor receipt."""
    global _count, _bytes, _poison
    key = request.get("request")
    reserved = locked = worker_used = False
    job = worker = None
    outcome = None
    closed_owner = False
    healthy = True
    state = {"cancel": None}
    reaped = False
    stop = threading.Event()
    control_guard = threading.Lock()
    reader_joined = True
    watcher = None
    upload = None
    upload_joined = True
    responses = _WriteOwner(conn.send, name="cadgen-snapshot-response")
    response_usable = True
    responses_joined = True
    delivered = False
    error = None
    operation = None

    def wait_write(ticket, deadline, *, phase, observe_cancel=True):
        while not ticket["done"].is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0 or observe_cancel and cancelled(phase):
                raise SnapshotError("snapshot" + phase + " did not complete before cancellation or deadline")
            ticket["done"].wait(min(CONTROL_POLL_SECONDS, remaining))
        if ticket["error"] is not None:
            raise SnapshotError("snapshot" + phase + " failed: " + str(ticket["error"])) from ticket["error"]

    def respond(value, *, terminal=False):
        nonlocal response_usable
        if not response_usable:
            raise SnapshotError("snapshot completion receipt cannot use an interrupted response channel")
        started = False
        try:
            charge = packet_size_bound(value)
            payload = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
            ticket = responses.begin(payload, size=charge)
            started = True
            deadline = receipt_deadline if terminal else work_deadline
            wait_write(ticket, deadline, phase=" response transfer", observe_cancel=not terminal)
        except BaseException:
            # A partial frame cannot be resumed or followed by another receipt.
            if started:
                response_usable = False
                with suppress(OSError):
                    conn.stop_sending()
            raise

    def cancelled(phase=""):
        with control_guard:
            if not state["cancel"] and time.monotonic() >= work_deadline:
                state["cancel"] = "timed out" + phase
            return state["cancel"]

    def watch():
        # This is the only reader, including while queued or acquiring a worker.
        # It records a decision; only the request thread can dispatch or reclaim.
        try:
            while not stop.is_set():
                control = _control(conn, key, CONTROL_POLL_SECONDS)
                with control_guard:
                    if stop.is_set():
                        return
                    if control:
                        state["cancel"] = control
                        return
        except BaseException as exc:
            with control_guard:
                if not stop.is_set():
                    state["cancel"] = str(exc) or "disconnected"

    def accept_frame(frame, *, relay):
        nonlocal outcome, closed_owner
        if "exit" in frame:
            if int(frame["exit"]) != 0 and outcome is None:
                raise SnapshotError("snapshot worker exited without an outcome")
            return True
        if set(frame) == {"snapshotOutcome"}:
            if outcome is not None:
                raise SnapshotError("duplicate snapshot worker outcome")
            outcome = _outcome(operation, frame["snapshotOutcome"])
        elif set(frame) == {"snapshotShutdown"}:
            if frame["snapshotShutdown"] != {"request": key, "closed": True}:
                raise SnapshotError("invalid snapshot worker shutdown receipt")
            closed_owner = True
        elif set(frame) == {"snapshotProgress"}:
            event = frame["snapshotProgress"]
            if set(event) != {"request", "method", "args", "kwargs"} or event["request"] != key:
                raise SnapshotError("invalid snapshot progress identity")
            progress_value(event["method"], event["args"], event["kwargs"])
            if relay and not state["cancel"] and outcome is None:
                respond(frame)
        elif frame.get("stream") in {"stdout", "stderr"} and type(frame.get("data")) is str:
            if relay and not state["cancel"] and outcome is None:
                respond(frame)
        else:
            raise SnapshotError("unexpected snapshot worker frame")
        return False

    try:
        if set(request) != {"tool", "argv", "snapshot", "request", "token"} or request["argv"] != []:
            raise SnapshotError("snapshot operations have no argv, source subject or ambient environment")
        # Charge the decoded JSON before copying it on this request thread.
        size = packet_size_bound(request)
        with _guard:
            if _poison is not None:
                raise SnapshotError(_poison)
            if _count >= MAX_REQUESTS or _bytes + size > MAX_PACKET_BYTES:
                raise SnapshotError("snapshot daemon render admission capacity is full")
            _count += 1
            _bytes += size
            reserved = True
        operation = normalize_operation(request["snapshot"])
        if key != operation_key(operation):
            raise SnapshotError("snapshot operation digest does not match its captured inputs")
        work_deadline = operation["deadline"] - CLEANUP_SECONDS
        cleanup_deadline = operation["deadline"] - min(2, CLEANUP_SECONDS / 4)
        receipt_deadline = operation["deadline"] - min(1.5, CLEANUP_SECONDS / 5)
        io_deadline = operation["deadline"] - min(1, CLEANUP_SECONDS / 8)
        watcher = threading.Thread(target=watch, name="cadgen-snapshot-control", daemon=True)
        watcher.start()
        while not cancelled(" during admission"):
            if _serial.acquire(timeout=max(0, min(CONTROL_POLL_SECONDS, work_deadline - time.monotonic()))):
                locked = True
                break
        if cancelled(" during admission"):
            return
        with _guard:
            if _poison is not None:
                raise SnapshotError(_poison)
        job = jobs.start(tool="snapshot-render", subject="", argv=[], store_root=operation["storeRoot"],
                         editing_producer=False, adopt_announced=False)
        worker = pool.acquire(_AFFINITY, deadline=work_deadline)
        # Cancellation can arrive while acquire starts a worker. An undispatched
        # lease is still healthy and has no browser work to acknowledge or reap.
        with control_guard:
            if not state["cancel"] and time.monotonic() >= work_deadline:
                state["cancel"] = "timed out during worker acquisition"
            if state["cancel"]:
                return
            worker_used = True
        upload = _WriteOwner(worker.send, name="cadgen-snapshot-upload")
        ticket = upload.begin({"kind": "snapshot", "tool": "snapshot-render", "argv": [], "request": key, "snapshot": operation}, size=size)
        wait_write(ticket, work_deadline, phase=" worker upload")
        upload_joined = upload.close(min(work_deadline, time.monotonic() + CONTROL_JOIN_SECONDS))
        if not upload_joined:
            raise SnapshotError("snapshot worker upload did not stop before its deadline")
        saw_exit = False
        while not cancelled():
            frame = worker.next_frame(timeout=max(0, min(CONTROL_POLL_SECONDS, work_deadline - time.monotonic())))
            if frame is not None and accept_frame(frame, relay=True):
                saw_exit = True
                break
        if cancelled():
            healthy = False
            return
        if not saw_exit or outcome is None:
            raise SnapshotError("snapshot worker returned no completed outcome")
        healthy = outcome["clean"] and not closed_owner
        error = outcome["error"]
    except BaseException as exc:
        error = (str(exc) or type(exc).__name__)[:8192]
        healthy = not worker_used
    finally:
        with control_guard:
            stop.set()
        if watcher is not None:
            # poll() can see only a frame prefix. Abort that native read and
            # require its join even when the request never acquired a worker.
            join_deadline = min(cleanup_deadline, time.monotonic() + CONTROL_JOIN_SECONDS)
            while watcher.is_alive() and time.monotonic() < join_deadline:
                with suppress(OSError):
                    conn.stop_receiving()
                watcher.join(min(CONTROL_POLL_SECONDS, max(0, join_deadline - time.monotonic())))
            reader_joined = not watcher.is_alive()
            if not reader_joined:
                healthy = False
                error = "snapshot control reader teardown failed; owning daemon must be reclaimed"
                with _guard:
                    _poison = error
                    # Retain ownership and admission until the host is retired.
                    _failed_controls.append((conn, watcher, worker))
        if worker is not None:
            reclaim_worker = worker_used and (state["cancel"] or not healthy)
            if reclaim_worker:
                healthy = False
                reaped = worker.reclaim(cleanup_deadline)
            if upload is not None:
                upload_joined = upload.close(min(cleanup_deadline, time.monotonic() + CONTROL_JOIN_SECONDS))
                if not upload_joined:
                    healthy = False
                    error = "snapshot worker upload teardown failed; owning daemon must be reclaimed"
                    with _guard:
                        _poison = error
                        _failed_writers.append((upload, worker))
            if reclaim_worker:
                if reaped:
                    # Termination can race the normal exit frame. Drain through
                    # EOF after reap to collect outer-finally owner cleanup too.
                    from cadgen.daemon.pool import WorkerGone
                    drain_deadline = min(cleanup_deadline, time.monotonic() + .25)
                    try:
                        while time.monotonic() < drain_deadline:
                            late = worker.next_frame(timeout=min(CONTROL_POLL_SECONDS, max(0, drain_deadline - time.monotonic())))
                            if late is not None:
                                accept_frame(late, relay=False)
                    except WorkerGone:
                        pass
                    except BaseException as exc:
                        error = str(exc) or "invalid late snapshot shutdown receipt"
                if not closed_owner:
                    # A process reap alone cannot assert Chromium teardown.
                    with _guard:
                        _poison = "snapshot worker reclamation lacked a browser shutdown acknowledgement; restart the owning daemon"
            if reader_joined and upload_joined:
                pool.release(worker, healthy=healthy and worker.alive())
        if locked:
            _serial.release()
        connected = state["cancel"] != "disconnected"
        status = "ok" if outcome and outcome["result"] is not None and not state["cancel"] and healthy else "error"
        if state["cancel"] in {"cancelled", "disconnected"}:
            status = "cancelled"
        if operation is None or "receipt_deadline" not in locals():
            # Even a rejected admission gets bounded best-effort delivery.
            receipt_deadline = time.monotonic() + CONTROL_JOIN_SECONDS
            io_deadline = receipt_deadline + CONTROL_POLL_SECONDS
        if connected:
            try:
                respond(_receipt(key, status,
                    result=outcome["result"] if status == "ok" else None,
                    error=None if status == "ok" else error or state["cancel"] or "snapshot request failed",
                    job=not worker_used or bool(outcome and outcome["clean"]),
                    owner=closed_owner, reaped=reaped, worker_used=worker_used), terminal=True)
                delivered = True
            except BaseException as exc:
                error = "snapshot completion receipt delivery failed: " + str(exc)
                logging.getLogger(__name__).warning(error)
        responses_joined = responses.close(io_deadline, abort=None if response_usable else conn.stop_sending)
        if not responses_joined:
            error = "snapshot response writer teardown failed; owning daemon must be reclaimed"
            logging.getLogger(__name__).error(error)
            with _guard:
                _poison = error
                _failed_writers.append((responses, conn))
        if job is not None:
            jobs.finish(job, 0 if healthy and reader_joined and upload_joined and responses_joined and delivered and outcome and outcome["result"] is not None and not state["cancel"] else 1, error=error)
        if reserved and reader_joined and upload_joined and responses_joined:
            with _guard:
                _count -= 1
                _bytes -= size


def _run_remote(payload, cancel, relay):
    from cadgen.daemon import client

    operation = payload["snapshot"]
    deadline = operation["deadline"]
    for attempt in range(2):
        if cancel.is_set():
            raise _RenderCancelled("snapshot cancelled before transfer")
        conn = client._connect_or_spawn(client.daemon_address(), deadline=deadline)
        if conn is None:
            raise SnapshotError("snapshot daemon could not start before its deadline; no render was retried")
        timer = threading.Timer(max(0, deadline - time.monotonic()), conn.close)
        timer.daemon = True
        timer.start()
        observed = False
        sent_cancel = False
        try:
            _send(conn, payload)
            while time.monotonic() < deadline:
                if cancel.is_set() and not sent_cancel:
                    # The supervisor can have revoked its input direction just
                    # before its completed receipt arrives on the other one.
                    with suppress(OSError):
                        _send(conn, {"snapshotCancel": payload["request"]})
                    sent_cancel = True
                frame = _receive(conn, min(.1, max(0, deadline - time.monotonic())))
                if frame is None:
                    continue
                if frame == b"":
                    raise SnapshotError("snapshot connection closed without a cleanup receipt; no retry")
                if frame == {"restart": True} and not observed and attempt == 0:
                    break
                observed = True
                if set(frame) == {"snapshotReceipt"}:
                    return read_receipt(operation, frame["snapshotReceipt"], as_value=True)
                if set(frame) == {"snapshotProgress"}:
                    event = frame["snapshotProgress"]
                    if set(event) != {"request", "method", "args", "kwargs"} or event["request"] != payload["request"]:
                        raise SnapshotError("invalid remote snapshot progress")
                    event = progress_value(event["method"], event["args"], event["kwargs"])
                    if not sent_cancel:
                        relay.send(event["method"], *event["args"], **event["kwargs"])
                elif set(frame) == {"stream", "data"} and frame["stream"] in {"stdout", "stderr"} and type(frame["data"]) is str:
                    if not sent_cancel:
                        relay.send("stream", frame["stream"], frame["data"])
                else:
                    raise SnapshotError("invalid remote snapshot frame; no retry")
            else:
                raise SnapshotError("snapshot deadline expired without a cleanup receipt; no retry")
        finally:
            timer.cancel()
            conn.close()
    raise SnapshotError("snapshot daemon restart did not complete before its deadline")


class RemoteSnapshotService:
    """Explicit CLI adapter; creates no local browser and executes no source remotely."""
    async def render(self, packet, *, runtime_dir, progress=None, narrate=None):
        from cadgen.store.paths import store_root
        from cadgen.snapshot_video import ffmpeg_binary
        from pathlib import Path

        from cadgen.snapshot_operation import resolved_packet
        packet = resolved_packet(packet)
        encoder = str(Path(ffmpeg_binary()).resolve()) if any(job.get("video") is not None for job in packet["jobs"]) else None
        operation = capture_operation(packet, runtime_dir=runtime_dir, cache_root=store_root(), encoder=encoder)
        return await self.render_operation(operation, progress=progress, narrate=narrate)

    async def render_operation(self, operation, *, progress=None, narrate=None, cleanup=None):
        from cadgen.daemon.client import compute_version_token
        from cadgen.snapshot_operation import RenderCleanup
        from cadgen.snapshot_service import _Relay
        if cleanup is not None:
            if type(cleanup) is not RenderCleanup:
                raise TypeError("snapshot cleanup requires an internal lifetime proof")
            cleanup.acknowledged = True  # No transport has been admitted yet.
        operation = normalize_operation(operation)
        payload = {"tool": "snapshot-render", "argv": [], "snapshot": operation,
                   "request": operation_key(operation), "token": compute_version_token()}
        relay = _Relay(progress, narrate)
        cancel = asyncio.Event()
        from cadgen.daemon.snapshot_transport import transport_request
        transfer = (transport_request(payload, cancel, relay) if cleanup is None else
                    transport_request(payload, cancel, relay, cleanup=cleanup))
        future = asyncio.create_task(transfer, context=Context())
        try:
            done, _pending = await asyncio.wait((future, relay.failure), return_when=asyncio.FIRST_COMPLETED)
            if relay.failure in done:
                relay.failure.result()
            return future.result()
        except BaseException as error:
            cancel.set()
            try:
                if future.done():
                    future.result()
                else:
                    await _finish_snapshot_cleanup(future)
            except (_RenderCancelled, asyncio.CancelledError):
                pass
            except BaseException as cleanup_error:
                if cleanup_error is not error:
                    error.add_note(f"Snapshot transport cleanup failed: {cleanup_error}")
            raise
        finally:
            relay.close()


@contextmanager
def cli_snapshot_service():
    from cadgen.snapshot_service import bind_snapshot_service, current_snapshot_service
    from cadgen.daemon.client import daemon_supported

    # An explicit development bundle remains caller-owned. Worker code authority
    # is the installed bundle, never a directory sent by a requesting process.
    if current_snapshot_service() is not None or os.environ.get("CADGEN_DAEMON") == "0" or os.environ.get("CADGEN_DAEMON_CHILD") or os.environ.get("CADGEN_BROWSER_RUNTIME_DIR") or not daemon_supported():
        yield
    else:
        with bind_snapshot_service(RemoteSnapshotService()):
            yield
