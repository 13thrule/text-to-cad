"""Retained single-owner native document prototype.

Source replay is external to this module. The caller supplies actual normalized
inputs; a logical feature label never substitutes for those evaluation inputs.
Only engine adapters may call evaluate/query/derive. Arbitrary Python and raw
native access belong in the transaction's private escape arena.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from threading import Event, RLock, get_ident
from types import MappingProxyType
from typing import Any, Callable, Mapping
from uuid import uuid4

from .identities import EvaluationIdentity, EvaluationKey, LogicalIdentity, allocation_provenance, normalize
from .native import NativeEscapeArena, NativeResult, TopologyHistory, copy_many, copy_shape
from .resources import Cancelled, ResourceAdmission, ResourceRequest
from .roots import RootNode, root_handles, validate_root


class Mutation(Enum):
    PRIVATE_INPUTS = "private_inputs"
    READ_ONLY = "read_only"


@dataclass(frozen=True)
class OperatorSpec:
    name: str
    version: str = "1"
    mutation: Mutation = Mutation.PRIVATE_INPUTS
    resources: ResourceRequest = field(default_factory=ResourceRequest)
    # Trusted engine adapters only: all inputs are immutable parameters, the
    # callback has no effects or external native reads, and its fresh output
    # has never been exposed to Python. An empty inputs tuple alone proves none
    # of these properties. Ordinary operators remain conservative after escape.
    closed_constructor: bool = False

    def __post_init__(self) -> None:
        if not self.name or not self.version:
            raise ValueError("an operator requires a name and implementation version")
        if not isinstance(self.mutation, Mutation):
            raise TypeError("operator mutation must be a Mutation member")
        if type(self.closed_constructor) is not bool:
            raise TypeError("closed_constructor must be a bool")
        if self.closed_constructor and self.mutation is not Mutation.READ_ONLY:
            raise ValueError("a closed constructor must be read-only")


@dataclass(frozen=True)
class GeometryHandle:
    owner_id: str
    evaluation_id: EvaluationIdentity
    prototype_id: str
    allocation_id: str


class RevisionState(Enum):
    GEOMETRY_READY = "geometry_ready"
    EXPORTS_COMPLETE = "exports_complete"
    FAILED = "failed"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class Revision:
    revision_id: int
    source_identity: str
    features: Mapping[LogicalIdentity, GeometryHandle]
    evaluations: tuple[GeometryHandle, ...]
    required_exports: tuple[str, ...]
    # Authoritative returned geometry; evaluations also include temporary tools.
    root: RootNode | None = None
    # None means coverage has not been established. An empty tuple attests that
    # the bound root represents all supported authored metadata. Publishers must
    # not silently discard fields while the frontend's coverage is incomplete.
    unrepresented_metadata: tuple[str, ...] | None = None
    # Snapshot IDs locate immutable results. Save ordering instead follows the
    # request that executed Python, then publication order within that request.
    _request_sequence: int = 0
    _publication_sequence: int = 0
    _entry_key: str | None = None


@dataclass
class EvaluationStats:
    computed: int = 0
    reused: int = 0
    native_copies: int = 0
    derived_computed: int = 0
    derived_reused: int = 0
    queries: int = 0


@dataclass(frozen=True)
class _Prototype:
    handle: GeometryHandle
    key: EvaluationKey
    shape: Any
    history: TopologyHistory
    dependencies: tuple[GeometryHandle, ...]
    alias_sources: tuple[Any, ...] = ()
    auxiliary: Any = None


@dataclass(frozen=True)
class _Allocation:
    handle: GeometryHandle
    inputs: tuple[GeometryHandle, ...] = ()


class SupersededRevision(RuntimeError):
    def __init__(self, revision: Revision) -> None:
        self.revision = revision
        super().__init__(f"revision {revision.revision_id} cannot replace a newer geometry head")


class ExportConflict(RuntimeError):
    pass


class RevisionPin:
    def __init__(self, document: Document, revision: Revision) -> None:
        self.document = document
        self.revision = revision
        self._released = False

    @property
    def revision_id(self) -> int:
        return self.revision.revision_id

    def __enter__(self) -> RevisionPin:
        if self._released:
            raise RuntimeError("revision pin has already been released")
        return self

    def release(self) -> None:
        with self.document._lock:
            if not self._released:
                self.document._pins[self.revision_id] -= 1
                self._released = True

    def __exit__(self, *exc) -> None:
        self.release()


def _assert_value_result(value: Any) -> None:
    """Reject ordinary pointer containers at the trusted scalar query boundary."""
    if hasattr(value, "ShapeType") and hasattr(value, "IsNull"):
        raise TypeError("native query results require a managed handle or private escape")
    wrapped = getattr(value, "wrapped", None)
    if hasattr(wrapped, "ShapeType"):
        raise TypeError("native query results require a managed handle or private escape")
    if isinstance(value, (tuple, list)):
        for item in value:
            _assert_value_result(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _assert_value_result(key)
            _assert_value_result(item)


def _validate_metadata_coverage(value: tuple[str, ...] | None) -> None:
    if value is not None and (type(value) is not tuple
                             or any(type(field) is not str or not field for field in value)):
        raise TypeError("metadata coverage requires an immutable tuple of nonempty field names or None")


def _publication_order(revision: Revision) -> tuple[int, int]:
    return revision._request_sequence, revision._publication_sequence


class Document:
    """A single native owner with immutable revisions and exact reader leases.

    This P1 implementation is resident only. Resource reservations bound declared
    simultaneous work; explicit collection bounds retained revisions by leases.
    It does not claim crash recovery, native RSS accounting, or disk durability.
    """
    def __init__(self, document_id: str, *, runtime: Any = (),
                 admission: ResourceAdmission | None = None) -> None:
        self.document_id = document_id
        self.owner_id = uuid4().hex
        self.runtime = runtime
        normalize(runtime)
        self.admission = admission or ResourceAdmission()
        self._owner_thread = get_ident()
        self._lock = RLock()
        self._next_revision = 0
        self._next_request_sequence = 0
        self._next_publication_sequence = 0
        self._head: int | None = None
        self._entry_heads: dict[str, int] = {}
        self._prototypes: dict[str, _Prototype] = {}
        self._allocations: dict[str, _Allocation] = {}
        self._revisions: dict[int, Revision] = {}
        self._states: dict[int, RevisionState] = {}
        self._completed_exports: dict[int, set[str]] = {}
        self._pins: dict[int, int] = {}
        self._output_claims: dict[str, tuple[int, int]] = {}
        self._active: dict[int, RevisionTransaction] = {}
        self._derivations: dict[tuple, Any] = {}

    def _assert_owner(self) -> None:
        if get_ident() != self._owner_thread:
            raise RuntimeError("native document work must run in its owning thread")

    @property
    def head(self) -> Revision | None:
        with self._lock:
            return self._revisions.get(self._head)

    def entry_head(self, entry_key: str) -> Revision | None:
        """The accepted result for one declared entry in this native family."""
        if type(entry_key) is not str or not entry_key:
            raise ValueError("a family entry requires a nonempty string key")
        with self._lock:
            return self._revisions.get(self._entry_heads.get(entry_key))

    @property
    def prototype_count(self) -> int:
        return len(self._prototypes)

    def state(self, revision_id: int) -> RevisionState:
        with self._lock:
            return self._states[revision_id]

    def begin(self, source_identity: str = "", *, required_exports=()) -> RevisionTransaction:
        self._assert_owner()
        with self._lock:
            self._next_revision += 1
            self._next_request_sequence += 1
            tx = RevisionTransaction(self, self._next_revision, source_identity,
                                     tuple(str(path) for path in required_exports),
                                     self._next_request_sequence)
            self._active[tx.revision_id] = tx
            return tx

    def _accept_result(self, revision: Revision) -> bool:
        """Install a root or child snapshot under the caller-held owner lock."""
        self._revisions[revision.revision_id] = revision
        self._completed_exports[revision.revision_id] = set()
        entry = revision._entry_key
        previous_id = self._head if entry is None else self._entry_heads.get(entry)
        order = _publication_order(revision)
        stale = previous_id is not None and order < _publication_order(self._revisions[previous_id])
        self._states[revision.revision_id] = (RevisionState.SUPERSEDED if stale
                                            else RevisionState.GEOMETRY_READY)
        if not stale:
            if entry is None:
                self._head = revision.revision_id
            else:
                self._entry_heads[entry] = revision.revision_id
            for path in revision.required_exports:
                # A different entry can already hold a newer request's claim.
                # Geometry publication must not lower that output-path fence.
                self._output_claims[path] = max(self._output_claims.get(path, order), order)
        return stale

    def pin(self, revision_id: int | None = None) -> RevisionPin:
        with self._lock:
            selected = self._head if revision_id is None else revision_id
            if selected not in self._revisions:
                raise KeyError(f"document revision is unavailable: {selected}")
            revision = self._revisions[selected]
            self._pins[selected] = self._pins.get(selected, 0) + 1
            return RevisionPin(self, revision)

    def complete_exports(self, revision_id: int, paths=()) -> None:
        """Record only already-completed obligations; file writers stay explicit."""
        with self._lock:
            revision = self._revisions[revision_id]
            completed = {str(path) for path in paths}
            unknown = completed - set(revision.required_exports)
            if unknown:
                raise ValueError(f"undeclared revision exports: {sorted(unknown)}")
            self._completed_exports[revision_id].update(completed)
            if self._states[revision_id] in {RevisionState.FAILED, RevisionState.SUPERSEDED}:
                return
            if set(revision.required_exports) <= self._completed_exports[revision_id]:
                self._states[revision_id] = RevisionState.EXPORTS_COMPLETE

    def fail(self, revision_id: int) -> None:
        with self._lock:
            self._states[revision_id] = RevisionState.FAILED

    def publish_export(self, pin: RevisionPin, path: str, writer: Callable[[], Any]) -> Any:
        """Serialize one output path and reject older accepted-save conflicts.

        The writer owns atomic bytes/sidecar publication. Superseded explicit
        calls receive a conflict; they never claim success with skipped exports.
        """
        if pin.document is not self or pin._released:
            raise ValueError("export requires a live pin of this document")
        path = str(path)
        with self._lock:
            if path not in pin.revision.required_exports:
                raise ValueError("export path was not declared by this revision")
            order = _publication_order(pin.revision)
            if self._output_claims.get(path, order) > order:
                raise ExportConflict(f"a newer accepted revision owns output {path}")
            with self.admission.admit(ResourceRequest(kind="export")):
                result = writer()
            self.complete_exports(pin.revision_id, (path,))
            return result

    def history(self, handle: GeometryHandle) -> TopologyHistory:
        return self._get(handle).history

    def _get(self, handle: GeometryHandle) -> _Prototype:
        if not isinstance(handle, GeometryHandle) or handle.owner_id != self.owner_id:
            raise ValueError("geometry handle belongs to another native owner")
        prototype = self._prototypes.get(handle.prototype_id)
        allocation = self._allocations.get(handle.allocation_id)
        if (prototype is None or prototype.handle.evaluation_id != handle.evaluation_id
                or allocation is None or allocation.handle != handle):
            raise ValueError("geometry prototype is no longer retained")
        return prototype

    def collect(self, *, keep_revisions: int = 2) -> tuple[int, int]:
        """Reclaim only unreachable resident results; pins and transactions win."""
        self._assert_owner()
        if keep_revisions < 0:
            raise ValueError("keep_revisions cannot be negative")
        with self._lock:
            retain = set(sorted(self._revisions, reverse=True)[:keep_revisions])
            retain.update(k for k, count in self._pins.items() if count)
            if self._head is not None:
                retain.add(self._head)
            retain.update(self._entry_heads.values())
            # Incomplete explicit exports remain obligations, including superseded ones.
            retain.update(k for k, r in self._revisions.items()
                          if set(r.required_exports) - self._completed_exports[k]
                          and self._states[k] != RevisionState.FAILED)
            removed_revisions = set(self._revisions) - retain
            for key in removed_revisions:
                del self._revisions[key], self._states[key], self._completed_exports[key]
                self._pins.pop(key, None)
            roots = [h for r in self._revisions.values() for h in r.evaluations]
            roots += [h for r in self._revisions.values() if r.root is not None
                      for h in root_handles(r.root)]
            roots += [h for tx in self._active.values() for h in tx._handles.values()]
            reachable = set()
            reachable_allocations = set()
            while roots:
                handle = roots.pop()
                if handle.allocation_id not in reachable_allocations:
                    reachable_allocations.add(handle.allocation_id)
                    reachable.add(handle.prototype_id)
                    roots.extend(self._allocations[handle.allocation_id].inputs)
            removed_prototypes = set(self._prototypes) - reachable
            for key in removed_prototypes:
                del self._prototypes[key]
            self._allocations = {k: a for k, a in self._allocations.items()
                                 if k in reachable_allocations}
            self._derivations = {k: v for k, v in self._derivations.items() if k[0] in reachable}
            products = getattr(self, "_step_products", None)
            if products is not None:
                products.prune(self)
            imports = getattr(self, "_step_imports", None)
            if imports is not None:
                imports.prune(self)
            return len(removed_revisions), len(removed_prototypes)


class RevisionTransaction:
    def __init__(self, document: Document, revision_id: int, source_identity: str,
                 required_exports: tuple[str, ...], request_sequence: int) -> None:
        self.document = document
        self.revision_id = revision_id
        self.source_identity = source_identity
        self.required_exports = required_exports
        self._request_sequence = request_sequence
        self.stats = EvaluationStats()
        self.cancellation = Event()
        self._handles: dict[str, GeometryHandle] = {}
        self._features: dict[LogicalIdentity, GeometryHandle] = {}
        self._root: RootNode | None = None
        self._unrepresented_metadata: tuple[str, ...] | None = None
        self._closed = False
        self._volatile = 0
        self.escape_arena = NativeEscapeArena(
            self._arena_snapshot, self._validate_handle,
            lambda: self.document.admission.admit(ResourceRequest(kind="escape"),
                                                  cancellation=self.cancellation),
            self._count_arena_copy)

    def _count_arena_copy(self) -> None:
        self.stats.native_copies += 1

    def _check(self) -> None:
        self.document._assert_owner()
        if self._closed:
            raise RuntimeError("document revision transaction is closed")
        if self.cancellation.is_set():
            raise Cancelled("document revision was cancelled")

    def _validate_handle(self, handle: GeometryHandle) -> _Prototype:
        self._check()
        prototype = self.document._get(handle)
        self._handles[handle.allocation_id] = handle
        return prototype

    def _arena_snapshot(self) -> dict[str, Any]:
        self._check()
        return self._allocation_snapshot(tuple(self._handles.values()))

    def _allocation_snapshot(self, handles) -> dict[str, Any]:
        """Ownership descriptors for these inputs and their real dependencies."""
        result = {}
        def include(handle):
            if handle.allocation_id in result:
                return
            allocation = self.document._allocations[handle.allocation_id]
            prototype = self.document._get(handle)
            parents = tuple((h.allocation_id, source) for h, source in
                            zip(allocation.inputs, prototype.alias_sources))
            result[handle.allocation_id] = (prototype.shape, parents)
            for parent in allocation.inputs:
                include(parent)
        for handle in handles:
            include(handle)
        return result

    def _input_alias_provenance(self, handles) -> tuple:
        return allocation_provenance(handles, self.document._allocations)

    def _nonce(self) -> str:
        self._volatile += 1
        return f"{self.document.owner_id}:{self.revision_id}:{self._volatile}"

    def _record(self, handle: GeometryHandle, logical_id=None) -> GeometryHandle:
        self._handles[handle.allocation_id] = handle
        if logical_id is not None:
            logical_id = logical_id if isinstance(logical_id, LogicalIdentity) else LogicalIdentity(str(logical_id))
            if logical_id in self._features and self._features[logical_id] != handle:
                raise ValueError(f"ambiguous duplicate logical feature: {logical_id.value}")
            self._features[logical_id] = handle
        return handle

    def _allocate(self, prototype: _Prototype, inputs: tuple[GeometryHandle, ...]) -> GeometryHandle:
        handle = GeometryHandle(self.document.owner_id, prototype.handle.evaluation_id,
                                prototype.handle.prototype_id, self._nonce())
        self.document._allocations[handle.allocation_id] = _Allocation(handle, inputs)
        return handle

    def evaluate(self, spec: OperatorSpec, parameters: Any,
                 inputs: tuple[GeometryHandle, ...],
                 compute: Callable[[tuple[Any, ...], NativeEscapeArena], NativeResult],
                 *, logical_id=None) -> GeometryHandle:
        self._check()
        inputs = tuple(inputs)
        if spec.closed_constructor and inputs:
            raise ValueError("a closed constructor cannot consume geometry handles")
        prototypes = tuple(self._validate_handle(h) for h in inputs)
        escaped = self.escape_arena.active and not spec.closed_constructor
        key = EvaluationKey.create(spec.name, spec.version, parameters,
                                   tuple(h.evaluation_id for h in inputs),
                                   (self.document.runtime, spec.mutation.value,
                                    spec.closed_constructor),
                                   self._nonce() if escaped else "",
                                   alias_provenance=self._input_alias_provenance(inputs))
        prototype_id = key.identity.value
        existing = self.document._prototypes.get(prototype_id)
        if existing is not None:
            self.stats.reused += 1
            return self._record(self._allocate(existing, inputs), logical_id)
        native_inputs = (tuple(self.escape_arena.native(h) for h in inputs) if escaped
                         else tuple(p.shape for p in prototypes))
        with self.document.admission.admit(spec.resources, cancellation=self.cancellation):
            if spec.mutation is Mutation.PRIVATE_INPUTS:
                if escaped:
                    # Current private shapes already embody their real alias
                    # relationships; one copier preserves those relationships.
                    native_inputs = copy_many(native_inputs)
                    self.stats.native_copies += len(native_inputs)
                else:
                    # Retained prototypes may stand for independent authored
                    # allocations. A plain compound copy would merge them.
                    private_inputs = NativeEscapeArena(
                        lambda: self._allocation_snapshot(inputs), on_copy=self._count_arena_copy)
                    native_inputs = tuple(private_inputs.native(handle) for handle in inputs)
            result = compute(native_inputs, self.escape_arena)
            if not isinstance(result, NativeResult):
                raise TypeError("document operator must return NativeResult")
            if result.shape is None or result.shape.IsNull():
                raise ValueError("document operator returned null geometry")
            auxiliary = _freeze_auxiliary(result.auxiliary)
            # Escaped outputs remain mutable in this execution; retained snapshots do not.
            retained = copy_shape(result.shape) if escaped else result.shape
            self.stats.native_copies += int(escaped)
        handle = GeometryHandle(self.document.owner_id, key.identity, prototype_id, self._nonce())
        self.document._prototypes[prototype_id] = _Prototype(
            handle, key, retained, result.history, inputs,
            native_inputs if spec.mutation is Mutation.READ_ONLY and not escaped else (),
            auxiliary)
        self.document._allocations[handle.allocation_id] = _Allocation(handle, inputs)
        if escaped:
            self.escape_arena.adopt(handle, result.shape)
        self.stats.computed += 1
        return self._record(handle, logical_id)

    def capture(self, shape: Any, *, logical_id=None) -> GeometryHandle:
        """Snapshot an external/opaque result; never infer pure native identity."""
        self._check()
        key = EvaluationKey.create("opaque", "1", (), runtime=self.document.runtime,
                                   volatility=self._nonce())
        with self.document.admission.admit(ResourceRequest(), cancellation=self.cancellation):
            retained = copy_shape(shape)
        handle = GeometryHandle(self.document.owner_id, key.identity, key.identity.value, self._nonce())
        self.document._prototypes[handle.prototype_id] = _Prototype(
            handle, key, retained, TopologyHistory(reason="opaque native capture"), ())
        self.document._allocations[handle.allocation_id] = _Allocation(handle)
        if self.escape_arena.active:
            self.escape_arena.adopt(handle, shape)
        self.stats.computed += 1
        self.stats.native_copies += 1
        return self._record(handle, logical_id)

    def query(self, handle: GeometryHandle, fn: Callable[[Any], Any]) -> Any:
        prototype = self._validate_handle(handle)
        native = self.escape_arena.native(handle) if self.escape_arena.active else prototype.shape
        with self.document.admission.admit(ResourceRequest(kind="query"),
                                          cancellation=self.cancellation):
            result = fn(native)
            _assert_value_result(result)
        self.stats.queries += 1
        return result

    def derive(self, handle: GeometryHandle, kind: str, parameters: Any,
               compute: Callable[[Any], Any]) -> Any:
        """Derive immutable data on a private copy (meshing mutates triangulation)."""
        prototype = self._validate_handle(handle)
        key = (handle.prototype_id, kind, normalize(parameters),
               self._nonce() if self.escape_arena.active else "")
        if key in self.document._derivations:
            self.stats.derived_reused += 1
            return self.document._derivations[key]
        native = self.escape_arena.native(handle) if self.escape_arena.active else prototype.shape
        with self.document.admission.admit(ResourceRequest(kind="mesh"),
                                          cancellation=self.cancellation):
            result = compute(copy_shape(native))
            _assert_value_result(result)
            result = _freeze_derived(result)
            self.stats.native_copies += 1
        self.document._derivations[key] = result
        self.stats.derived_computed += 1
        return result

    def bind_root(self, root: RootNode, *,
                  unrepresented_metadata: tuple[str, ...] | None = None) -> RootNode:
        """Bind the exact returned tree without native capture or evaluation.

        Local sibling keys must be unique; labels and prototype IDs need not be.
        Rebinding replaces the candidate tree atomically after validation.
        Evaluation history remains retained separately for subsequent reuse.
        """
        self._check()
        _validate_metadata_coverage(unrepresented_metadata)
        handles = validate_root(root, self.document._get)
        self._handles.update((handle.allocation_id, handle) for handle in handles)
        self._root = root
        self._unrepresented_metadata = unrepresented_metadata
        return root

    def publish_result(self, entry_key: str, root: RootNode, *,
                       source_identity: str, required_exports: tuple[str, ...],
                       unrepresented_metadata: tuple[str, ...] | None) -> Revision:
        """Publish one completed child without ending the Python execution.

        The supplied root already describes an immutable native snapshot; the
        frontend captures private/opaque return values before reaching here.
        Subsequent authored mutations stay in this transaction's shared escape
        arena. Entry and export ordering use this request's original sequence,
        never the later snapshot ID allocated for the completed child.
        """
        self._check()
        if type(entry_key) is not str or not entry_key:
            raise ValueError("a family entry requires a nonempty string key")
        if type(source_identity) is not str:
            raise TypeError("a family result requires a captured source identity string")
        if (type(required_exports) is not tuple
                or any(type(path) is not str or not path for path in required_exports)):
            raise TypeError("family exports require an immutable tuple of nonempty path strings")
        _validate_metadata_coverage(unrepresented_metadata)
        handles = validate_root(root, self.document._get)
        self._handles.update((handle.allocation_id, handle) for handle in handles)
        with self.document._lock:
            self.document._next_revision += 1
            self.document._next_publication_sequence += 1
            revision = Revision(self.document._next_revision, source_identity,
                                MappingProxyType({}), handles, required_exports,
                                root, unrepresented_metadata, self._request_sequence,
                                self.document._next_publication_sequence, entry_key)
            stale = self.document._accept_result(revision)
        if stale:
            raise SupersededRevision(revision)
        return revision

    def commit(self) -> Revision:
        self._check()
        with self.document._lock:
            self.document._next_publication_sequence += 1
            revision = Revision(self.revision_id, self.source_identity,
                                MappingProxyType(dict(self._features)),
                                tuple(self._handles.values()),
                                self.required_exports, self._root, self._unrepresented_metadata,
                                self._request_sequence, self.document._next_publication_sequence)
            stale = self.document._accept_result(revision)
            self._close()
        if stale:
            raise SupersededRevision(revision)
        return revision

    def abort(self) -> None:
        if not self._closed:
            self._close()

    def _close(self) -> None:
        self._closed = True
        self.document._active.pop(self.revision_id, None)
        self.escape_arena.clear()

    def __enter__(self) -> RevisionTransaction:
        self._check()
        return self

    def __exit__(self, *exc) -> None:
        self.abort()


def _freeze_auxiliary(value: Any, depth: int = 0, _budget=None) -> Any:
    """Snapshot bounded closed structural values carried by a native result.

    Count expanded visits, not only unique containers: checkpoint serialization
    expands shared value tuples too. A tiny recursive DAG must not turn into
    unbounded allocation or serialization work.
    """
    if _budget is None:
        _budget = [8 * 1024**2]
    _budget[0] -= 64 + (len(value) * (4 if type(value) is str else 1)
                        if type(value) in (str, bytes) else 0)
    if _budget[0] < 0:
        raise ValueError("native result auxiliary values exceed the size limit")
    if depth > 128:
        raise ValueError("native result auxiliary nesting exceeds the limit")
    if value is None or type(value) in (str, bytes, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) in (tuple, list):
        return tuple(_freeze_auxiliary(item, depth + 1, _budget) for item in value)
    if type(value) in (dict, MappingProxyType) and all(type(key) is str for key in value):
        result = {}
        for key, item in value.items():
            _freeze_auxiliary(key, depth + 1, _budget)
            result[key] = _freeze_auxiliary(item, depth + 1, _budget)
        return MappingProxyType(result)
    raise TypeError("native result auxiliary data requires finite closed values")


def _freeze_derived(value: Any) -> Any:
    if value is None or type(value) in (str, bytes, bool, int, float):
        return value
    if type(value) in (list, tuple):
        return tuple(_freeze_derived(v) for v in value)
    if type(value) is dict:
        return MappingProxyType({k: _freeze_derived(v) for k, v in value.items()})
    raise TypeError("derived native data must be immutable scalar, bytes, tuple, or mapping data")
