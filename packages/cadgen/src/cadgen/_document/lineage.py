"""Exact topology lineage inside one pinned allocation DAG, never source naming.

History uses one-based ALL-topology ordinals; mesh selections use zero-based
kind ordinals. This module translates with OCCT IsSame maps while capturing a
closed value snapshot. It follows allocation inputs, never prototype equality.
Private-input/escaped operators need an explicit copy correspondence that core
does not yet retain; cleanup with incomplete history also stops traversal.
Source edits require separate source reconciliation before any route exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Literal

from .consumers import OccurrencePath, RevisionConsumer
from .core import GeometryHandle
from .inspection import TopologyReference
from .native import SubelementRef, TopologyHistory, TopologyRelation, topology_map
from .resources import Cancelled, ResourceRequest

MAX_NODES = 512
MAX_TOPOLOGY = 100_000
MAX_WORK = 1_000_000


@dataclass(frozen=True)
class InputRoute:
    complete: bool
    reason: str
    # Parent ALL index, output ALL indices, explicit deletion evidence.
    relations: tuple[tuple[int, tuple[int, ...], bool], ...] = ()


@dataclass(frozen=True)
class EvaluationNode:
    handle: GeometryHandle
    inputs: tuple[str, ...]
    kinds: tuple[str, ...]
    faces: tuple[int, ...]
    edges: tuple[int, ...]
    routes: tuple[InputRoute, ...]


@dataclass(frozen=True)
class EvaluationRoutes:
    target: OccurrencePath
    target_allocation: str
    # Dependency-first order; contains only immutable values, no native handles.
    nodes: tuple[EvaluationNode, ...]


@dataclass(frozen=True)
class EvaluationSelection:
    owner_id: str
    revision_id: int
    allocation_id: str
    prototype_id: str
    kind: Literal["face", "edge"]
    ordinal: int


@dataclass(frozen=True)
class LineageResult:
    status: Literal["unique", "ambiguous", "deleted", "unavailable"]
    targets: tuple[TopologyReference, ...] = ()
    reason: str = ""


class _Budget:
    def __init__(self, checkpoint):
        self.remaining = MAX_WORK
        self.checkpoint = checkpoint

    def use(self, count=1):
        self.remaining -= count
        if self.remaining < 0:
            raise ValueError("lineage traversal exceeds the work limit")
        self.checkpoint()


def _input_routes(history, aliases, parent_maps, output, independent, budget):
    unavailable = lambda reason: tuple(InputRoute(False, reason) for _ in parent_maps)
    if type(history) is not TopologyHistory or history.complete is not True:
        reason = history.reason if type(history) is TopologyHistory and type(history.reason) is str else "invalid native history"
        return unavailable(reason[:1024] or "incomplete native history")
    if len(aliases) != len(parent_maps):
        return unavailable("operator did not retain exact history-input correspondence")
    if any(type(rows) is not tuple for rows in (history.generated, history.modified, history.unchanged, history.deleted)):
        return unavailable("invalid native history records")
    records = [dict() for _ in parent_maps]
    try:
        def source(ref):
            budget.use()
            if (type(ref) is not SubelementRef or type(ref.input_index) is not int
                    or not 0 <= ref.input_index < len(aliases) or type(ref.index) is not int
                    or not 1 <= ref.index <= aliases[ref.input_index].Extent()):
                raise ValueError
            native = aliases[ref.input_index].FindKey(ref.index)
            if native.ShapeType().name != ref.kind:
                raise ValueError
            index = parent_maps[ref.input_index].FindIndex(native)
            if not index:
                raise ValueError
            return records[ref.input_index].setdefault(index, [set(), False])
        for rows in (history.generated, history.modified, history.unchanged):
            budget.use(len(rows))
            for relation in rows:
                if type(relation) is not TopologyRelation or type(relation.targets) is not tuple:
                    raise ValueError
                record = source(relation.source)
                for ref in relation.targets:
                    budget.use()
                    if (type(ref) is not SubelementRef or ref.input_index is not None
                            or type(ref.index) is not int or not 1 <= ref.index <= output.Extent()
                            or output.FindKey(ref.index).ShapeType().name != ref.kind):
                        raise ValueError
                    record[0].add(ref.index)
        for ref in history.deleted:
            source(ref)[1] = True
    except ValueError:
        if budget.remaining < 0:
            raise
        return unavailable("native history lacks an exact topology correspondence")
    return tuple(InputRoute(False, "independent inputs share native topology without allocation correspondence")
                 if index in independent else InputRoute(True, "", tuple(
                     (source, tuple(sorted(targets)), deleted)
                     for source, (targets, deleted) in sorted(rows.items())))
                 for index, rows in enumerate(records))


def capture_routes(consumer: RevisionConsumer, target: OccurrencePath, *,
                   source: GeometryHandle | None = None) -> EvaluationRoutes:
    """Snapshot exact current allocation routes to a selected returned leaf.

    Optional source includes a valid independent allocation for an explicit
    no-route result. This trusted internal bridge accesses core ownership rows;
    it does not expose native values. Capture requires a live pinned consumer.
    Native map allocation is admitted/limited conservatively, not hard-capped
    inside OCCT. Native calls finish before cooperative cancellation checks.
    """
    consumer.checkpoint()
    if type(target) is not OccurrencePath:
        raise TypeError("lineage target requires an exact occurrence path")
    occurrence = consumer.occurrence(target.nodes)
    if occurrence.path != target:
        raise ValueError("lineage target belongs to another owner or revision")
    doc = consumer._document
    sink = consumer._leaves[target.nodes].handle
    if source is not None:
        if type(source) is not GeometryHandle:
            raise TypeError("lineage source requires an exact geometry handle")
        doc._get(source)
    budget = _Budget(consumer.checkpoint)
    ordered, done, visiting = [], set(), set()
    # Iterative DFS bounds depth without consuming the Python call stack.
    for root in (sink,) if source is None else (sink, source):
        stack = [(root, False)]
        while stack:
            budget.use()
            handle, finish = stack.pop()
            key = handle.allocation_id
            if finish:
                visiting.remove(key)
                done.add(key)
                ordered.append(handle)
                continue
            if key in done:
                continue
            if key in visiting:
                raise ValueError("allocation dependencies contain a cycle")
            if len(done) + len(visiting) >= MAX_NODES:
                raise ValueError("lineage exceeds the allocation limit")
            doc._get(handle)
            visiting.add(key)
            stack.append((handle, True))
            stack.extend((parent, False) for parent in reversed(doc._allocations[key].inputs))
    nodes, maps, ancestors = [], {}, {}
    total = 0
    with doc.admission.admit(ResourceRequest(kind="query", native_bytes=64 * 1024**2),
                             cancellation=consumer._cancellation):
        def mapped(native):
            nonlocal total
            budget.use()
            mapping = topology_map(native)
            total += mapping.Extent()
            if total > MAX_TOPOLOGY:
                raise ValueError("lineage exceeds the total topology limit")
            return mapping
        for handle in ordered:
            budget.use()
            prototype = doc._get(handle)
            inputs = doc._allocations[handle.allocation_id].inputs
            mapping = mapped(prototype.shape)
            maps[handle.allocation_id] = mapping
            kinds = tuple(mapping.FindKey(index).ShapeType().name for index in range(1, mapping.Extent() + 1))
            budget.use(len(kinds))
            # Exact kind ordinals must be read from their own native maps, not
            # inferred from positions in the ALL-map traversal.
            from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
            from OCP.TopExp import TopExp
            from OCP.TopTools import TopTools_IndexedMapOfShape
            ordinals = []
            for kind in (TopAbs_FACE, TopAbs_EDGE):
                by_kind = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(prototype.shape, kind, by_kind)
                budget.use(by_kind.Extent())
                ordinals.append(tuple(mapping.FindIndex(by_kind.FindKey(i)) for i in range(1, by_kind.Extent() + 1)))
            ancestors[handle.allocation_id] = {handle.allocation_id}.union(
                *(ancestors[parent.allocation_id] for parent in inputs))
            aliases = tuple(mapped(native) for native in prototype.alias_sources)
            independent = set()
            for index, first in enumerate(inputs):
                for other in range(index + 1, len(inputs)):
                    second = inputs[other]
                    if ancestors[first.allocation_id] & ancestors[second.allocation_id]:
                        continue
                    left, right = maps[first.allocation_id], maps[second.allocation_id]
                    for i in range(1, left.Extent() + 1):
                        budget.use()
                        if right.Contains(left.FindKey(i)):
                            independent.update((index, other))
                            break
            routes = _input_routes(prototype.history, aliases,
                                   tuple(maps[parent.allocation_id] for parent in inputs),
                                   mapping, independent, budget)
            nodes.append(EvaluationNode(handle, tuple(parent.allocation_id for parent in inputs),
                                        kinds, *ordinals, routes))
    consumer.checkpoint()
    return EvaluationRoutes(target, sink.allocation_id, tuple(nodes))


def selection(routes: EvaluationRoutes, handle: GeometryHandle, kind: str,
              ordinal: int) -> EvaluationSelection:
    """Convert a mesh kind ordinal to a scoped allocation selection."""
    if type(routes) is not EvaluationRoutes or type(handle) is not GeometryHandle:
        raise TypeError("selection requires an exact route snapshot and handle")
    node = next((node for node in routes.nodes if node.handle == handle), None)
    if node is None:
        raise ValueError("selection handle is absent from the captured allocation routes")
    if (type(kind) is not str or kind not in ("face", "edge") or type(ordinal) is not int
            or not 0 <= ordinal < len(node.faces if kind == "face" else node.edges)):
        raise ValueError("selection requires an existing zero-based face/edge ordinal")
    return EvaluationSelection(routes.target.owner_id, routes.target.revision_id,
                               handle.allocation_id, handle.prototype_id, kind, ordinal)


def resolve(routes: EvaluationRoutes, selected: EvaluationSelection, *,
            cancellation: Event | None = None) -> LineageResult:
    """Resolve all proven DAG routes; never select one split or unknown branch.

    Returned targets are exact candidates. An unavailable result may contain
    proven candidates, but the set is incomplete and must never auto-select.
    Frozen snapshots can be read after their consumer closes; they attest only
    the captured owner/revision and are not claims about a newer document head.
    """
    if type(routes) is not EvaluationRoutes or type(selected) is not EvaluationSelection:
        raise TypeError("lineage resolution requires exact immutable snapshot values")
    if (type(selected.owner_id) is not str or type(selected.revision_id) is not int
            or type(selected.allocation_id) is not str or type(selected.prototype_id) is not str):
        raise ValueError("lineage selection requires exact typed scope values")
    def checkpoint():
        if cancellation is not None and cancellation.is_set():
            raise Cancelled("lineage resolution was cancelled")
    budget = _Budget(checkpoint)
    if (selected.owner_id != routes.target.owner_id or selected.revision_id != routes.target.revision_id):
        raise ValueError("lineage selection belongs to another owner or revision")
    source = next((node for node in routes.nodes if node.handle.allocation_id == selected.allocation_id), None)
    if source is None or selection(routes, source.handle, selected.kind, selected.ordinal) != selected:
        raise ValueError("lineage selection is absent or forged")
    states = {}
    for node in routes.nodes:
        budget.use()
        if node is source:
            ordinals = node.faces if selected.kind == "face" else node.edges
            states[node.handle.allocation_id] = ({ordinals[selected.ordinal]}, True, set())
            continue
        indices, reachable, reasons = set(), False, set()
        for parent, route in zip(node.inputs, node.routes):
            budget.use()
            incoming, exists, unknown = states[parent]
            if not exists:
                continue
            reachable = True
            reasons.update(unknown)
            budget.use(len(route.relations))
            rows = {index: (targets, deleted) for index, targets, deleted in route.relations}
            for index in incoming:
                budget.use()
                if not route.complete:
                    reasons.add(route.reason)
                elif index not in rows or (not rows[index][0] and not rows[index][1]):
                    reasons.add("native history has no relation for this subelement")
                else:
                    targets, _ = rows[index]
                    budget.use(len(targets))
                    indices.update(targets)
        states[node.handle.allocation_id] = (indices, reachable, reasons)
    indices, reachable, reasons = states[routes.target_allocation]
    target = next(node for node in routes.nodes if node.handle.allocation_id == routes.target_allocation)
    face_ordinals = {index: ordinal for ordinal, index in enumerate(target.faces)}
    edge_ordinals = {index: ordinal for ordinal, index in enumerate(target.edges)}
    output = []
    for index in sorted(indices):
        budget.use()
        kind = "face" if index in face_ordinals else "edge" if index in edge_ordinals else None
        if kind is None:
            reasons.add("lineage target is outside face/edge selection coverage")
        else:
            ordinal = (face_ordinals if kind == "face" else edge_ordinals)[index]
            output.append(TopologyReference(routes.target, target.handle.prototype_id, kind, ordinal))
    if not reachable:
        reasons.add("source allocation has no dependency route to the target")
    if reasons:
        return LineageResult("unavailable", tuple(output), "; ".join(sorted(reasons)))
    return LineageResult("unique" if len(output) == 1 else "ambiguous" if output else "deleted", tuple(output))
