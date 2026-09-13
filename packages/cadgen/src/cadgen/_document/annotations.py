"""Bounded durable appearance annotations bound to actual saved STEP bytes.

This codec owns no publication or source lookup. A publisher must write its
product beside the STEP as ``<part>.step.json`` and remove that companion
when ``payload`` is None. Occurrence paths address the independent saved
hierarchy, including any STEP root envelope. They are not source node IDs or
persistent face names. Only PBR fields and material tags belong here; native
STEP colors and physical material facts remain in the independently read STEP.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from .appearance import appearance, encoded_size_bound, to_value
from .step_product import SavedNode

SCHEMA = "cadgen.document.annotations"
VERSION = 1
MAX_BYTES = 16 * 1024**2
MAX_NODES = 100_000
MAX_DEPTH = 128
_MAPS = (dict, MappingProxyType)


@dataclass(frozen=True)
class SavedAnnotationPaths:
    """Trusted native-reader inventory bound to its exact captured STEP bytes."""
    step_sha256: str
    step_bytes: int
    leaves: tuple[tuple[int, ...], ...]

    def __post_init__(self):
        if (type(self.step_sha256) is not str or len(self.step_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.step_sha256)
                or type(self.step_bytes) is not int or self.step_bytes < 1):
            raise ValueError("saved path inventory requires exact STEP byte binding")
        if type(self.leaves) is not tuple or not 0 < len(self.leaves) <= MAX_NODES:
            raise ValueError("saved path inventory exceeds the occurrence limit")
        seen = set()
        for path in self.leaves:
            if (type(path) is not tuple or not 0 < len(path) <= MAX_DEPTH
                    or any(type(index) is not int or not 1 <= index <= MAX_NODES for index in path)
                    or path in seen):
                raise ValueError("saved path inventory contains invalid or duplicate paths")
            seen.add(path)
        object.__setattr__(self, "leaves", tuple(sorted(seen)))


def paths_from_product(product):
    """Pair only a writer's independently parsed roots with its verified bytes."""
    from .step_product import StepProduct
    if type(product) is not StepProduct:
        raise TypeError("annotation paths require a verified STEP product")
    digest, size = _binding(product.payload)
    if digest != product.sha256:
        raise ValueError("STEP product payload no longer matches its saved facts")
    return SavedAnnotationPaths(digest, size, tuple(sorted(_saved_paths(product.saved_roots))))


@dataclass(frozen=True)
class AnnotationOccurrence:
    path: tuple[int, ...]
    appearance: MappingProxyType


@dataclass(frozen=True)
class AnnotationProduct:
    step_sha256: str
    step_bytes: int
    payload: bytes | None
    sha256: str | None
    occurrences: tuple[AnnotationOccurrence, ...]


def companion_path(step_path: Path) -> Path:
    path = Path(step_path)
    if path.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("annotation companions require a STEP path")
    return path.with_name(path.name + ".json")


def capture_companion(step_path: Path):
    """Capture a bounded companion before a saved-file job is dispatched."""
    from .sources import CapturedInput
    path = companion_path(step_path)
    try:
        with path.open("rb") as source:
            payload = source.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(payload) > MAX_BYTES:
        raise ValueError("annotation companion exceeds the byte limit")
    return CapturedInput(path, payload, hashlib.sha256(payload).hexdigest())


def _binding(step_payload):
    if type(step_payload) is not bytes or not step_payload:
        raise ValueError("annotations require nonempty captured STEP bytes")
    return hashlib.sha256(step_payload).hexdigest(), len(step_payload)


def _saved_paths(saved_roots):
    if type(saved_roots) is not tuple or len(saved_roots) > MAX_NODES:
        raise TypeError("annotations require independently parsed saved STEP roots")
    leaves = set()
    stack = [(node, (index,)) for index, node in enumerate(saved_roots, 1)]
    visits = 0
    while stack:
        node, path = stack.pop()
        visits += 1
        if visits > MAX_NODES or len(path) > MAX_DEPTH:
            raise ValueError("saved annotation hierarchy exceeds the limit")
        if type(node) is not SavedNode or node.path != path:
            raise ValueError("annotation paths must match the actual saved hierarchy")
        if node.children:
            if len(node.children) > MAX_NODES:
                raise ValueError("saved annotation hierarchy exceeds the limit")
            stack.extend((child, path + (index,)) for index, child in enumerate(node.children, 1))
        elif node.geometry is not None:
            leaves.add(path)
        else:
            raise ValueError("annotation hierarchy has an empty geometry leaf")
    if not leaves:
        raise ValueError("annotations require saved STEP geometry")
    return leaves


def _bound_paths(paths, digest, size):
    if type(paths) is not SavedAnnotationPaths:
        raise TypeError("annotations require a byte-bound native saved path inventory")
    if paths.step_sha256 != digest or paths.step_bytes != size:
        raise ValueError("saved path inventory binding does not match captured STEP bytes")
    if len(paths.leaves) > MAX_NODES:
        raise ValueError("saved annotation hierarchy exceeds the limit")
    return frozenset(paths.leaves)


def _occurrences(values, leaves):
    if type(values) not in (list, tuple) or len(values) > MAX_NODES:
        raise ValueError("annotations require a bounded occurrence sequence")
    result = {}
    byte_bound = 256
    for row in values:
        if type(row) not in _MAPS or "path" not in row or set(row) - {"path", "pbr", "material"}:
            raise ValueError("annotation occurrence fields are path, pbr and material")
        path = row["path"]
        if (type(path) not in (list, tuple) or not 1 <= len(path) <= MAX_DEPTH
                or any(type(index) is not int or not 1 <= index <= MAX_NODES for index in path)):
            raise ValueError("annotation paths require bounded one-based integer indices")
        path = tuple(path)
        if path not in leaves or path in result:
            raise ValueError("annotation path is duplicate or not a saved geometry occurrence")
        own = appearance({key: value for key, value in row.items() if key != "path"})
        # Empty fields have no consumer effect. An entirely empty product means
        # deletion, so a rebuild cannot leave stale durable annotations behind.
        own = appearance({key: value for key, value in own.items() if value})
        byte_bound += encoded_size_bound(own) + len(path) * 12
        if byte_bound > MAX_BYTES:
            raise ValueError("annotation product exceeds the byte limit")
        result[path] = AnnotationOccurrence(path, own)
    return tuple(result[path] for path in sorted(result) if result[path].appearance)


def prepare_annotations(step_payload: bytes, paths: SavedAnnotationPaths,
                        occurrences: list | tuple) -> AnnotationProduct:
    """Encode explicit effective leaf annotations against verified saved paths."""
    digest, size = _binding(step_payload)
    leaves = _bound_paths(paths, digest, size)
    rows = _occurrences(occurrences, leaves)
    if not rows:
        return AnnotationProduct(digest, size, None, None, ())
    value = {"schema": SCHEMA, "version": VERSION, "step": {"sha256": digest, "bytes": size},
             "occurrences": [{"path": row.path, **to_value(row.appearance)} for row in rows]}
    chunks = []
    written = 0
    for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False,
                                  ensure_ascii=True).iterencode(value):
        encoded = chunk.encode("ascii")
        written += len(encoded)
        if written + 1 > MAX_BYTES:
            raise ValueError("annotation product exceeds the byte limit")
        chunks.append(encoded)
    payload = b"".join(chunks) + b"\n"
    return read_annotations(step_payload, paths, payload)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("annotation JSON contains a duplicate key")
        value[key] = item
    return value


def read_annotations(step_payload: bytes, paths: SavedAnnotationPaths,
                     payload: bytes | None) -> AnnotationProduct:
    """Read only captured companion bytes; reject drift and every old schema."""
    digest, size = _binding(step_payload)
    leaves = _bound_paths(paths, digest, size)
    if payload is None:
        return AnnotationProduct(digest, size, None, None, ())
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES:
        raise ValueError("annotation bytes exceed the limit or are empty")
    try:
        value = json.loads(payload, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("annotation bytes are not bounded JSON") from error
    if (type(value) is not dict or set(value) != {"schema", "version", "step", "occurrences"}
            or value["schema"] != SCHEMA or type(value["version"]) is not int
            or value["version"] != VERSION):
        raise ValueError("unsupported annotation schema")
    binding = value["step"]
    if (type(binding) is not dict or set(binding) != {"sha256", "bytes"}
            or type(binding["bytes"]) is not int or binding["bytes"] != size
            or binding["sha256"] != digest):
        raise ValueError("annotation binding does not match captured STEP bytes")
    rows = _occurrences(value["occurrences"], leaves)
    if not rows:
        raise ValueError("an empty annotation companion must be removed")
    return AnnotationProduct(digest, size, payload, hashlib.sha256(payload).hexdigest(), rows)
