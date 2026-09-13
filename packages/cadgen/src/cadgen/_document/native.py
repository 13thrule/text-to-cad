"""Small, lazy OCCT ownership and history adapter; no BREP codecs.

Callbacks accepted by the document are trusted engine adapters. Author code
receives only an execution-private arena; Python cannot enforce immutability of
a TopoDS pointer once that pointer has escaped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import nullcontext
from typing import Any, Iterable


@dataclass(frozen=True)
class SubelementRef:
    """An exact ordinal in one evaluation, not a persistent selection name."""
    input_index: int | None
    kind: str
    index: int


@dataclass(frozen=True)
class TopologyRelation:
    source: SubelementRef
    targets: tuple[SubelementRef, ...]


@dataclass(frozen=True)
class TopologyHistory:
    generated: tuple[TopologyRelation, ...] = ()
    modified: tuple[TopologyRelation, ...] = ()
    deleted: tuple[SubelementRef, ...] = ()
    unchanged: tuple[TopologyRelation, ...] = ()
    complete: bool = False
    reason: str = "operator did not provide native topology history"


@dataclass(frozen=True)
class NativeResult:
    shape: Any
    history: TopologyHistory = field(default_factory=TopologyHistory)


def copy_shape(shape: Any) -> Any:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    if shape is None or shape.IsNull():
        raise ValueError("a retained native prototype must contain a non-null shape")
    return BRepBuilderAPI_Copy(shape, True, True).Shape()


def copy_many(shapes: Iterable[Any]) -> tuple[Any, ...]:
    """One copier preserves shared topology across roots and subshape wrappers."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.TopoDS import TopoDS_Compound
    shapes = tuple(shapes)
    if not shapes:
        return ()
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for shape in shapes:
        if shape is None or shape.IsNull():
            raise ValueError("cannot copy null native input")
        builder.Add(compound, shape)
    copier = BRepBuilderAPI_Copy(compound, True, True)
    return tuple(copier.ModifiedShape(shape) for shape in shapes)


def topology_map(shape: Any) -> Any:
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape
    result = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, result)
    return result


def _history_targets(values: Any) -> Iterable[Any]:
    """Read native history lists without the binding's costly Python iterator.

    Empty and singleton histories are common. For longer lists, copy only the
    list nodes and drain that private list; TopoDS values remain shared and the
    builder's history is never mutated. First/RemoveFirst preserve list order.
    """
    count = values.Extent()
    if not count:
        return
    if count == 1:
        yield values.First()
        return
    from OCP.TopTools import TopTools_ListOfShape
    remaining = TopTools_ListOfShape(values)
    while not remaining.IsEmpty():
        yield remaining.First()
        remaining.RemoveFirst()


def history_from_builder(builder: Any, inputs: Iterable[Any], result: Any | None = None
                         ) -> TopologyHistory:
    """Capture builder evidence before disposal, with explicit incompleteness.

    A missing generated/modified target makes the evidence incomplete. Native
    same-shape comparisons, not approximate geometry, identify unchanged input
    subelements. Consumers must reject ambiguity rather than guess a match.
    """
    result = builder.Shape() if result is None else result
    output = topology_map(result)
    generated, modified, deleted, unchanged = [], [], [], []
    complete = True
    required = ("Generated", "Modified", "IsDeleted")
    if not all(hasattr(builder, name) for name in required):
        return TopologyHistory(reason="native builder does not expose full shape history")
    def ref(index: int, input_index: int | None, mapping: Any) -> SubelementRef:
        shape = mapping.FindKey(index)
        return SubelementRef(input_index, shape.ShapeType().name, index)
    for input_index, shape in enumerate(inputs):
        source_map = topology_map(shape)
        for index in range(1, source_map.Extent() + 1):
            source = ref(index, input_index, source_map)
            subshape = source_map.FindKey(index)
            for method, records in (("Generated", generated), ("Modified", modified)):
                targets = []
                for target in _history_targets(getattr(builder, method)(subshape)):
                    ordinal = output.FindIndex(target)
                    if ordinal:
                        targets.append(ref(ordinal, None, output))
                    else:
                        complete = False
                if targets:
                    records.append(TopologyRelation(source, tuple(targets)))
            if builder.IsDeleted(subshape):
                deleted.append(source)
            else:
                ordinal = output.FindIndex(subshape)
                if ordinal:
                    unchanged.append(TopologyRelation(source, (ref(ordinal, None, output),)))
    return TopologyHistory(tuple(generated), tuple(modified), tuple(deleted),
                           tuple(unchanged), complete,
                           "" if complete else "native history names a target absent from the result")


class NativeEscapeArena:
    """Execution-private native alias families copied by one OCCT copier each.

    Topology substitutions between independent deep copies are unsafe: an edge's
    pcurves must stay bound to its face's copied surface. Copy each connected
    family together, retaining OCCT's own topology/geometry copy correspondence.
    Independent authored allocations form independent families even when their
    immutable prototype is shared.
    """
    def __init__(self, snapshot, validate=None, reservation=nullcontext, on_copy=None) -> None:
        self._snapshot = snapshot
        self._validate = validate
        self._reservation = reservation
        self._on_copy = on_copy
        self._shapes: dict[str, Any] = {}
        self._owned = {}
        self.active = False
        self.copy_batches = 0

    def _copy_region(self, owned) -> None:
        groups = _alias_families(owned)
        for members in groups:
            shapes = tuple(owned[key][0] for key in members)
            moved = any(shape.IsPartner(source) and not shape.IsSame(source)
                        for key in members for shape, parents in (owned[key],)
                        for _, source in parents)
            copied = _copy_placed_family(members, owned) if moved else copy_many(shapes)
            self._shapes.update(zip(members, copied))
            self.copy_batches += 1
            if self._on_copy is not None:
                for _ in members:
                    self._on_copy()
        self._owned.update(owned)

    def _start(self) -> None:
        if self.active:
            return
        owned = self._snapshot()
        with self._reservation():
            self._copy_region(owned)
        self.active = True

    def native(self, handle) -> Any:
        if self._validate is not None:
            self._validate(handle)
        self._start()
        if handle.allocation_id not in self._shapes:
            additions = {key: value for key, value in self._snapshot().items()
                         if key not in self._owned}
            # Native values already exposed cannot be replaced with another
            # whole-family copy. Ordinary subsequent computations adopt their
            # current private result, so this only affects a late old handle.
            if any(parent in self._owned for _, parents in additions.values()
                   for parent, _ in parents):
                raise ValueError("late native alias family requires private operation replay")
            with self._reservation():
                self._copy_region(additions)
        try:
            return self._shapes[handle.allocation_id]
        except KeyError:
            raise ValueError("prototype is not part of this execution's native arena") from None

    def adopt(self, handle, private_shape: Any) -> None:
        if not self.active:
            raise RuntimeError("cannot adopt into an inactive native arena")
        self._shapes[handle.allocation_id] = private_shape

    def clear(self) -> None:
        self._shapes.clear()
        self._owned.clear()


def _alias_families(owned):
    """Group exact dependency aliases; native locations distinguish occurrences.

    Only a whole-root rigid move uses IsPartner across different placements.
    Stripping every subshape location would merge unrelated repeated cutters.
    """
    parent = {key: key for key in owned}
    maps = {key: topology_map(shape) for key, (shape, _) in owned.items()}
    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key
    def join(first, second):
        parent[find(first)] = find(second)
    for key, (shape, inputs) in owned.items():
        result_map = maps[key]
        for input_key, source in inputs:
            if input_key not in owned:
                raise ValueError("native allocation dependency is unavailable")
            # Whole-root location changes preserve partner identity, and OCCT
            # copies them together without a hand-written subshape rewrite.
            shares = shape.IsPartner(source)
            if not shares:
                source_map = topology_map(source)
                shares = any(result_map.Contains(source_map.FindKey(index))
                             for index in range(1, source_map.Extent() + 1))
            if shares:
                join(key, input_key)
    groups = {}
    for key in owned:
        groups.setdefault(find(key), []).append(key)
    for members in groups.values():
        # Independent coincident inputs require actual private replay if one
        # result collapses their native provenance. Never merge those roots.
        roots = [key for key in members if not owned[key][1]]
        for index, key in enumerate(roots):
            for other in roots[index + 1:]:
                if owned[key][0].IsPartner(owned[other][0]):
                    raise ValueError("ambiguous native allocations require private operation replay")
    return tuple(tuple(members) for members in groups.values())


def _copy_placed_family(members, owned):
    """Copy root placements/selections as views of their canonical source.

    OCCT Copy treats differing TopLoc locations as different copy-map keys.
    Keep upstream modeling in its own frame, normalize only proven native
    views, then restore root headers. General new modeling from mixed-location
    aliases requires private replay; rewriting its edges breaks surface bindings.
    """
    from OCP.TopLoc import TopLoc_Location
    identity = TopLoc_Location()
    member_set = set(members)
    views = {}
    visiting = set()
    def resolve(key):
        if key in views:
            return views[key]
        if key in visiting:
            raise ValueError("native allocation graph contains a cycle")
        visiting.add(key)
        shape, parents = owned[key]
        resolved = []
        for parent_key, source in parents:
            if parent_key not in member_set:
                continue
            canonical_parent, parent_view = resolve(parent_key)
            resolved.append((source, parent_view))
            if shape.IsPartner(source):
                relative = shape.Location().Multiplied(source.Location().Inverted())
                view = relative.Multiplied(parent_view)
                views[key] = (canonical_parent.Oriented(shape.Orientation()), view)
                break
            if topology_map(source).Contains(shape):
                views[key] = (shape.Moved(parent_view.Inverted()), parent_view)
                break
        else:
            output_map = topology_map(shape)
            for source, parent_view in resolved:
                source_map = topology_map(source)
                if (not parent_view.IsIdentity()
                        and any(output_map.Contains(source_map.FindKey(index))
                                for index in range(1, source_map.Extent() + 1))):
                    raise ValueError("mixed-location native alias family requires private operation replay")
            views[key] = (shape, identity)
        visiting.remove(key)
        return views[key]
    for key in members:
        resolve(key)
    copied = copy_many(views[key][0] for key in members)
    return tuple(private.Moved(views[key][1]).Oriented(owned[key][0].Orientation())
                 for private, key in zip(copied, members))
