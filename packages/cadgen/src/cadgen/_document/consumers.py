"""Pinned, owner-thread consumers for one immutable document revision.

This internal bridge deliberately exposes no author API and creates no worker or
geometry store.  Scene membership, paths, placement, labels and appearance come
only from the pinned revision's returned root.  Trusted query callbacks receive
the retained prototype under an explicit read-only contract; derivation
callbacks receive a private native copy because meshing and similar algorithms
may attach data to their input.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from threading import Event
from types import MappingProxyType
from typing import Any, Callable

from .core import Document, GeometryHandle
from .identities import normalize
from .native import copy_shape, copy_shape_with_topology_order
from .resources import AdmissionDenied, Cancelled, ResourceRequest
from .roots import AssemblyGroup, GeometryLeaf, IDENTITY_TRANSFORM


class StaleOccurrencePath(KeyError):
    """An occurrence path belongs to another document revision."""


class AmbiguousOccurrencePath(ValueError):
    """A malformed root tree supplies the same exact path more than once."""


@dataclass(frozen=True)
class OccurrencePath:
    """Exact local-key path scoped to one document owner and revision."""

    owner_id: str
    revision_id: int
    nodes: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.owner_id) is not str or not self.owner_id:
            raise ValueError("an occurrence path requires a document owner")
        if type(self.revision_id) is not int:
            raise TypeError("an occurrence path requires an integer revision id")
        if (type(self.nodes) is not tuple or not self.nodes
                or any(type(node) is not str or not node for node in self.nodes)):
            raise TypeError("an occurrence path requires nonempty exact local keys")


@dataclass(frozen=True)
class ConsumerOccurrence:
    """Immutable scene metadata; it contains no native pointer or handle."""

    path: OccurrencePath
    prototype_id: str
    transform: tuple[float, ...]
    label: str
    appearance: Any


@dataclass(frozen=True)
class ConsumerMetrics:
    paths_resolved: int
    queries_completed: int
    derivations_computed: int
    derivations_reused: int
    native_copies: int
    admission_denied: int
    cancelled: int


@dataclass(frozen=True)
class _ResolvedLeaf:
    occurrence: ConsumerOccurrence
    handle: GeometryHandle


_MISSING = object()


class _DocumentBridge:
    """The only access to core-private prototype and derivation storage."""

    def __init__(self, document: Document) -> None:
        self.document = document

    def prototype_shape(self, handle: GeometryHandle) -> Any:
        return self.document._get(handle).shape

    def derivation(self, key: tuple) -> Any:
        return self.document._derivations.get(key, _MISSING)

    def save_derivation(self, key: tuple, value: Any) -> None:
        self.document._derivations[key] = value


def _multiply(first: tuple[float, ...], second: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(sum(first[row * 4 + k] * second[k * 4 + column]
                     for k in range(4))
                 for row in range(4) for column in range(4))


def _freeze_value(value: Any) -> Any:
    """Copy a closed value vocabulary into deeply immutable result data."""
    if value is None or type(value) in (str, bytes, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("consumer result values must be finite")
        return value
    if type(value) in (list, tuple):
        return tuple(_freeze_value(item) for item in value)
    if type(value) in (dict, MappingProxyType):
        if any(type(key) is not str for key in value):
            raise TypeError("consumer result mappings require string keys")
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    raise TypeError("consumer callbacks must return immutable value data, never native objects")


def _index_root(owner_id: str, revision_id: int, root: Any,
                bridge: _DocumentBridge) -> dict[tuple[str, ...], _ResolvedLeaf]:
    if type(root) not in (GeometryLeaf, AssemblyGroup):
        raise ValueError("a consumer requires an authoritative returned root")
    result: dict[tuple[str, ...], _ResolvedLeaf] = {}
    stack = [(root, (), IDENTITY_TRANSFORM, frozenset())]
    while stack:
        node, parent_path, parent_transform, ancestors = stack.pop()
        if type(node) not in (GeometryLeaf, AssemblyGroup):
            raise TypeError("root hierarchy requires GeometryLeaf or AssemblyGroup nodes")
        if id(node) in ancestors:
            raise ValueError("root hierarchy contains a cycle")
        path = parent_path + (node.node_id.value,)
        transform = _multiply(parent_transform, node.transform)
        if type(node) is GeometryLeaf:
            if path in result:
                raise AmbiguousOccurrencePath(f"ambiguous occurrence path: {path!r}")
            bridge.prototype_shape(node.geometry)
            occurrence_path = OccurrencePath(owner_id, revision_id, path)
            result[path] = _ResolvedLeaf(
                ConsumerOccurrence(occurrence_path, node.geometry.prototype_id,
                                   transform, node.label, _freeze_value(node.appearance)),
                node.geometry)
        else:
            seen = set()
            for child in node.children:
                key = child.node_id.value
                if key in seen:
                    raise AmbiguousOccurrencePath(
                        f"ambiguous occurrence path below {path!r}: {key!r}")
                seen.add(key)
            branch = ancestors | {id(node)}
            stack.extend((child, path, transform, branch)
                         for child in reversed(node.children))
    if not result:
        raise ValueError("a consumer root must contain reachable geometry")
    return result


class RevisionConsumer:
    """Synchronous consumer bound to one exact pinned revision and its root.

    All native work runs on the document owner thread.  ``query_value``
    callbacks are trusted read-only native adapters and receive the composed
    occurrence transform separately.  ``derive`` callbacks receive a private
    prototype copy; their cache identity excludes occurrence placement, label
    and appearance.
    """

    def __init__(self, document: Document, revision_id: int, *,
                 cancellation: Event | None = None) -> None:
        if not isinstance(document, Document):
            raise TypeError("a revision consumer requires a Document")
        if type(revision_id) is not int:
            raise TypeError("a revision consumer requires an exact integer revision id")
        document._assert_owner()
        self._document = document
        self._bridge = _DocumentBridge(document)
        self._cancellation = cancellation or Event()
        self._closed = False
        self._paths_resolved = 0
        self._queries_completed = 0
        self._derivations_computed = 0
        self._derivations_reused = 0
        self._native_copies = 0
        self._admission_denied = 0
        self._cancelled = 0
        self._pin = document.pin(revision_id)
        try:
            root = self._pin.revision.root
            if root is None:
                raise ValueError("a consumer requires the revision's authoritative returned root")
            self._leaves = _index_root(document.owner_id, revision_id, root, self._bridge)
        except BaseException:
            self._pin.release()
            raise

    @property
    def revision_id(self) -> int:
        return self._pin.revision_id

    @property
    def metrics(self) -> ConsumerMetrics:
        self._assert_open_owner()
        return ConsumerMetrics(self._paths_resolved, self._queries_completed,
                               self._derivations_computed, self._derivations_reused,
                               self._native_copies, self._admission_denied,
                               self._cancelled)

    def occurrences(self) -> tuple[ConsumerOccurrence, ...]:
        self._assert_open_owner()
        return tuple(leaf.occurrence for leaf in self._leaves.values())

    def occurrence(self, nodes: tuple[str, ...]) -> ConsumerOccurrence:
        self._assert_open_owner()
        if (type(nodes) is not tuple or not nodes
                or any(type(node) is not str for node in nodes)):
            raise TypeError("an occurrence requires a nonempty tuple of exact local keys")
        try:
            leaf = self._leaves[nodes]
        except KeyError:
            raise StaleOccurrencePath(
                f"occurrence path is unavailable in revision {self.revision_id}: {nodes!r}") from None
        self._paths_resolved += 1
        return leaf.occurrence

    def query_value(self, path: OccurrencePath,
                    read_only: Callable[[Any, tuple[float, ...]], Any], *,
                    resources: ResourceRequest | None = None) -> Any:
        """Run a trusted read-only native query and return immutable value data."""
        leaf = self._resolve(path)
        if not callable(read_only):
            raise TypeError("a native value query requires a callable")
        request = resources or ResourceRequest(kind="query")
        if request.kind != "query":
            raise ValueError("a native value query requires query resource admission")
        native = self._bridge.prototype_shape(leaf.handle)
        try:
            with self._document.admission.admit(request, cancellation=self._cancellation):
                result = _freeze_value(read_only(native, leaf.occurrence.transform))
        except AdmissionDenied:
            self._admission_denied += 1
            raise
        except Cancelled:
            self._cancelled += 1
            raise
        self._queries_completed += 1
        return result

    def derive(self, path: OccurrencePath, kind: str, parameters: Any,
               compute: Callable[[Any], Any], *,
               resources: ResourceRequest | None = None,
               topology_kinds: tuple[str, ...] = ()) -> Any:
        """Compute or reuse immutable prototype data from a private native copy."""
        leaf = self._resolve(path)
        if type(kind) is not str or not kind:
            raise ValueError("a consumer derivation requires a nonempty kind")
        if not callable(compute):
            raise TypeError("a consumer derivation requires a callable")
        if type(topology_kinds) is not tuple or topology_kinds not in ((), ("face",), ("face", "edge")):
            raise ValueError("unsupported derivation topology order")
        normalized_parameters = normalize(parameters)
        normalized_runtime = normalize(self._document.runtime)
        key = (leaf.handle.prototype_id, "consumer-v2", kind, topology_kinds,
               normalized_parameters, normalized_runtime)
        cached = self._bridge.derivation(key)
        if cached is not _MISSING:
            self._derivations_reused += 1
            return cached
        request = resources or ResourceRequest(kind="mesh")
        if request.kind not in {"mesh", "native", "checkpoint"}:
            raise ValueError("a derivation requires mesh, native, or checkpoint admission")
        native = self._bridge.prototype_shape(leaf.handle)
        try:
            with self._document.admission.admit(request, cancellation=self._cancellation):
                if topology_kinds:
                    private, ordered = copy_shape_with_topology_order(
                        native, topology_kinds, checkpoint=self.checkpoint)
                else:
                    private = copy_shape(native)
                self._native_copies += 1
                result = _freeze_value(compute(private, ordered) if topology_kinds else compute(private))
        except AdmissionDenied:
            self._admission_denied += 1
            raise
        except Cancelled:
            self._cancelled += 1
            raise
        self._bridge.save_derivation(key, result)
        self._derivations_computed += 1
        return result

    def cancel(self) -> None:
        """Thread-safe cancellation signal; native callbacks remain owner-thread only."""
        self._cancellation.set()

    def checkpoint(self) -> None:
        """Let a trusted derivation stop between native calls or Python batches.

        The enclosing derive/query request counts cancellation once when it
        unwinds. A callback checkpoint does not count a second failed request.
        Native calls that offer no interruptible binding finish before this
        checkpoint can observe cancellation.
        """
        self._assert_open_owner()
        if self._cancellation.is_set():
            raise Cancelled("document consumer was cancelled")

    def close(self) -> None:
        self._document._assert_owner()
        if not self._closed:
            self._pin.release()
            self._closed = True
            self._leaves.clear()

    def _assert_open_owner(self) -> None:
        self._document._assert_owner()
        if self._closed:
            raise RuntimeError("revision consumer is closed")

    def _check_cancellation(self) -> None:
        if self._cancellation.is_set():
            self._cancelled += 1
            raise Cancelled("document consumer was cancelled")

    def _resolve(self, path: OccurrencePath) -> _ResolvedLeaf:
        self._assert_open_owner()
        self._check_cancellation()
        if type(path) is not OccurrencePath:
            raise TypeError("consumer work requires an exact OccurrencePath")
        if path.owner_id != self._document.owner_id or path.revision_id != self.revision_id:
            raise StaleOccurrencePath(
                f"occurrence path does not belong to pinned revision {self.revision_id}")
        try:
            leaf = self._leaves[path.nodes]
        except KeyError:
            raise StaleOccurrencePath(
                f"occurrence path is unavailable in revision {self.revision_id}: {path.nodes!r}") from None
        self._paths_resolved += 1
        return leaf

    def __enter__(self) -> RevisionConsumer:
        self._assert_open_owner()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
