"""Typed identities for resident evaluation, distinct from stored byte digests."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any


@dataclass(frozen=True)
class LogicalIdentity:
    """Frontend supplied correspondence, never a geometric equality claim."""
    value: str


@dataclass(frozen=True)
class EvaluationIdentity:
    value: str


@dataclass(frozen=True)
class RepresentationIdentity:
    value: str

    @classmethod
    def from_bytes(cls, payload: bytes) -> RepresentationIdentity:
        return cls(sha256(payload).hexdigest())


def normalize(value: Any) -> tuple:
    """Closed typed encoding; never repr(), object addresses, or shape hashing.

    Frontend adapters must explicitly lower other values into this vocabulary.
    Type differences (including bool/int and list/tuple) remain significant.
    """
    if isinstance(value, Enum):
        return ("enum", type(value).__module__, type(value).__qualname__, value.name)
    if value is None:
        return ("none",)
    if type(value) is bool:
        return ("bool", value)
    if type(value) is int:
        return ("int", str(value))
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("document operation parameters must be finite")
        return ("float", value.hex())
    if type(value) is str:
        return ("str", value)
    if type(value) is bytes:
        return ("bytes", value.hex())
    if type(value) in (tuple, list):
        return (type(value).__name__, tuple(normalize(v) for v in value))
    if type(value) is dict:
        entries = [(normalize(k), normalize(v)) for k, v in value.items()]
        entries.sort(key=lambda pair: json.dumps(pair[0], separators=(",", ":")))
        return ("dict", tuple(entries))
    raise TypeError(f"unsupported document parameter type: {type(value).__module__}.{type(value).__qualname__}")


def allocation_provenance(handles, allocations) -> tuple:
    """Canonical input-sharing DAG used by evaluation and checkpoint recovery.

    Execution UUIDs locate rows while traversing but never enter the result.
    Unary ancestry is already encoded by its evaluation identity; relations
    between multiple inputs additionally distinguish shared and equal roots.
    """
    if len(handles) < 2:
        return ()
    disjoint = ("disjoint-input-dags-v1",)
    intervals = sorted(allocations[handle.allocation_id].ancestry_interval for handle in handles)
    if all(left[1] < right[0] for left, right in zip(intervals, intervals[1:])):
        return disjoint
    indices = {}
    nodes = []
    owners = {}
    shared = False
    roots = []
    for root_index, root in enumerate(handles):
        stack = [(root, False)]
        while stack:
            handle, finish = stack.pop()
            key = handle.allocation_id
            if finish:
                children = tuple(indices[parent.allocation_id] for parent in allocations[key].inputs)
                nodes[indices[key]] = (handle.evaluation_id.value, children)
                continue
            if key in indices:
                shared |= owners[key] != root_index
                continue
            indices[key] = len(nodes)
            owners[key] = root_index
            nodes.append(None)
            stack.append((handle, True))
            stack.extend((parent, False) for parent in reversed(allocations[key].inputs))
        roots.append(indices[root.allocation_id])
    # Overlapping rank intervals do not prove sharing. Exact traversal must
    # produce the same disjoint identity as the fast proof, independent of
    # creation order (including topological checkpoint reconstruction).
    return (tuple(roots), tuple(nodes)) if shared else disjoint


@dataclass(frozen=True)
class EvaluationKey:
    operator: str
    implementation: str
    parameters: tuple
    inputs: tuple[EvaluationIdentity, ...]
    runtime: tuple
    volatility: str = ""
    alias_provenance: tuple = ()

    @classmethod
    def create(cls, operator: str, implementation: str, parameters: Any,
               inputs: tuple[EvaluationIdentity, ...] = (), runtime: Any = (),
               volatility: str = "", alias_provenance: Any = ()) -> EvaluationKey:
        return cls(operator, implementation, normalize(parameters), inputs,
                   normalize(runtime), volatility, normalize(alias_provenance))

    @property
    def identity(self) -> EvaluationIdentity:
        payload = ("cadgen-document-evaluation-v3", self.operator,
                   self.implementation, self.parameters,
                   tuple(v.value for v in self.inputs), self.runtime,
                   self.volatility, self.alias_provenance)
        return EvaluationIdentity(sha256(json.dumps(payload, separators=(",", ":"),
                                                     ensure_ascii=False).encode()).hexdigest())
