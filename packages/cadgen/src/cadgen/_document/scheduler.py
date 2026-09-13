"""Process-local request, publication-order and hierarchical admission authority.

One coordinator daemon must own every family sharing output paths. Tickets and
canonical-path claims are not a cross-process filesystem CAS. This module runs
no source, kernel, encoders, pools or threads. An owner dispatcher pulls work;
producers publish inside a short coordinator-locked scope and acknowledge the
exact bytes they successfully wrote. Cancellation cannot undo an acknowledged
write, so receipts survive cancellation or a later failure.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
import re
import threading
from typing import Iterator

from .resources import AdmissionDenied, Cancelled, ResourceAdmission, ResourceRequest
from .sources import CapturedInput


class QueueFull(RuntimeError):
    pass


class PublicationConflict(RuntimeError):
    pass


class RequestStateError(RuntimeError):
    pass


class State(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    GEOMETRY_READY = "geometry_ready"
    EXPORTS_COMPLETE = "exports_complete"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class Request:
    ticket: int
    family: str
    document_key: str
    source: CapturedInput
    function: str
    outputs: tuple[Path, ...]
    preview: bool
    resources: ResourceRequest


@dataclass(frozen=True)
class Invocation:
    ticket: int
    sequence: int
    source: CapturedInput
    function: str


@dataclass(frozen=True)
class Receipt:
    ticket: int
    sequence: int
    path: Path
    digest: str | None
    publication_sequence: int


@dataclass(frozen=True)
class Facts:
    request: Request
    state: State
    finished: bool
    geometry_id: str | None
    exports_complete: bool
    cancellation_requested: bool
    required_outputs: tuple[tuple[int, Path], ...]
    receipts: tuple[Receipt, ...]
    completed_invocations: tuple[int, ...]
    error: str | None


@dataclass
class _Entry:
    request: Request
    state: State = State.QUEUED
    finished: bool = False
    cancellation: threading.Event = field(default_factory=threading.Event)
    invocations: dict[int, Invocation] = field(default_factory=dict)
    geometry: dict[int, str] = field(default_factory=dict)
    outputs: dict[int, tuple[Path, ...]] = field(default_factory=dict)
    receipts: list[Receipt] = field(default_factory=list)
    published: set[tuple[int, Path]] = field(default_factory=set)
    completed: set[int] = field(default_factory=set)
    problem: BaseException | None = None


def _name(value, label):
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _source(value):
    if type(value) is not CapturedInput:
        raise TypeError("requests require already captured source bytes")
    return CapturedInput(value.path, value.data, value.digest)


def _paths(values):
    # Resolve once when a claim is bound. Producers receive this frozen target,
    # so changing cwd or a symlink later cannot silently change the claimed path.
    return tuple(dict.fromkeys(Path(os.path.normcase(str(Path(path).resolve())))
                               for path in values))


class Publication:
    """One producer acknowledgement; it does not encode or inspect a file."""
    def __init__(self, job, sequence, path):
        self._job, self.sequence, self.path = job, sequence, path
        self._active = True
        self.receipt: Receipt | None = None

    def acknowledge(self, digest: str | None) -> Receipt:
        self._job._check_owner()
        if not self._active or self.receipt is not None:
            raise RequestStateError("publication acknowledgement is no longer available")
        if digest is not None and (type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
            raise ValueError("publication acknowledgement requires an exact SHA-256 or verified absence")
        entry = self._job._entry
        self.receipt = Receipt(self._job.request.ticket, self.sequence, self.path, digest,
                               len(entry.receipts) + 1)
        # Record immediately: an acknowledged external write is a fact even if
        # the producer or cancellation check subsequently raises.
        entry.receipts.append(self.receipt)
        entry.published.add((self.sequence, self.path))
        return self.receipt


class Job:
    """Owner-thread dispatch lease, with synchronous child invocations.

    The coordinator reserves the whole job globally. Native documents borrow
    from ``admission``, whose capacity is exactly that reservation, rather than
    reserving the same CPU slot from the global authority a second time. Child
    calls share this bounded admission and never wait for another family slot.
    """
    def __init__(self, coordinator, entry, reservation):
        self._coordinator, self._entry, self._reservation = coordinator, entry, reservation
        self.request = entry.request
        self.cancellation = entry.cancellation
        self._thread = threading.get_ident()
        self._stack = [0]
        self._next_sequence = 1
        resources = self.request.resources
        self.admission = ResourceAdmission(cpu_slots=resources.cpu_slots,
                                            native_bytes=resources.native_bytes,
                                            derived_bytes=resources.derived_bytes)

    @property
    def invocation(self) -> Invocation:
        return self._entry.invocations[self._stack[-1]]

    def _check_owner(self):
        self._coordinator._check_process()
        if threading.get_ident() != self._thread:
            raise RequestStateError("a dispatched job belongs to its owner thread")
        if self._entry.finished:
            raise RequestStateError("the dispatched job is already finished")

    def checkpoint(self) -> None:
        self._check_owner()
        if self.cancellation.is_set():
            raise Cancelled("document request was cancelled")
        if self._entry.problem is not None:
            raise self._entry.problem

    def bind_outputs(self, outputs) -> tuple[Path, ...]:
        self._check_owner()
        paths = _paths(outputs)
        with self._coordinator._lock:
            self.checkpoint()
            self._coordinator._bind(self._entry, self.invocation.sequence, paths)
        return paths

    def geometry_ready(self, geometry_id: str) -> None:
        _name(geometry_id, "geometry identity")
        with self._coordinator._lock:
            self.checkpoint()
            sequence = self.invocation.sequence
            if sequence in self._entry.geometry:
                raise RequestStateError("invocation geometry was already published")
            self._entry.geometry[sequence] = geometry_id
            if sequence == 0:
                self._entry.state = State.GEOMETRY_READY

    @contextmanager
    def child(self, source: CapturedInput, function: str, *, outputs=()) -> Iterator[Invocation]:
        self.checkpoint()
        source, function, paths = _source(source), _name(function, "function"), _paths(outputs)
        with self._coordinator._lock:
            if self._coordinator._publishing:
                raise RequestStateError("child calls cannot begin inside publication")
            sequence = self._next_sequence
            self._next_sequence += 1
            invocation = Invocation(self.request.ticket, sequence, source, function)
            self._entry.invocations[sequence] = invocation
            self._entry.outputs[sequence] = ()
            self._coordinator._bind(self._entry, sequence, paths)
            self._stack.append(sequence)
        try:
            yield invocation
            with self._coordinator._lock:
                self.checkpoint()
                self._coordinator._validate_completion(self._entry, sequence)
                self._entry.completed.add(sequence)
        except BaseException as error:
            self._entry.problem = self._entry.problem or error
            raise
        finally:
            self._stack.pop()

    @contextmanager
    def publication(self, path) -> Iterator[Publication]:
        """Guard one completed output; grouped products use publications()."""
        with self.publications((path,)) as publications:
            yield publications[0]

    @contextmanager
    def publications(self, paths) -> Iterator[tuple[Publication, ...]]:
        """Claim a complete output group before any final filesystem effects.

        Encoding and staging happen before this scope. All claims are checked
        while holding one coordinator lock. Each completed file or absence is
        acknowledged immediately; partial failures retain those historical facts
        and fail the invocation. This is not a multi-file filesystem transaction.
        """
        self._check_owner()
        paths = _paths(paths)
        if not paths or len(paths) > 1024:
            raise ValueError("publication requires a bounded nonempty output group")
        coordinator = self._coordinator
        with coordinator._lock:
            self.checkpoint()
            sequence = self.invocation.sequence
            if any(path not in self._entry.outputs[sequence] for path in paths):
                raise RequestStateError("publication path was not bound to this invocation")
            if sequence not in self._entry.geometry:
                raise RequestStateError("publication requires invocation geometry")
            if coordinator._publishing:
                raise RequestStateError("publication scopes cannot be nested")
            publications = tuple(Publication(self, sequence, path) for path in paths)
            try:
                for path in paths:
                    coordinator._check_claim(self._entry, sequence, path)
                coordinator._publishing = True
                yield publications
                if any(publication.receipt is None for publication in publications):
                    raise RequestStateError("producer did not acknowledge every completed output")
                self.checkpoint()
            except BaseException as error:
                self._entry.problem = self._entry.problem or error
                raise
            finally:
                for publication in publications:
                    publication._active = False
                coordinator._publishing = False

    def finish(self) -> Facts:
        self._check_owner()
        return self._coordinator._finish(self)

    def __enter__(self):
        try:
            self.checkpoint()
        except BaseException as error:
            self._coordinator._finish(self, error)
            raise
        return self

    def __exit__(self, kind, error, traceback):
        if not self._entry.finished:
            self._coordinator._finish(self, error)
        return False


class Coordinator:
    """Single-process authority above all native families.

    Queue and unacknowledged record counts are bounded. Call ``forget`` after
    recording a terminal result durably; saturation rejects new acceptance
    explicitly and never drops an accepted explicit build. Output high-water
    claims survive forgetting while any older live request could still publish.
    """
    def __init__(self, *, admission: ResourceAdmission | None = None,
                 max_queued: int = 128, max_records: int = 1024):
        if any(type(value) is not int or value < 1 for value in (max_queued, max_records)):
            raise ValueError("scheduler capacities must be positive integers")
        self.admission = admission if admission is not None else ResourceAdmission()
        self.max_queued, self.max_records = max_queued, max_records
        self._pid = os.getpid()
        self._lock = threading.RLock()
        self._next_ticket = 1
        self._entries: dict[int, _Entry] = {}
        self._queue: deque[int] = deque()
        self._active: dict[str, Job] = {}
        self._claims: dict[Path, int] = {}
        self._publishing = False

    def _check_process(self):
        if os.getpid() != self._pid:
            raise RequestStateError("scheduler authority cannot be copied into another process")

    def accept(self, family: str, document_key: str, source: CapturedInput,
               function: str, *, outputs=(), preview: bool = False,
               resources: ResourceRequest = ResourceRequest(),
               cancellation: threading.Event | None = None) -> Request:
        self._check_process()
        family, document_key = _name(family, "family"), _name(document_key, "document key")
        source, function, paths = _source(source), _name(function, "function"), _paths(outputs)
        if type(preview) is not bool or type(resources) is not ResourceRequest:
            raise TypeError("preview and resource declarations must be typed values")
        if cancellation is not None and not isinstance(cancellation, threading.Event):
            raise TypeError("request cancellation requires a threading Event")
        demand = (resources.cpu_slots, resources.native_bytes, resources.derived_bytes)
        if any(demand > capacity for demand, capacity in zip(demand, self.admission.capacity)):
            raise AdmissionDenied("request cannot fit the coordinator resource capacity")
        with self._lock:
            if self._publishing:
                raise RequestStateError("acceptance cannot reenter a publication scope")
            coalesced = [ticket for ticket in self._queue
                         if preview and self._entries[ticket].request.preview
                         and self._entries[ticket].request.document_key == document_key]
            if len(self._queue) - len(coalesced) >= self.max_queued or len(self._entries) >= self.max_records:
                raise QueueFull("document request capacity is exhausted")
            ticket = self._next_ticket
            self._next_ticket += 1
            request = Request(ticket, family, document_key, source, function, paths, preview, resources)
            entry = _Entry(request)
            if cancellation is not None:
                entry.cancellation = cancellation
            entry.invocations[0] = Invocation(ticket, 0, source, function)
            entry.outputs[0] = ()
            self._entries[ticket] = entry
            self._bind(entry, 0, paths)
            for old in coalesced:
                previous = self._entries[old]
                previous.state, previous.finished = State.SUPERSEDED, True
                self._queue.remove(old)
            self._queue.append(ticket)
            return request

    def _bind(self, entry, sequence, paths):
        if self._publishing:
            raise RequestStateError("output binding cannot reenter a publication scope")
        entry.outputs[sequence] = tuple(dict.fromkeys((*entry.outputs[sequence], *paths)))
        # Invocation order is provenance, not a fence: an ancestor may publish
        # after its synchronous child returns, including to the same path.
        claim = entry.request.ticket
        for path in paths:
            previous = self._claims.get(path)
            if previous is not None and previous > claim:
                error = PublicationConflict(f"output belongs to later accepted work: {path}")
                entry.problem = entry.problem or error
                raise error
        for path in paths:
            self._claims[path] = claim

    def _check_claim(self, entry, sequence, path):
        if self._claims.get(path) != entry.request.ticket:
            raise PublicationConflict(f"output belongs to later accepted work: {path}")

    def pull(self, family: str, *, ticket: int | None = None) -> Job | None:
        """Dispatch the family's oldest request, optionally requiring its ticket.

        Synchronous callers must not accidentally execute previously queued
        work. A ticket mismatch leaves both requests queued in FIFO order.
        """
        self._check_process()
        if ticket is not None and (type(ticket) is not int or ticket < 1):
            raise ValueError("a dispatch ticket must be a positive integer")
        with self._lock:
            if family in self._active:
                return None
            oldest = next((candidate for candidate in self._queue
                           if self._entries[candidate].request.family == family), None)
            if oldest is None or (ticket is not None and oldest != ticket):
                return None
            entry = self._entries[oldest]
            reservation = self.admission.admit(entry.request.resources,
                                                cancellation=entry.cancellation)
            try:
                reservation.__enter__()
            except AdmissionDenied:
                return None  # FIFO request remains accepted and queued.
            self._queue.remove(oldest)
            entry.state = State.RUNNING
            job = Job(self, entry, reservation)
            self._active[family] = job
            return job

    def cancel(self, ticket: int) -> bool:
        self._check_process()
        with self._lock:
            entry = self._entries[ticket]
            if entry.finished:
                return False
            entry.cancellation.set()
            if entry.state is State.QUEUED:
                self._queue.remove(ticket)
                entry.state, entry.finished = State.CANCELLED, True
            return True

    def snapshot(self, ticket: int) -> Facts:
        self._check_process()
        with self._lock:
            entry = self._entries[ticket]
            return Facts(entry.request, entry.state, entry.finished, entry.geometry.get(0),
                         entry.state is State.EXPORTS_COMPLETE, entry.cancellation.is_set(),
                         tuple((sequence, path) for sequence, paths in entry.outputs.items() for path in paths),
                         tuple(entry.receipts),
                         tuple(sorted(entry.completed)),
                         None if entry.problem is None else str(entry.problem))

    def _validate_completion(self, entry, sequence):
        if sequence not in entry.geometry:
            raise RequestStateError("request returned without declared geometry")
        for path in entry.outputs[sequence]:
            self._check_claim(entry, sequence, path)
            if (sequence, path) not in entry.published:
                raise RequestStateError(f"request returned without completed output: {path}")

    def _finish(self, job, error=None):
        job._check_owner()
        with self._lock:
            if self._publishing:
                raise RequestStateError("finish cannot run inside publication")
            if job._stack != [0] or job.admission.used != (0, 0, 0):
                raise RequestStateError("finish requires closed child calls and released operator reservations")
            entry = job._entry
            problem = error or entry.problem
            try:
                if problem is None:
                    job.checkpoint()
                    for sequence in entry.invocations:
                        if sequence not in entry.completed:
                            self._validate_completion(entry, sequence)
                    # Same-request writes follow actual synchronous publication
                    # order, including ancestors after children. A later
                    # accepted request still prevents overall success.
                    latest = {path: sequence for sequence, paths in entry.outputs.items()
                              for path in paths}
                    for path, sequence in latest.items():
                        self._check_claim(entry, sequence, path)
            except BaseException as failure:
                problem = failure
            try:
                job._reservation.__exit__(None if problem is None else type(problem), problem, None)
            except BaseException as failure:
                problem = problem or failure
            self._active.pop(entry.request.family)
            entry.finished = True
            entry.problem = problem
            if problem is None:
                entry.completed.add(0)
                entry.state = State.GEOMETRY_READY if entry.request.preview and not any(entry.outputs.values()) else State.EXPORTS_COMPLETE
            elif isinstance(problem, Cancelled):
                entry.state = State.CANCELLED
            elif isinstance(problem, PublicationConflict) and entry.request.preview:
                entry.state = State.SUPERSEDED
            else:
                entry.state = State.FAILED
            result = self.snapshot(entry.request.ticket)
            if error is None and problem is not None:
                raise problem
            return result

    def forget(self, ticket: int) -> None:
        self._check_process()
        with self._lock:
            if not self._entries[ticket].finished:
                raise RequestStateError("cannot forget unfinished accepted work")
            del self._entries[ticket]
            floor = min((ticket for ticket, entry in self._entries.items() if not entry.finished),
                        default=self._next_ticket)
            self._claims = {path: claim for path, claim in self._claims.items() if claim >= floor}
