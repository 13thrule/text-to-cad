"""Immutable returned geometry hierarchy, separate from evaluated tools.

Node IDs are local keys under a parent, never labels or prototype identities.
The tuple of keys along a path identifies an occurrence in this revision.
An immutable subtree may therefore appear below distinct parent occurrences.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Callable, Iterator, TYPE_CHECKING

from .identities import LogicalIdentity

if TYPE_CHECKING:
    from .core import GeometryHandle


IDENTITY_TRANSFORM = (1., 0., 0., 0., 0., 1., 0., 0.,
                      0., 0., 1., 0., 0., 0., 0., 1.)


def _transform(value) -> tuple[float, ...]:
    values = tuple(value)
    if len(values) != 16:
        raise ValueError("root transform requires 16 row-major matrix values")
    if any(type(v) not in (int, float) for v in values):
        raise TypeError("root transform values must be real numbers")
    result = tuple(float(v) for v in values)
    if not all(math.isfinite(v) for v in result):
        raise ValueError("root transform values must be finite")
    if result[12:] != (0., 0., 0., 1.):
        raise ValueError("root transform must be affine")
    return result


def _appearance(value: Any, ancestors: frozenset[int] = frozenset()) -> Any:
    if value is None or type(value) in (bool, int, str, bytes):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("root appearance values must be finite")
        return value
    if id(value) in ancestors:
        raise ValueError("root appearance must not contain cycles")
    ancestors = ancestors | {id(value)}
    if type(value) in (tuple, list):
        return tuple(_appearance(v, ancestors) for v in value)
    if type(value) in (dict, MappingProxyType):
        if any(type(key) is not str for key in value):
            raise TypeError("root appearance keys must be strings")
        return MappingProxyType({key: _appearance(v, ancestors) for key, v in value.items()})
    raise TypeError("root appearance requires immutable value data")


def _metadata(node) -> None:
    key = node.node_id
    if type(key) is str:
        key = LogicalIdentity(key)
    if type(key) is not LogicalIdentity or type(key.value) is not str or not key.value:
        raise ValueError("a root node requires a nonempty local identity")
    if type(node.label) is not str:
        raise TypeError("a root label must be a string")
    object.__setattr__(node, "node_id", key)
    object.__setattr__(node, "transform", _transform(node.transform))
    object.__setattr__(node, "appearance", _appearance(node.appearance))


@dataclass(frozen=True)
class GeometryLeaf:
    node_id: LogicalIdentity | str
    geometry: GeometryHandle
    transform: tuple[float, ...] = IDENTITY_TRANSFORM
    label: str = ""
    appearance: Any = ()

    def __post_init__(self) -> None:
        _metadata(self)


@dataclass(frozen=True)
class AssemblyGroup:
    node_id: LogicalIdentity | str
    children: tuple[RootNode, ...]
    transform: tuple[float, ...] = IDENTITY_TRANSFORM
    label: str = ""
    appearance: Any = ()

    def __post_init__(self) -> None:
        _metadata(self)
        object.__setattr__(self, "children", tuple(self.children))


RootNode = GeometryLeaf | AssemblyGroup


def walk_root(root: RootNode) -> Iterator[tuple[tuple[str, ...], RootNode]]:
    """Visit exact occurrence paths; shared subtrees are legal, cycles are not."""
    stack = [(root, (), frozenset())]
    while stack:
        node, parent, ancestors = stack.pop()
        if type(node) not in (GeometryLeaf, AssemblyGroup):
            raise TypeError("root hierarchy requires GeometryLeaf or AssemblyGroup nodes")
        if id(node) in ancestors:
            raise ValueError("root hierarchy contains a cycle")
        key = node.node_id
        if type(key) is not LogicalIdentity or type(key.value) is not str or not key.value:
            raise ValueError("a root node requires a nonempty local identity")
        _transform(node.transform)
        if type(node.label) is not str:
            raise TypeError("a root label must be a string")
        path = parent + (key.value,)
        yield path, node
        if type(node) is AssemblyGroup:
            keys = set()
            for child in node.children:
                if type(child) not in (GeometryLeaf, AssemblyGroup):
                    raise TypeError("root hierarchy requires GeometryLeaf or AssemblyGroup nodes")
                child_key = child.node_id
                if type(child_key) is not LogicalIdentity:
                    raise ValueError("a root node requires a local identity")
                if child_key in keys:
                    raise ValueError(f"ambiguous duplicate root identity under {path}: {child_key.value}")
                keys.add(child_key)
            ancestors = ancestors | {id(node)}
            stack.extend((child, path, ancestors) for child in reversed(node.children))


def root_handles(root: RootNode) -> tuple[GeometryHandle, ...]:
    """Distinct native allocations reachable from a returned hierarchy."""
    return tuple(dict.fromkeys(node.geometry for _, node in walk_root(root)
                               if type(node) is GeometryLeaf))


def validate_root(root: RootNode, validate_handle: Callable[[GeometryHandle], Any]
                  ) -> tuple[GeometryHandle, ...]:
    handles = root_handles(root)
    if not handles:
        raise ValueError("a returned root must contain reachable geometry")
    for handle in handles:
        validate_handle(handle)
    return handles
