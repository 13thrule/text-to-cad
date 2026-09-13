"""Bounded thread-safe requests to one thread-owned document process.

Only closed operation messages cross this boundary. It never runs submitted
callables, imports the old engine, retries source after owner loss, or claims an
RSS cap. Queue/startup/execution share an acceptance deadline; owner teardown
may take the worker's bounded cancellation/close interval after that deadline.
"""
from __future__ import annotations

from collections import deque
from concurrent.futures import Future, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import threading
import time
from types import MappingProxyType

from . import wire
from .worker import DocumentWorker, RemoteRevision, WorkerError, WorkerCancelled, WorkerTimeout

_SOURCE = frozenset({"generate", "open_step"})
_FIELDS = {
    "generate": frozenset({"path", "digest", "function"}),
    "open_step": frozenset({"path", "digest", "annotations"}),
    "display": frozenset({"lease", "options", "known"}),
    "query": frozenset({"lease", "references", "space"}),
    "checkpoint": frozenset({"lease"}),
    "release": frozenset({"lease"}),
}


class DispatchFull(RuntimeError):
    """The bounded dispatcher has no remaining count or buffered-byte capacity."""


class DispatcherClosed(RuntimeError):
    pass


class StaleLease(WorkerError):
    """A lease is unknown, released, or belongs to an owner that was lost."""


def _seconds(value, maximum=300):
    if type(value) not in (int, float) or not 0 < value <= maximum or not math.isfinite(value):
        raise ValueError(f"timeout must be positive, finite and at most {maximum} seconds")
    return float(value)


def _revision(value):
    if type(value) is RemoteRevision:
        result = value
    elif type(value) in (dict, MappingProxyType) and set(value) == {"lease", "owner", "revision", "document"}:
        result = RemoteRevision(**value)
    else:
        raise StaleLease("lease operations require an exact remote revision value")
    if (any(type(item) is not str or not item or len(item) > 4096
            for item in (result.lease, result.owner, result.document))
            or type(result.revision) is not int or result.revision < 1):
        raise StaleLease("invalid remote revision value")
    return result


@dataclass
class _Request:
    sequence: int
    operation: str
    metadata: bytes
    payloads: tuple[bytes, ...]
    deadline: float
    charge: int
    generation: int
    lease: RemoteRevision | None
    expired: bool = False
    call_started: bool = False
    cancellation: threading.Event = field(default_factory=threading.Event)
    future: Future = field(default_factory=Future)


@dataclass(frozen=True)
class DispatchTicket:
    sequence: int
    _dispatcher: DocumentDispatcher = field(repr=False)
    _request: _Request = field(repr=False)

    def cancel(self) -> bool:
        """Accept cancellation once; active cancellation never retries source."""
        return self._dispatcher._cancel(self._request)

    def done(self) -> bool:
        self._dispatcher._expire_pending()
        return self._request.future.done()

    def result(self, wait_timeout=None):
        """Wait for the worker's (response, immutable payloads) result.

        wait_timeout bounds this wait only; it does not cancel a request. The
        request's acceptance deadline always applies, including while queued.
        """
        wait_deadline = math.inf if wait_timeout is None else time.monotonic() + _seconds(wait_timeout, 86400)
        while True:
            remaining = min(wait_deadline, self._request.deadline) - time.monotonic()
            try:
                return self._request.future.result(timeout=max(0., remaining))
            except FutureTimeout:
                # Future.result also rethrows an operation's own TimeoutError.
                if self._request.future.done():
                    return self._request.future.result()
                if time.monotonic() >= self._request.deadline:
                    self._dispatcher._expire(self._request)
                    # Queued expiry is immediate. An active request must finish
                    # bounded owner teardown before reporting its terminal fact.
                    return self._request.future.result()
                raise


class DocumentDispatcher:
    """One worker-owning thread with bounded active + queued requests.

    Multiple callers may use the same exact RemoteRevision sequentially. Lease
    subscriber reference counting belongs to the coordinator above this class:
    an explicit release invalidates that lease for every caller. Only a fresh
    generate/open_step request may start an owner after a loss.

    Queued expiry is observed by submit/done/result and between executions.
    Without a caller observing it, an expired queued request retains its bounded
    reservation until the active call returns; there is no extra timer thread.
    Completed response buffers are caller-owned and outside the input budget.
    """

    def __init__(self, root: Path, *, max_pending=16, max_buffered_bytes=256 * 1024**2):
        if type(max_pending) is not int or not 1 <= max_pending <= 1024:
            raise ValueError("max_pending must be within 1..1024")
        if type(max_buffered_bytes) is not int or not 1 <= max_buffered_bytes <= wire.MAX_BYTES:
            raise ValueError("invalid dispatcher buffered-byte capacity")
        self.root = Path(root).resolve()
        self.max_pending = max_pending
        self.max_buffered_bytes = max_buffered_bytes
        self._condition = threading.Condition()
        self._queue = deque()
        self._active = None
        self._pending = {}
        self._bytes = 0
        self._next = 0
        self._generation = 0
        self._leases = {}
        self._worker = None
        self._stopping = False
        self._thread = threading.Thread(target=self._run, name="cadgen-document-dispatch", daemon=True)
        self._thread.start()

    def submit(self, operation, *, payloads=(), timeout=60, context=None, **parameters) -> DispatchTicket:
        started = time.monotonic()
        timeout = _seconds(timeout)
        if type(operation) is not str or operation not in _FIELDS:
            raise ValueError("unsupported document dispatcher operation")
        if type(payloads) not in (list, tuple) or len(payloads) > wire.MAX_PAYLOADS:
            raise ValueError("invalid document payload count")
        buffers = tuple(payloads)
        if len(buffers) > wire.MAX_PAYLOADS or any(type(value) is not bytes for value in buffers):
            raise TypeError("dispatcher payloads must be immutable bytes")
        expected_payloads = (1 + int(parameters.get("annotations") is not None)
                             if operation == "open_step" else int(operation == "generate"))
        if len(buffers) != expected_payloads:
            raise ValueError("source/open requests require their exact captured buffers; other requests require none")
        payload_bytes = sum(map(len, buffers))
        if payload_bytes > min(wire.MAX_BYTES, self.max_buffered_bytes):
            raise DispatchFull("document request exceeds buffered-byte capacity")
        params = dict(parameters)
        if operation == "generate":
            params.setdefault("function", None)
        elif operation == "display":
            params.setdefault("options", {})
            params.setdefault("known", [])
        elif operation == "query":
            params.setdefault("space", "world")
        if set(params) != _FIELDS[operation]:
            raise ValueError("invalid document operation fields")
        lease = None if operation in _SOURCE else _revision(params["lease"])
        if lease is not None:
            params["lease"] = lease.lease
        captured_context = ({"cwd": os.getcwd(), "environment": dict(os.environ)}
                            if context is None else context)
        values = wire._value({"parameters": params, "context": captured_context})
        if type(values["context"]) is not dict or set(values["context"]) != {"cwd", "environment"}:
            raise ValueError("document context requires cwd and environment")
        encoded = json.dumps(values, separators=(",", ":"), allow_nan=False).encode("utf-8")
        # Allow for the worker's operation/id/envelope fields before accepting.
        if len(encoded) + 256 > wire.MAX_HEADER:
            raise ValueError("document request metadata exceeds the protocol limit")
        charge = payload_bytes + len(encoded)
        with self._condition:
            self._expire_pending_locked()
            if self._stopping:
                raise DispatcherClosed("document dispatcher is shutting down")
            if len(self._pending) >= self.max_pending or self._bytes + charge > self.max_buffered_bytes:
                raise DispatchFull("document dispatcher capacity exhausted")
            if lease is not None and self._leases.get(lease.lease) != lease:
                raise StaleLease("document revision lease is unknown, released, or expired")
            if time.monotonic() >= started + timeout:
                raise WorkerTimeout("document request expired while capturing inputs")
            self._next += 1
            request = _Request(self._next, operation, encoded, buffers, started + timeout,
                               charge, self._generation, lease)
            self._pending[request.sequence] = request
            self._queue.append(request)
            self._bytes += charge
            self._condition.notify()
            return DispatchTicket(request.sequence, self, request)

    def _complete_locked(self, request, *, value=None, error=None):
        if request.sequence in self._pending:
            del self._pending[request.sequence]
            self._bytes -= request.charge
        # Release captured buffers even when callers retain the ticket forever.
        request.metadata = b""
        request.payloads = ()
        if not request.future.done():
            if error is not None:
                # Execution frames retain decoded metadata and input buffers.
                # The remote authored traceback remains in WorkerError.details;
                # callers own any frames added when they later raise the error.
                error.__traceback__ = error.__cause__ = error.__context__ = None
            request.future.set_exception(error) if error is not None else request.future.set_result(value)

    def _expire_pending_locked(self):
        now = time.monotonic()
        for request in tuple(self._queue):
            if now >= request.deadline:
                self._queue.remove(request)
                self._complete_locked(request, error=WorkerTimeout("document request expired in the queue"))

    def _expire_pending(self):
        with self._condition:
            self._expire_pending_locked()

    def _expire(self, request):
        with self._condition:
            if request.future.done():
                return
            if request is self._active:
                request.expired = True
                request.cancellation.set()
            elif request in self._queue:
                self._queue.remove(request)
                self._complete_locked(request, error=WorkerTimeout("document request expired in the queue"))

    def _cancel(self, request):
        with self._condition:
            if request.future.done() or request.cancellation.is_set():
                return False
            request.cancellation.set()
            if request is not self._active:
                self._queue.remove(request)
                self._complete_locked(request, error=WorkerCancelled("queued document request was cancelled"))
            self._condition.notify_all()
            return True

    def _drop_worker(self):
        worker, self._worker = self._worker, None
        try:
            if worker is not None:
                worker.close(force=True)
        finally:
            with self._condition:
                self._generation += 1
                self._leases.clear()

    def _execute(self, request):
        def remaining():
            if time.monotonic() >= request.deadline:
                raise WorkerTimeout("document request exceeded its acceptance deadline")
            if request.cancellation.is_set():
                raise WorkerCancelled("document request was cancelled before execution")
            return request.deadline - time.monotonic()
        remaining()
        if request.lease is not None:
            with self._condition:
                if (request.generation != self._generation
                        or self._leases.get(request.lease.lease) != request.lease):
                    raise StaleLease("document owner or revision lease has expired")
        if self._worker is None:
            if request.operation not in _SOURCE:
                raise StaleLease("document owner is no longer available")
            self._worker = DocumentWorker(self.root, startup_timeout=min(120., remaining()),
                                          cancellation=request.cancellation)
        values = json.loads(request.metadata)
        duration = remaining()
        request.call_started = True
        return self._worker.request(request.operation, payloads=request.payloads,
                                    timeout=duration, cancellation_grace=0,
                                    cancellation=request.cancellation,
                                    context=values["context"], **values["parameters"])

    def _run(self):
        try:
            while True:
                with self._condition:
                    self._expire_pending_locked()
                    while not self._queue and not self._stopping:
                        self._condition.wait()
                        self._expire_pending_locked()
                    if self._stopping:
                        break
                    request = self._queue.popleft()
                    self._active = request
                response = None
                error = None
                try:
                    response = self._execute(request)
                except BaseException as caught:
                    error = caught
                    # Structured authored failures leave their owner intact.
                    # Release may have applied before its cleanup failed; an
                    # uncertain acknowledgement invalidates the whole owner.
                    if (self._worker is not None and
                            (self._worker._closed
                             or (request.operation == "release" and request.call_started
                                 and not isinstance(caught, WorkerCancelled))
                             or not isinstance(caught, (ValueError, WorkerError, WorkerTimeout)))):
                        self._drop_worker()
                revision = None
                if response is not None:
                    try:
                        if request.operation in _SOURCE:
                            revision = _revision(response[0]["result"]["revision"])
                        elif request.operation == "release" and response[0]["result"] != {"released": True}:
                            raise ValueError("invalid release acknowledgement")
                    except (KeyError, TypeError, ValueError, StaleLease):
                        self._drop_worker()
                        error = WorkerError("document owner returned an invalid lease acknowledgement")
                        response = None
                while True:
                    with self._condition:
                        if time.monotonic() >= request.deadline:
                            request.expired = True
                            request.cancellation.set()
                        cancelled = request.cancellation.is_set()
                        # WorkerCancelled with an open worker proves its own
                        # pre-send check won. Preserve that healthy owner.
                        drop = (cancelled and self._worker is not None and
                                (response is not None or (request.call_started and not isinstance(error, WorkerCancelled))))
                        if not drop:
                            if cancelled:
                                response = None
                                error = (WorkerTimeout("document request exceeded its acceptance deadline")
                                         if request.expired or isinstance(error, WorkerTimeout)
                                         else WorkerCancelled("document request was cancelled"))
                            if response is not None:
                                if revision is not None:
                                    self._leases[revision.lease] = revision
                                elif request.operation == "release":
                                    self._leases.pop(request.lease.lease, None)
                            # Publication and accepted cancel are serialized.
                            self._complete_locked(request, value=response, error=error)
                            self._active = None
                            break
                    # A received success may already own an unreported lease.
                    # Never strand it or publish success after accepted cancel.
                    self._drop_worker()
                    response = None
                # An idle dispatcher does not retain the previous caller's
                # potentially large display response through thread locals.
                request = response = error = revision = None
        finally:
            try:
                self._drop_worker()
            finally:
                with self._condition:
                    self._stopping = True
                    self._queue.clear()
                    for request in tuple(self._pending.values()):
                        self._complete_locked(request, error=DispatcherClosed("document dispatcher stopped"))
                    self._active = None

    def shutdown(self, *, timeout=5):
        timeout = _seconds(timeout, 60)
        with self._condition:
            self._stopping = True
            for request in tuple(self._queue):
                self._queue.remove(request)
                request.cancellation.set()
                self._complete_locked(request, error=WorkerCancelled("document dispatcher shut down"))
            if self._active is not None:
                self._active.cancellation.set()
            self._condition.notify_all()
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise TimeoutError("document dispatcher is still completing owner shutdown")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.shutdown()
