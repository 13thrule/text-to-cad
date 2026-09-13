"""Explicit worker-owned rendering; no native/source work crosses this boundary.

A host constructs this service, binds it around its request execution, and closes
it before worker shutdown. Ordinary library calls never construct a hidden pool.
Only closed resolved packets and captured path authority reach the render thread.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import Future
from contextlib import contextmanager
from contextvars import Context, ContextVar, copy_context
from dataclasses import dataclass, field
from pathlib import Path
import threading
import sys

from .snapshot_core import (BatchSnapshotRenderer, SnapshotError, _capture_snapshot_job,
                            _finish_snapshot_cleanup, render_snapshot)
from .store.paths import _bind_store_root, store_root
from .snapshot_operation import packet_size_bound, resolved_packet

MAX_SERVICE_REQUESTS = 4
MAX_SERVICE_PACKET_BYTES = 64 * 1024 * 1024
SERVICE_START_SECONDS = 5
SERVICE_CLOSE_SECONDS = 25
SERVICE_JOIN_SECONDS = 5
MAX_PENDING_PROGRESS = 1024
_CURRENT: ContextVar[SnapshotService | None] = ContextVar("cadgen_snapshot_service", default=None)


_packet_size_bound = packet_size_bound


@contextmanager
def bind_snapshot_service(service):
    """A worker's explicit request scope; never inferred from environment flags."""
    token = _CURRENT.set(service)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def current_snapshot_service():
    return _CURRENT.get()


@dataclass(eq=False)
class _Ticket:
    receipt: Future = field(default_factory=Future)
    task: object = None
    cancelled: threading.Event = field(default_factory=threading.Event)
    size: int = 0


class _Relay:
    """Only value events cross threads; original callbacks run on caller context."""
    def __init__(self, progress, narrate):
        self.loop = asyncio.get_running_loop()
        self.context = copy_context()
        self.progress, self.narrator = progress, narrate
        self.streams = {"stdout": sys.stdout, "stderr": sys.stderr}
        self.failure = self.loop.create_future()
        self.pending = 0
        self.guard = threading.Lock()
        self.closed = False

    def send(self, method, *args, **kwargs):
        value = _capture_snapshot_job({"args": args, "kwargs": kwargs})
        with self.guard:
            if self.closed:
                return
            if self.pending >= MAX_PENDING_PROGRESS:
                raise SnapshotError("snapshot progress consumer exceeded its pending event limit")
            self.pending += 1
        self.loop.call_soon_threadsafe(self.deliver, method, value, context=self.context)

    def deliver(self, method, value):
        with self.guard:
            self.pending -= 1
            closed = self.closed
        if closed:
            return
        try:
            if method == "stream":
                stream, text = value["args"]
                self.streams[stream].write(text)
                self.streams[stream].flush()
            elif method == "narrate":
                if self.narrator is not None:
                    self.narrator(*value["args"])
            elif self.progress is not None:
                getattr(self.progress, method)(*value["args"], **value["kwargs"])
        except BaseException as exc:
            if not self.failure.done():
                self.failure.set_exception(exc)

    def phase(self, *args, **kwargs):
        self.send("phase", *args, **kwargs)

    def detail(self, *args, **kwargs):
        self.send("detail", *args, **kwargs)

    def advance(self, *args, **kwargs):
        self.send("advance", *args, **kwargs)

    def narrate(self, message):
        self.send("narrate", message)

    def close(self):
        with self.guard:
            self.closed = True
        if self.failure.done() and not self.failure.cancelled():
            self.failure.exception()
        else:
            self.failure.cancel()


class SnapshotService:
    """One host-owned loop/thread and browser, started lazily and explicitly closed."""
    def __init__(self):
        self._guard = threading.Lock()
        self._ready = threading.Event()
        self._thread = None
        self._loop = None
        self._run_lock = None
        self._renderer = None
        self._runtime_dir = None
        self._tickets = set()
        self._reserved_bytes = 0
        self._closing = False
        self._closed = False
        self._poison = None
        self._shutdown = None

    @property
    def poisoned(self):
        with self._guard:
            return self._poison is not None

    def _thread_main(self):
        # Deliberately no copied source, build or worker ContextVars on this loop.
        try:
            loop = asyncio.new_event_loop()
        except BaseException as exc:
            with self._guard:
                self._poison = exc
            self._ready.set()
            return
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._run_lock = asyncio.Lock()
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    def _start(self):
        with self._guard:
            if self._closed or self._closing:
                raise SnapshotError("the snapshot service is closing or closed")
            if self._poison is not None:
                raise SnapshotError("snapshot service teardown failed; its worker must reclaim it") from self._poison
            if self._thread is None:
                self._thread = threading.Thread(target=lambda: Context().run(self._thread_main),
                                                name="cadgen-snapshot", daemon=True)
                self._thread.start()
        if not self._ready.wait(SERVICE_START_SECONDS):
            raise SnapshotError("snapshot service loop did not start before its deadline")
        if self._loop is None:
            raise SnapshotError("snapshot service loop could not start") from self._poison

    def _cancel(self, ticket):
        ticket.cancelled.set()
        if self._loop is not None:
            def cancel():
                if ticket.task is not None and not ticket.task.done():
                    ticket.task.cancel()
            self._loop.call_soon_threadsafe(cancel, context=Context())

    async def _run(self, packet, runtime_dir, cache_root, encoder, relay):
        async with self._run_lock:
            if self._poison is not None:
                raise SnapshotError("snapshot service teardown failed; its worker must reclaim it") from self._poison
            from .snapshot_video import _bind_video_encoder
            try:
                if self._renderer is not None and self._runtime_dir != runtime_dir:
                    await self._renderer.close()
                    self._renderer = None
                if self._renderer is None:
                    self._renderer = BatchSnapshotRenderer(runtime_dir)
                    self._runtime_dir = runtime_dir
                with _bind_store_root(cache_root), _bind_video_encoder(encoder):
                    return await render_snapshot(packet, runtime_dir=runtime_dir, renderer=self._renderer,
                                                 progress=relay, narrate=relay.narrate)
            finally:
                if self._renderer is not None and self._renderer._shutdown_error is not None:
                    with self._guard:
                        self._poison = self._renderer._shutdown_error

    def _submit(self, packet, runtime_dir, cache_root, encoder, relay, cleanup=None):
        size = _packet_size_bound(packet)
        if size > MAX_SERVICE_PACKET_BYTES:
            raise SnapshotError("snapshot service packet exceeds its byte capacity")
        ticket = _Ticket(size=size)
        with self._guard:
            if len(self._tickets) >= MAX_SERVICE_REQUESTS or self._reserved_bytes + size > MAX_SERVICE_PACKET_BYTES:
                raise SnapshotError("snapshot service request capacity is full")
            if self._closing or self._closed or self._poison is not None:
                raise SnapshotError("snapshot service is unavailable and cannot accept work")
            self._tickets.add(ticket)
            self._reserved_bytes += size
        try:
            self._start()
            def begin():
                task = asyncio.create_task(self._run(packet, runtime_dir, cache_root, encoder, relay), context=Context())
                ticket.task = task
                def completed(done):
                    with self._guard:
                        self._tickets.discard(ticket)
                        self._reserved_bytes -= ticket.size
                    if done.cancelled():
                        ticket.receipt.cancel()
                    elif done.exception() is not None:
                        ticket.receipt.set_exception(done.exception())
                    else:
                        ticket.receipt.set_result(done.result())
                task.add_done_callback(completed, context=Context())
                if ticket.cancelled.is_set():
                    task.cancel()
            with self._guard:
                if self._closing:
                    raise SnapshotError("snapshot service is closing")
                if cleanup is not None:
                    cleanup.acknowledged = False
                self._loop.call_soon_threadsafe(begin, context=Context())
        except BaseException:
            with self._guard:
                self._tickets.discard(ticket)
                self._reserved_bytes -= ticket.size
            raise
        return ticket

    async def render(self, packet, *, runtime_dir, progress=None, narrate=None):
        """Admit a resolved request on its caller thread, then await a clean receipt."""
        packet = resolved_packet(packet)
        runtime_dir = Path(runtime_dir).resolve()
        cache_root = store_root().resolve()
        encoder = None
        if any(job.get("video") is not None for job in packet["jobs"]):
            from .snapshot_video import ffmpeg_binary
            encoder = str(Path(ffmpeg_binary()).resolve())
        return await self._render_captured(packet, runtime_dir, cache_root, encoder, progress, narrate)

    async def render_operation(self, operation, *, progress=None, narrate=None, cleanup=None):
        """A host-validated transport operation carries every path capability."""
        from .snapshot_operation import CLEANUP_SECONDS, RenderCleanup, normalize_operation
        if cleanup is not None:
            if type(cleanup) is not RenderCleanup:
                raise TypeError("snapshot cleanup requires an internal lifetime proof")
            cleanup.acknowledged = True  # No input consumer has been admitted yet.
        operation = normalize_operation(operation)
        async with asyncio.timeout_at(operation["deadline"] - CLEANUP_SECONDS):
            return await self._render_captured(operation["packet"], Path(operation["runtimeRoot"]),
                                               Path(operation["storeRoot"]), operation["encoder"], progress, narrate, cleanup)

    async def _render_captured(self, packet, runtime_dir, cache_root, encoder, progress, narrate, cleanup=None):
        relay = _Relay(progress, narrate)
        ticket = None
        wrapped = None
        try:
            ticket = self._submit(packet, runtime_dir, cache_root, encoder, relay, cleanup)
            wrapped = asyncio.wrap_future(ticket.receipt)
            done, _pending = await asyncio.wait((wrapped, relay.failure), return_when=asyncio.FIRST_COMPLETED)
            if relay.failure in done:
                relay.failure.result()
            return wrapped.result()
        except BaseException:
            if ticket is not None:
                self._cancel(ticket)
                if wrapped is None:
                    wrapped = asyncio.wrap_future(ticket.receipt)
                try:
                    await _finish_snapshot_cleanup(wrapped)
                except BaseException:
                    pass
            raise
        finally:
            relay.close()
            if cleanup is not None and ticket is not None and ticket.receipt.done() and not self.poisoned:
                cleanup.acknowledged = True

    async def _close_owned(self):
        with self._guard:
            tickets = tuple(self._tickets)
        tasks = []
        for ticket in tickets:
            ticket.cancelled.set()
            if ticket.task is not None and not ticket.task.done():
                ticket.task.cancel()
                tasks.append(ticket.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._renderer is not None:
            await self._renderer.close()
        self._renderer = None

    def close(self):
        """A synchronous host shutdown; success requires cleanup and a joined thread."""
        with self._guard:
            if self._closed:
                return
            self._closing = True
            thread = self._thread
        if thread is None:
            with self._guard:
                self._closed = True
            return
        if threading.current_thread() is thread:
            raise SnapshotError("snapshot service must be closed by its host thread")
        try:
            if not self._ready.wait(SERVICE_START_SECONDS):
                raise SnapshotError("snapshot service loop did not become ready for shutdown")
            if self._shutdown is None or self._shutdown.done():
                self._shutdown = asyncio.run_coroutine_threadsafe(self._close_owned(), self._loop)
            self._shutdown.result(timeout=SERVICE_CLOSE_SECONDS)
            self._loop.call_soon_threadsafe(self._loop.stop, context=Context())
            thread.join(SERVICE_JOIN_SECONDS)
            if thread.is_alive():
                raise SnapshotError("snapshot service thread did not stop before its deadline")
        except BaseException as exc:
            with self._guard:
                self._poison = exc
            raise SnapshotError("snapshot service shutdown was not acknowledged; worker reclamation is required") from exc
        with self._guard:
            self._closed = True
