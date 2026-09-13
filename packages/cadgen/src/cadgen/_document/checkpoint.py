"""Versioned native checkpoints for one exact retained-document revision.

The caller owns the :class:`storage.Catalog`.  This module is the only bridge
between that kernel-free byte catalog and the document's private native state.
It has no legacy readers and never converts an incompatible payload.  This
bounded proof retains the selected revision's evaluation closure and root.  Its
only optional derived data is a validated native-mesh packet cache; arbitrary
derivations and private STEP-import registry descriptors are never persisted.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import marshal
import struct
import sys
from types import MappingProxyType
from typing import Any

from .core import (Document, GeometryHandle, Revision, RevisionState,
                   _Prototype, _freeze_auxiliary)
from .identities import EvaluationIdentity, EvaluationKey, LogicalIdentity, allocation_provenance, normalize
from .native import SubelementRef, TopologyHistory, TopologyRelation, topology_map
from .resources import AdmissionDenied, ResourceAdmission, ResourceRequest
from .roots import AssemblyGroup, GeometryLeaf, root_handles, validate_root
from .storage import Catalog, ExportReceipt, Stage
from . import consumers as _consumers
from . import meshing as _meshing
from . import native as _native


CHECKPOINT_VERSION = 5
EVALUATION_SEMANTICS = "cadgen-document-evaluation-v3.closed-constructor-v1.auxiliary-v1.disjoint-dags-v1"
_MAGIC = "cadgen.document.native-checkpoint"
_MANIFEST_ROLE = "document-manifest"
_NATIVE_ROLE = "document-native"
_MESH_ROLE = "document-native-mesh-cache"
_MESH_CACHE_MAGIC = b"CGDMCHE\x00"
_MESH_CACHE_VERSION = 1
_MESH_PRODUCER_SEMANTICS = "cadgen-native-mesh-v2.consumer-v2.copier-order-v1"
MAX_MESH_CACHE_ENTRIES = 128
MAX_MESH_CACHE_INDEX_BYTES = 1024 * 1024
MAX_MESH_CACHE_BYTES = 120 * 1024**2


class CheckpointError(ValueError):
    """A checkpoint cannot be safely installed as retained native state."""


class CheckpointIncompatible(CheckpointError):
    """The checkpoint requires another schema, runtime, or evaluator."""


class CheckpointCorrupt(CheckpointError):
    """The verified catalog blobs do not contain a valid closed checkpoint."""


@dataclass(frozen=True)
class RecoveredCheckpoint:
    """A new geometry-ready owner plus explicitly historical completion facts."""

    document: Document
    revision: Revision
    catalog_revision_id: str
    historical_state: RevisionState
    historical_completed_exports: tuple[str, ...]
    historical_receipts: tuple[ExportReceipt, ...]


def _read_native_fingerprint() -> dict[str, Any]:
    version = _native.dependency_version("cadquery-ocp")
    if type(version) is not str or not version:
        raise CheckpointIncompatible("the native runtime has no stable distribution version")
    return {
        "cadquery_ocp": version,
        "codec": "BinTools_FormatVersion_VERSION_4",
    }


_CAPTURED_NATIVE_FINGERPRINT = MappingProxyType(_read_native_fingerprint())


def _native_fingerprint() -> dict[str, Any]:
    """Return the engine-owned pre-author native identity."""
    return dict(_CAPTURED_NATIVE_FINGERPRINT)


def _implementation_digest() -> str:
    """Fingerprint the loaded closed mesh producer without consulting disk."""
    functions = (
        _meshing.MeshOptions.__init__,
        _meshing.MeshOptions.__post_init__,
        _meshing.mesh_for_occurrence,
        _meshing._mesh_private,
        _meshing._pack,
        _meshing.unpack_mesh,
        _meshing._validate_ranges,
        _consumers._DocumentBridge.prototype_shape,
        _consumers._DocumentBridge.derivation,
        _consumers._DocumentBridge.save_derivation,
        Document._is_native_mesh_key,
        Document._native_mesh_derivation,
        Document._save_native_mesh_derivation,
        _consumers.RevisionConsumer.derive,
        _native.copy_shape_with_topology_order,
    )
    digest = hashlib.sha256()
    for function in functions:
        digest.update(function.__module__.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(function.__qualname__.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(marshal.dumps(function.__code__))
    return digest.hexdigest()


def _default_proof(value: Any) -> Any:
    if value is None or type(value) in (bool, int, float, str, bytes):
        return (type(value), value)
    if type(value) is tuple:
        return (tuple, tuple(_default_proof(item) for item in value))
    if type(value) is dict:
        return (dict, tuple((key, _default_proof(value[key])) for key in sorted(value)))
    if type(value) is _meshing.MeshOptions and type(vars(value)) is dict:
        return (_meshing.MeshOptions,
                tuple((key, _default_proof(item)) for key, item in sorted(vars(value).items())))
    return (type(value), value)


def _function_proof(function) -> tuple[Any, ...]:
    return (function, function.__code__, _default_proof(function.__defaults__),
            _default_proof(function.__kwdefaults__))


_MESH_FUNCTION_PROOFS = (
    (_meshing.MeshOptions, "__init__", _function_proof(_meshing.MeshOptions.__init__)),
    (_meshing.MeshOptions, "__post_init__",
     _function_proof(_meshing.MeshOptions.__post_init__)),
    (_meshing, "mesh_for_occurrence", _function_proof(_meshing.mesh_for_occurrence)),
    (_meshing, "_mesh_private", _function_proof(_meshing._mesh_private)),
    (_meshing, "_pack", _function_proof(_meshing._pack)),
    (_meshing, "unpack_mesh", _function_proof(_meshing.unpack_mesh)),
    (_meshing, "_validate_ranges", _function_proof(_meshing._validate_ranges)),
    (_consumers._DocumentBridge, "prototype_shape",
     _function_proof(_consumers._DocumentBridge.prototype_shape)),
    (_consumers._DocumentBridge, "derivation",
     _function_proof(_consumers._DocumentBridge.derivation)),
    (_consumers._DocumentBridge, "save_derivation",
     _function_proof(_consumers._DocumentBridge.save_derivation)),
    (Document, "_is_native_mesh_key", _function_proof(Document._is_native_mesh_key)),
    (Document, "_native_mesh_derivation",
     _function_proof(Document._native_mesh_derivation)),
    (Document, "_save_native_mesh_derivation",
     _function_proof(Document._save_native_mesh_derivation)),
    (_consumers.RevisionConsumer, "derive", _function_proof(_consumers.RevisionConsumer.derive)),
    (_native, "copy_shape_with_topology_order",
     _function_proof(_native.copy_shape_with_topology_order)),
)
_MESH_GLOBAL_PROOFS = (
    (_consumers, "copy_shape_with_topology_order", _consumers.copy_shape_with_topology_order),
    (_consumers, "normalize", _consumers.normalize),
    (_consumers, "_freeze_value", _consumers._freeze_value),
    (_consumers, "ResourceRequest", _consumers.ResourceRequest),
    (_consumers, "_MISSING", _consumers._MISSING),
    (_meshing, "MeshOptions", _meshing.MeshOptions),
    (_meshing, "ResourceRequest", _meshing.ResourceRequest),
    (_meshing, "asdict", _meshing.asdict),
)
_MESH_VALUE_PROOFS = (
    (_meshing, "VERSION", _default_proof(_meshing.VERSION)),
    (_meshing, "MAGIC", _default_proof(_meshing.MAGIC)),
    (_meshing, "MAX_PACKET_BYTES", _default_proof(_meshing.MAX_PACKET_BYTES)),
    (_meshing, "MAX_HEADER_BYTES", _default_proof(_meshing.MAX_HEADER_BYTES)),
    (_meshing, "MAX_TOPOLOGY_ROWS", _default_proof(_meshing.MAX_TOPOLOGY_ROWS)),
    (_meshing, "_LAYOUT", _default_proof(_meshing._LAYOUT)),
    (_meshing, "_EDGE_CLASSES", frozenset(_meshing._EDGE_CLASSES)),
)
_MESH_PRODUCER = MappingProxyType({
    "semantics": _MESH_PRODUCER_SEMANTICS,
    "implementation": _implementation_digest(),
    "python": sys.implementation.cache_tag,
    "native": MappingProxyType(dict(_CAPTURED_NATIVE_FINGERPRINT)),
})


def _mesh_producer_is_current() -> bool:
    if not all(getattr(owner, name, None) is proof[0]
               and _function_proof(proof[0]) == proof
               for owner, name, proof in _MESH_FUNCTION_PROOFS):
        return False
    if not all(getattr(owner, name, None) is value
               for owner, name, value in _MESH_GLOBAL_PROOFS):
        return False
    for owner, name, proof in _MESH_VALUE_PROOFS:
        current = getattr(owner, name, None)
        if (name == "_EDGE_CLASSES" and
                (type(current) is not set or frozenset(current) != proof)):
            return False
        if name != "_EDGE_CLASSES" and _default_proof(current) != proof:
            return False
    return True


def checkpoint_engine_version() -> str:
    """Catalog engine identity; changing it causes the disposable hard reset."""
    native = _native_fingerprint()
    return (f"document-checkpoint-v{CHECKPOINT_VERSION};"
            f"eval={EVALUATION_SEMANTICS};ocp={native['cadquery_ocp']};codec=bintools-v4;"
            f"mesh={_MESH_PRODUCER['implementation']}")


def _expect_fields(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise CheckpointCorrupt(f"invalid {what} fields")
    return value


def _nonempty(value: Any, what: str) -> str:
    if type(value) is not str or not value:
        raise CheckpointCorrupt(f"invalid {what}")
    return value


def _integer(value: Any, what: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise CheckpointCorrupt(f"invalid {what}")
    return value


def _encode_value(value: Any) -> list[Any]:
    if value is None:
        return ["none"]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        return ["int", str(value)]
    if type(value) is float:
        return ["float", value.hex()]
    if type(value) is str:
        return ["str", value]
    if type(value) is bytes:
        return ["bytes", value.hex()]
    if type(value) is tuple:
        return ["tuple", [_encode_value(item) for item in value]]
    if type(value) in (dict, MappingProxyType):
        if any(type(key) is not str for key in value):
            raise TypeError("checkpoint value mappings require string keys")
        return ["mapping", [[key, _encode_value(value[key])] for key in sorted(value)]]
    raise TypeError(f"checkpoint value is outside the closed vocabulary: {type(value).__name__}")


def _decode_value(encoded: Any) -> Any:
    if type(encoded) is not list or not encoded or type(encoded[0]) is not str:
        raise CheckpointCorrupt("invalid encoded value")
    tag = encoded[0]
    if tag == "none" and len(encoded) == 1:
        return None
    if tag == "bool" and len(encoded) == 2 and type(encoded[1]) is bool:
        return encoded[1]
    if tag == "int" and len(encoded) == 2 and type(encoded[1]) is str:
        try:
            value = int(encoded[1])
        except ValueError as exc:
            raise CheckpointCorrupt("invalid encoded integer") from exc
        if str(value) != encoded[1]:
            raise CheckpointCorrupt("encoded integer is not canonical")
        return value
    if tag == "float" and len(encoded) == 2 and type(encoded[1]) is str:
        try:
            value = float.fromhex(encoded[1])
        except (ValueError, OverflowError) as exc:
            raise CheckpointCorrupt("invalid encoded float") from exc
        if not value == value or value in (float("inf"), float("-inf")):
            raise CheckpointCorrupt("checkpoint floats must be finite")
        if value.hex() != encoded[1]:
            raise CheckpointCorrupt("encoded float is not canonical")
        return value
    if tag == "str" and len(encoded) == 2 and type(encoded[1]) is str:
        return encoded[1]
    if tag == "bytes" and len(encoded) == 2 and type(encoded[1]) is str:
        try:
            value = bytes.fromhex(encoded[1])
        except ValueError as exc:
            raise CheckpointCorrupt("invalid encoded bytes") from exc
        if value.hex() != encoded[1]:
            raise CheckpointCorrupt("encoded bytes are not canonical")
        return value
    if tag == "tuple" and len(encoded) == 2 and type(encoded[1]) is list:
        return tuple(_decode_value(item) for item in encoded[1])
    if tag == "mapping" and len(encoded) == 2 and type(encoded[1]) is list:
        result: dict[str, Any] = {}
        for pair in encoded[1]:
            if (type(pair) is not list or len(pair) != 2 or type(pair[0]) is not str
                    or pair[0] in result):
                raise CheckpointCorrupt("invalid encoded mapping")
            result[pair[0]] = _decode_value(pair[1])
        if list(result) != sorted(result):
            raise CheckpointCorrupt("encoded mapping keys are not canonical")
        return MappingProxyType(result)
    raise CheckpointCorrupt("unknown or malformed encoded value")


def _encode_ref(ref: SubelementRef) -> list[Any]:
    return [ref.input_index, ref.kind, ref.index]


def _decode_ref(value: Any, *, input_count: int, output: bool) -> SubelementRef:
    if type(value) is not list or len(value) != 3:
        raise CheckpointCorrupt("invalid topology reference")
    input_index, kind, index = value
    if output:
        if input_index is not None:
            raise CheckpointCorrupt("output topology reference names an input")
    elif (type(input_index) is not int or input_index < 0 or input_index >= input_count):
        raise CheckpointCorrupt("topology reference input is unavailable")
    _nonempty(kind, "topology kind")
    _integer(index, "topology ordinal", minimum=1)
    return SubelementRef(input_index, kind, index)


def _encode_relations(values: tuple[TopologyRelation, ...]) -> list[Any]:
    return [[_encode_ref(value.source), [_encode_ref(target) for target in value.targets]]
            for value in values]


def _decode_relations(values: Any, *, input_count: int) -> tuple[TopologyRelation, ...]:
    if type(values) is not list:
        raise CheckpointCorrupt("invalid topology relations")
    result = []
    for value in values:
        if type(value) is not list or len(value) != 2 or type(value[1]) is not list:
            raise CheckpointCorrupt("invalid topology relation")
        source = _decode_ref(value[0], input_count=input_count, output=False)
        targets = tuple(_decode_ref(item, input_count=input_count, output=True)
                        for item in value[1])
        if not targets:
            raise CheckpointCorrupt("topology relation requires a target")
        result.append(TopologyRelation(source, targets))
    return tuple(result)


def _encode_history(value: TopologyHistory) -> dict[str, Any]:
    return {
        "generated": _encode_relations(value.generated),
        "modified": _encode_relations(value.modified),
        "deleted": [_encode_ref(ref) for ref in value.deleted],
        "unchanged": _encode_relations(value.unchanged),
        "complete": value.complete,
        "reason": value.reason,
    }


def _decode_history(value: Any, *, input_count: int) -> TopologyHistory:
    value = _expect_fields(value, {"generated", "modified", "deleted", "unchanged",
                                   "complete", "reason"}, "topology history")
    if type(value["deleted"]) is not list or type(value["complete"]) is not bool:
        raise CheckpointCorrupt("invalid topology history")
    reason = value["reason"]
    if type(reason) is not str:
        raise CheckpointCorrupt("invalid topology history reason")
    deleted = tuple(_decode_ref(item, input_count=input_count, output=False)
                    for item in value["deleted"])
    return TopologyHistory(
        _decode_relations(value["generated"], input_count=input_count),
        _decode_relations(value["modified"], input_count=input_count),
        deleted,
        _decode_relations(value["unchanged"], input_count=input_count),
        value["complete"], reason,
    )


def _location_evidence(shape: Any) -> list[str]:
    transform = shape.Location().Transformation()
    return [transform.Value(row, column).hex()
            for row in range(1, 4) for column in range(1, 5)]


def _native_topology_attestation(shapes: tuple[Any, ...]) -> dict[str, Any]:
    """Describe native sharing without comparing every prototype pair.

    ``TopTools_IndexedMapOfShape`` keys shapes by ``IsSame``: orientation is
    ignored while the TShape and location must match.  A second map receives
    identity-located views, so its classes are exactly ``IsPartner`` classes.
    The explicit orientation and location evidence closes the two dimensions
    intentionally omitted by those identities.

    Class numbers are assigned on first encounter in prototype/local-topology
    order.  Consequently the table is canonical for the serialized prototype
    order and its construction is proportional to visited topology members.
    """
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopTools import TopTools_IndexedMapOfShape

    same_classes = TopTools_IndexedMapOfShape()
    partner_classes = TopTools_IndexedMapOfShape()
    identity_location = TopLoc_Location()
    locations: list[list[str]] = []
    location_indices: dict[tuple[str, ...], int] = {}
    same_class_evidence: list[list[Any]] = []
    prototypes = []
    for shape in shapes:
        local = topology_map(shape)
        members = []
        for ordinal in range(1, local.Extent() + 1):
            member = local.FindKey(ordinal)
            same_class = same_classes.Add(member)
            # Binding/API drift here must fail checkpoint creation rather than
            # silently weaken an attestation.
            if not same_classes.FindKey(same_class).IsSame(member):
                raise CheckpointError("native IsSame map semantics are unavailable")
            normalized = member.Located(identity_location)
            partner_class = partner_classes.Add(normalized)
            if not partner_classes.FindKey(partner_class).IsPartner(member):
                raise CheckpointError("native IsPartner map semantics are unavailable")
            location = _location_evidence(member)
            location_key = tuple(location)
            location_class = location_indices.get(location_key)
            if location_class is None:
                location_class = len(locations) + 1
                location_indices[location_key] = location_class
                locations.append(location)
            class_evidence = [member.ShapeType().name, location_class]
            if same_class == len(same_class_evidence) + 1:
                same_class_evidence.append(class_evidence)
            elif same_class_evidence[same_class - 1] != class_evidence:
                raise CheckpointError("native IsSame class evidence is inconsistent")
            members.append([
                same_class,
                partner_class,
                member.Orientation().name,
            ])
        prototypes.append(members)
    return {
        "version": 1,
        "same_classes": same_class_evidence,
        "partner_classes": partner_classes.Extent(),
        "locations": locations,
        "prototypes": prototypes,
    }


def _validate_native_topology(value: Any, prototype_count: int) -> None:
    value = _expect_fields(
        value, {"version", "same_classes", "partner_classes", "locations",
                "prototypes"},
        "native topology attestation",
    )
    if value["version"] != 1:
        raise CheckpointCorrupt("native topology attestation version is invalid")
    same_classes = value["same_classes"]
    if type(same_classes) is not list:
        raise CheckpointCorrupt("native same class table is invalid")
    same_count = len(same_classes)
    partner_count = _integer(value["partner_classes"], "native partner class count")
    locations = value["locations"]
    if type(locations) is not list:
        raise CheckpointCorrupt("native location class table is invalid")
    for location in locations:
        if type(location) is not list or len(location) != 12:
            raise CheckpointCorrupt("native topology location is invalid")
        for encoded in location:
            if type(encoded) is not str:
                raise CheckpointCorrupt("native topology location is invalid")
            try:
                coordinate = float.fromhex(encoded)
            except ValueError as exc:
                raise CheckpointCorrupt("native topology location is invalid") from exc
            if (not coordinate == coordinate
                    or coordinate in (float("inf"), float("-inf"))
                    or coordinate.hex() != encoded):
                raise CheckpointCorrupt("native topology location is invalid")
    used_locations: set[int] = set()
    for same_class in same_classes:
        if (type(same_class) is not list or len(same_class) != 2
                or type(same_class[0]) is not str or not same_class[0]
                or type(same_class[1]) is not int or same_class[1] < 1
                or same_class[1] > len(locations)):
            raise CheckpointCorrupt("native same class evidence is invalid")
        used_locations.add(same_class[1])
    prototypes = value["prototypes"]
    if type(prototypes) is not list or len(prototypes) != prototype_count:
        raise CheckpointCorrupt("native topology prototype table is invalid")
    seen_same: set[int] = set()
    seen_partner: set[int] = set()
    partner_by_same: dict[int, int] = {}
    for members in prototypes:
        if type(members) is not list or not members:
            raise CheckpointCorrupt("native topology membership table is invalid")
        for member in members:
            if (type(member) is not list or len(member) != 3
                    or type(member[0]) is not int or member[0] < 1
                    or member[0] > same_count
                    or type(member[1]) is not int or member[1] < 1
                    or member[1] > partner_count
                    or type(member[2]) is not str or not member[2]):
                raise CheckpointCorrupt("native topology membership is invalid")
            previous_partner = partner_by_same.setdefault(member[0], member[1])
            if previous_partner != member[1]:
                raise CheckpointCorrupt("native same class has inconsistent partner identity")
            seen_same.add(member[0])
            seen_partner.add(member[1])
    # IDs were range-checked above, so cardinality proves a gap-free table
    # without allocating a set proportional to an attacker-supplied count.
    if len(seen_same) != same_count:
        raise CheckpointCorrupt("native same classes are not canonical")
    if len(seen_partner) != partner_count:
        raise CheckpointCorrupt("native partner classes are not canonical")
    if len(used_locations) != len(locations):
        raise CheckpointCorrupt("native location classes are not canonical")


def _shape_digest(shape: Any) -> str:
    from OCP.BinTools import BinTools, BinTools_FormatVersion

    stream = BytesIO()
    BinTools.Write_s(shape, stream, False, False,
                     BinTools_FormatVersion.BinTools_FormatVersion_VERSION_4)
    return hashlib.sha256(stream.getvalue()).hexdigest()


def _write_native(shapes: tuple[Any, ...]) -> tuple[bytes, dict[str, Any]]:
    from OCP.BinTools import BinTools, BinTools_FormatVersion
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    if not shapes:
        raise CheckpointError("a native checkpoint requires retained prototypes")
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for shape in shapes:
        if shape is None or shape.IsNull():
            raise CheckpointError("a native checkpoint cannot contain null geometry")
        builder.Add(compound, shape)
    stream = BytesIO()
    BinTools.Write_s(compound, stream, False, False,
                     BinTools_FormatVersion.BinTools_FormatVersion_VERSION_4)
    return stream.getvalue(), _native_topology_attestation(shapes)


def _read_native(payload: bytes, count: int, expected_topology: Any) -> tuple[Any, ...]:
    from OCP.BinTools import BinTools
    from OCP.TopAbs import TopAbs_COMPOUND
    from OCP.TopoDS import TopoDS_Iterator, TopoDS_Shape

    if type(payload) is not bytes or not payload:
        raise CheckpointCorrupt("native checkpoint payload is empty")
    _validate_native_topology(expected_topology, count)
    shape = TopoDS_Shape()
    try:
        BinTools.Read_s(shape, BytesIO(payload))
    except Exception as exc:
        raise CheckpointCorrupt("native checkpoint payload is unreadable") from exc
    if shape.IsNull() or shape.ShapeType() != TopAbs_COMPOUND:
        raise CheckpointCorrupt("native checkpoint payload is not a shape compound")
    iterator = TopoDS_Iterator(shape)
    shapes = []
    while iterator.More():
        shapes.append(iterator.Value())
        iterator.Next()
    result = tuple(shapes)
    if len(result) != count:
        raise CheckpointCorrupt("native checkpoint prototype count disagrees")
    actual_topology = _native_topology_attestation(result)
    if actual_topology != expected_topology:
        raise CheckpointCorrupt("native checkpoint changed topology alias relationships")
    return result


def _find_alias_source(source: Any, shapes: tuple[Any, ...],
                       identities: tuple[EvaluationIdentity, ...],
                       expected: EvaluationIdentity) -> int:
    matches = [index for index, shape in enumerate(shapes)
               if identities[index] == expected and source.IsSame(shape)]
    if not matches:
        raise CheckpointError("prototype alias source is outside the checkpoint graph")
    return matches[0]


def _reachable(document: Document, revision: Revision
               ) -> tuple[dict[str, GeometryHandle], dict[str, _Prototype]]:
    pending = list(revision.evaluations)
    pending.extend(revision.features.values())
    if revision.root is not None:
        pending.extend(root_handles(revision.root))
    allocations: dict[str, GeometryHandle] = {}
    prototypes: dict[str, _Prototype] = {}
    while pending:
        handle = pending.pop()
        prototype = document._get(handle)
        previous = allocations.setdefault(handle.allocation_id, handle)
        if previous != handle:
            raise CheckpointError("one allocation names inconsistent geometry handles")
        prototypes.setdefault(handle.prototype_id, prototype)
        allocation = document._allocations[handle.allocation_id]
        pending.extend(input_handle for input_handle in allocation.inputs
                       if input_handle.allocation_id not in allocations)
    return allocations, prototypes


def _encode_root(root: Any) -> dict[str, Any] | None:
    if root is None:
        return None
    nodes: list[dict[str, Any] | None] = []
    indices: dict[int, int] = {}
    visiting: set[int] = set()

    def visit(node: Any) -> int:
        identity = id(node)
        if identity in visiting:
            raise CheckpointError("root hierarchy contains a cycle")
        if identity in indices:
            return indices[identity]
        if type(node) not in (GeometryLeaf, AssemblyGroup):
            raise CheckpointError("root hierarchy contains an unsupported node")
        index = len(nodes)
        indices[identity] = index
        nodes.append(None)
        visiting.add(identity)
        common = {
            "kind": "leaf" if type(node) is GeometryLeaf else "group",
            "node_id": node.node_id.value,
            "transform": [value.hex() for value in node.transform],
            "label": node.label,
            "appearance": _encode_value(node.appearance),
        }
        if type(node) is GeometryLeaf:
            common["allocation"] = node.geometry.allocation_id
        else:
            common["children"] = [visit(child) for child in node.children]
        visiting.remove(identity)
        nodes[index] = common
        return index

    root_index = visit(root)
    return {"root": root_index, "nodes": nodes}


def _decode_root(value: Any, handles: dict[str, GeometryHandle]) -> Any:
    if value is None:
        return None
    value = _expect_fields(value, {"root", "nodes"}, "root graph")
    if type(value["nodes"]) is not list or not value["nodes"]:
        raise CheckpointCorrupt("root graph requires nodes")
    root_index = _integer(value["root"], "root node index")
    if root_index >= len(value["nodes"]):
        raise CheckpointCorrupt("root node is unavailable")
    built: dict[int, Any] = {}
    visiting: set[int] = set()

    def build(index: int) -> Any:
        if index in built:
            return built[index]
        if index in visiting or index >= len(value["nodes"]):
            raise CheckpointCorrupt("root graph contains a cycle or bad reference")
        visiting.add(index)
        raw = value["nodes"][index]
        if type(raw) is not dict or raw.get("kind") not in {"leaf", "group"}:
            raise CheckpointCorrupt("invalid root node")
        common_fields = {"kind", "node_id", "transform", "label", "appearance"}
        expected = common_fields | ({"allocation"} if raw["kind"] == "leaf" else {"children"})
        _expect_fields(raw, expected, "root node")
        node_id = _nonempty(raw["node_id"], "root node identity")
        if (type(raw["transform"]) is not list or len(raw["transform"]) != 16
                or any(type(item) is not str for item in raw["transform"])):
            raise CheckpointCorrupt("invalid root transform")
        try:
            transform = tuple(float.fromhex(item) for item in raw["transform"])
        except ValueError as exc:
            raise CheckpointCorrupt("invalid root transform") from exc
        if type(raw["label"]) is not str:
            raise CheckpointCorrupt("invalid root label")
        appearance = _decode_value(raw["appearance"])
        try:
            if raw["kind"] == "leaf":
                allocation = _nonempty(raw["allocation"], "root allocation")
                if allocation not in handles:
                    raise CheckpointCorrupt("root allocation is unavailable")
                node = GeometryLeaf(LogicalIdentity(node_id), handles[allocation], transform,
                                    raw["label"], appearance)
            else:
                if type(raw["children"]) is not list:
                    raise CheckpointCorrupt("invalid root children")
                children = []
                for child in raw["children"]:
                    child = _integer(child, "root child index")
                    children.append(build(child))
                node = AssemblyGroup(LogicalIdentity(node_id), tuple(children), transform,
                                     raw["label"], appearance)
        except (TypeError, ValueError) as exc:
            if isinstance(exc, CheckpointCorrupt):
                raise
            raise CheckpointCorrupt("invalid root value") from exc
        visiting.remove(index)
        built[index] = node
        return node

    result = build(root_index)
    if len(built) != len(value["nodes"]):
        raise CheckpointCorrupt("root graph contains unreachable nodes")
    return result


def _manifest(document: Document, revision: Revision) -> tuple[dict[str, Any], bytes]:
    allocations, prototypes = _reachable(document, revision)
    ordered_prototypes = sorted(prototypes.items())
    shapes = tuple(prototype.shape for _, prototype in ordered_prototypes)
    shape_identities = tuple(prototype.handle.evaluation_id
                             for _, prototype in ordered_prototypes)
    native, native_topology = _write_native(shapes)
    prototype_index = {prototype_id: index
                       for index, (prototype_id, _) in enumerate(ordered_prototypes)}
    encoded_prototypes = []
    for prototype_id, prototype in ordered_prototypes:
        key = prototype.key
        if key.identity.value != prototype_id or prototype.handle.evaluation_id != key.identity:
            raise CheckpointError("prototype evaluation identity is inconsistent")
        if len(prototype.alias_sources) not in (0, len(key.inputs)):
            raise CheckpointError("prototype alias source count is inconsistent")
        alias_sources = [
            _find_alias_source(source, shapes, shape_identities, key.inputs[index])
            for index, source in enumerate(prototype.alias_sources)
        ]
        encoded_prototypes.append({
            "prototype_id": prototype_id,
            "key": {
                "operator": key.operator,
                "implementation": key.implementation,
                "parameters": _encode_value(key.parameters),
                "inputs": [identity.value for identity in key.inputs],
                "runtime": _encode_value(key.runtime),
                "volatility": key.volatility,
                "alias_provenance": _encode_value(key.alias_provenance),
            },
            "history": _encode_history(prototype.history),
            "auxiliary": _encode_value(prototype.auxiliary),
            "alias_sources": alias_sources,
            "shape_index": prototype_index[prototype_id],
            "shape_digest": _shape_digest(prototype.shape),
        })
    encoded_allocations = []
    for allocation_id, handle in sorted(allocations.items()):
        allocation = document._allocations[allocation_id]
        encoded_allocations.append({
            "allocation_id": allocation_id,
            "prototype_id": handle.prototype_id,
            "evaluation_id": handle.evaluation_id.value,
            "inputs": [item.allocation_id for item in allocation.inputs],
        })
    with document._lock:
        state = document._states[revision.revision_id]
        completed = tuple(sorted(document._completed_exports[revision.revision_id]))
    manifest = {
        "magic": _MAGIC,
        "version": CHECKPOINT_VERSION,
        "evaluation_semantics": EVALUATION_SEMANTICS,
        "native_runtime": _native_fingerprint(),
        "runtime": _encode_value(normalize(document.runtime)),
        "document_id": document.document_id,
        "native_topology": native_topology,
        "prototypes": encoded_prototypes,
        "allocations": encoded_allocations,
        "revision": {
            "revision_id": revision.revision_id,
            "source_identity": revision.source_identity,
            "features": [[identity.value, handle.allocation_id]
                         for identity, handle in sorted(revision.features.items(),
                                                        key=lambda item: item[0].value)],
            "evaluations": [handle.allocation_id for handle in revision.evaluations],
            "required_exports": list(revision.required_exports),
            "root": _encode_root(revision.root),
            "unrepresented_metadata": (None if revision.unrepresented_metadata is None
                                       else list(revision.unrepresented_metadata)),
            "request_sequence": revision._request_sequence,
            "publication_sequence": revision._publication_sequence,
            "entry_key": revision._entry_key,
            "historical_state": state.value,
            "historical_completed_exports": list(completed),
        },
    }
    return manifest, native


def _manifest_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _mesh_producer_value() -> dict[str, Any]:
    return {
        "semantics": _MESH_PRODUCER["semantics"],
        "implementation": _MESH_PRODUCER["implementation"],
        "python": _MESH_PRODUCER["python"],
        "native": dict(_MESH_PRODUCER["native"]),
    }


def _cancel_checkpoint(cancellation) -> None:
    if cancellation is not None and cancellation.is_set():
        from .resources import Cancelled

        raise Cancelled("document checkpoint was cancelled")


def _mesh_bindings(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Bind mesh ordinals to the checkpoint's exact restored topology proof."""
    topology = manifest["native_topology"]
    same_classes = topology["same_classes"]
    result = {}
    for row, members in zip(manifest["prototypes"], topology["prototypes"]):
        order = {"face": [], "edge": []}
        for member in members:
            shape_type, location_class = same_classes[member[0] - 1]
            kind = ("face" if shape_type == "TopAbs_FACE" else
                    "edge" if shape_type == "TopAbs_EDGE" else None)
            if kind is not None:
                order[kind].append([member[0], member[1], member[2], location_class])
        order_payload = _manifest_bytes({"version": 1, "order": order})
        result[row["prototype_id"]] = {
            "shape_digest": row["shape_digest"],
            "topology_digest": hashlib.sha256(order_payload).hexdigest(),
            "faces": len(order["face"]),
            "edges": len(order["edge"]),
        }
    return result


@dataclass(frozen=True)
class _MeshCachePlan:
    encoded_index: bytes
    packets: tuple[bytes, ...]
    payload_size: int


def _mesh_cache_plan(document: Document, manifest: dict[str, Any], cancellation
                     ) -> _MeshCachePlan | None:
    """Validate a bounded MRU packet inventory without copying packet bodies."""
    if not _mesh_producer_is_current():
        return None
    retained_keys = document._retained_native_mesh_keys(MAX_MESH_CACHE_ENTRIES)
    if not retained_keys:
        return None
    bindings = _mesh_bindings(manifest)
    expected_runtime = normalize(document.runtime)
    candidates = []
    candidate_bytes = 0
    body_limit = MAX_MESH_CACHE_BYTES - MAX_MESH_CACHE_INDEX_BYTES - 12
    for key in retained_keys:
        _cancel_checkpoint(cancellation)
        packet = document._derivations.get(key)
        try:
            if (type(key) is not tuple or len(key) != 6
                    or type(key[0]) is not str or key[0] not in bindings
                    or key[1] != "consumer-v2"
                    or key[2] != f"native-mesh-{_meshing.VERSION}"
                    or type(key[3]) is not tuple
                    or key[3] not in (("face",), ("face", "edge"))
                    or type(key[4]) is not tuple or type(key[5]) is not tuple
                    or key[5] != expected_runtime
                    or type(packet) is not bytes
                    or len(packet) > _meshing.MAX_PACKET_BYTES):
                continue
            header, _ = _meshing.unpack_mesh(packet)
            topology = (("face", "edge") if header["options"]["edges"] else ("face",))
            binding = bindings[key[0]]
            if (key[3] != topology or key[4] != normalize(header["options"])
                    or len(header["faces"]) != binding["faces"]
                    or len(header["edges"]) != (binding["edges"] if topology[-1] == "edge" else 0)):
                continue
            descriptor = {
                "prototype": key[0],
                "parameters": _encode_value(key[4]),
                "topology": list(topology),
                "shape_digest": binding["shape_digest"],
                "topology_digest": binding["topology_digest"],
                "faces": binding["faces"],
                "edges": binding["edges"] if topology[-1] == "edge" else 0,
                "size": len(packet),
                "sha256": hashlib.sha256(packet).hexdigest(),
            }
            if candidate_bytes + len(packet) > body_limit:
                continue
            candidates.append((descriptor, packet))
            candidate_bytes += len(packet)
        except (CheckpointError, TypeError, ValueError, KeyError, OverflowError,
                RecursionError):
            continue
    selected = []
    body_bytes = 0
    # Selection above prioritizes MRU packets; encode the chosen subset from
    # LRU to MRU so recovery insertion reconstructs the same access order.
    for descriptor, packet in reversed(candidates):
        selected.append((dict(descriptor, offset=body_bytes), packet))
        body_bytes += len(packet)
    if not selected:
        return None
    header = {
        "magic": "cadgen.document.native-mesh-cache",
        "version": _MESH_CACHE_VERSION,
        "producer": _mesh_producer_value(),
        "entries": [descriptor for descriptor, _ in selected],
    }
    encoded = _manifest_bytes(header)
    if not encoded or len(encoded) > MAX_MESH_CACHE_INDEX_BYTES:
        return None
    padding = (-len(encoded)) % 4
    size = 12 + len(encoded) + padding + body_bytes
    if size > MAX_MESH_CACHE_BYTES:
        return None
    return _MeshCachePlan(encoded, tuple(packet for _, packet in selected), size)


def _pack_mesh_cache(plan: _MeshCachePlan, cancellation) -> bytes:
    _cancel_checkpoint(cancellation)
    encoded = plan.encoded_index
    payload = b"".join((_MESH_CACHE_MAGIC, struct.pack("<I", len(encoded)), encoded,
                        b" " * ((-len(encoded)) % 4), *plan.packets))
    _cancel_checkpoint(cancellation)
    if len(payload) != plan.payload_size:
        raise CheckpointError("mesh cache plan size changed before packing")
    return payload


def _install_mesh_cache(document: Document, payload: bytes,
                        bindings: dict[str, dict[str, Any]], cancellation) -> None:
    """Install independently validated packets; malformed cache data is a miss."""
    if not _mesh_producer_is_current():
        return
    try:
        if (type(payload) is not bytes or not 12 <= len(payload) <= MAX_MESH_CACHE_BYTES
                or payload[:8] != _MESH_CACHE_MAGIC):
            return
        length, = struct.unpack_from("<I", payload, 8)
        start = 12 + length + (-length) % 4
        if not 0 < length <= MAX_MESH_CACHE_INDEX_BYTES or start > len(payload):
            return
        header = json.loads(payload[12:12 + length])
        if (_manifest_bytes(header) != payload[12:12 + length]
                or type(header) is not dict
                or set(header) != {"magic", "version", "producer", "entries"}
                or header["magic"] != "cadgen.document.native-mesh-cache"
                or header["version"] != _MESH_CACHE_VERSION
                or header["producer"] != _mesh_producer_value()
                or type(header["entries"]) is not list
                or len(header["entries"]) > MAX_MESH_CACHE_ENTRIES):
            return
        parsed = []
        offset = 0
        keys = set()
        for raw in header["entries"]:
            _cancel_checkpoint(cancellation)
            raw = _expect_fields(
                raw,
                {"prototype", "parameters", "topology", "shape_digest",
                 "topology_digest", "faces", "edges", "offset", "size", "sha256"},
                "mesh cache entry",
            )
            prototype = _nonempty(raw["prototype"], "mesh prototype")
            topology_raw = raw["topology"]
            if (type(topology_raw) is not list
                    or tuple(topology_raw) not in (("face",), ("face", "edge"))):
                return
            topology = tuple(topology_raw)
            parameters = _decode_value(raw["parameters"])
            if type(parameters) is not tuple:
                return
            size = _integer(raw["size"], "mesh packet size", minimum=12)
            if (raw["offset"] != offset or size > _meshing.MAX_PACKET_BYTES
                    or start + offset + size > len(payload)):
                return
            digest = raw["sha256"]
            if (type(digest) is not str or len(digest) != 64
                    or any(character not in "0123456789abcdef" for character in digest)):
                return
            binding = bindings.get(prototype)
            if (binding is None
                    or raw["shape_digest"] != binding["shape_digest"]
                    or raw["topology_digest"] != binding["topology_digest"]
                    or raw["faces"] != binding["faces"]
                    or raw["edges"] != (binding["edges"] if topology[-1] == "edge" else 0)):
                return
            key = (prototype, "consumer-v2", f"native-mesh-{_meshing.VERSION}",
                   topology, parameters, normalize(document.runtime))
            if key in keys:
                return
            keys.add(key)
            parsed.append((key, start + offset, size, digest, binding))
            offset += size
        if start + offset != len(payload):
            return
    except (CheckpointError, TypeError, ValueError, KeyError, UnicodeError,
            OverflowError, RecursionError, json.JSONDecodeError):
        return
    for key, offset, size, digest, binding in parsed:
        _cancel_checkpoint(cancellation)
        packet = payload[offset:offset + size]
        try:
            if hashlib.sha256(packet).hexdigest() != digest:
                continue
            header, _ = _meshing.unpack_mesh(packet)
            topology = key[3]
            if (normalize(header["options"]) != key[4]
                    or len(header["faces"]) != binding["faces"]
                    or len(header["edges"]) != (binding["edges"] if topology[-1] == "edge" else 0)
                    or topology != (("face", "edge") if header["options"]["edges"] else ("face",))):
                continue
        except (TypeError, ValueError, KeyError, OverflowError, RecursionError):
            continue
        document._save_native_mesh_derivation(key, packet)


class CheckpointCodec:
    """Encode and recover exact revisions through a caller-owned Catalog."""

    def __init__(self, catalog: Catalog, *, runtime: Any = ()) -> None:
        if not isinstance(catalog, Catalog):
            raise TypeError("a checkpoint codec requires a caller-owned Catalog")
        self.catalog = catalog
        self.runtime = runtime
        self._normalized_runtime = normalize(runtime)
        expected = checkpoint_engine_version()
        with catalog._transaction(write=False):
            actual = catalog._meta()[2]
        if actual != expected:
            raise CheckpointIncompatible(
                f"catalog engine is incompatible; open it with engine_version={expected!r}"
            )

    def _check_runtime(self) -> None:
        if normalize(self.runtime) != self._normalized_runtime:
            raise CheckpointIncompatible("checkpoint codec runtime changed after construction")

    def stage(self, document: Document, revision_id: int, *, seconds: float = 300,
              resources: ResourceRequest | None = None, cancellation=None) -> Stage:
        if not isinstance(document, Document):
            raise TypeError("checkpoint staging requires a Document")
        if type(revision_id) is not int:
            raise TypeError("checkpoint staging requires an exact integer revision")
        document._assert_owner()
        self._check_runtime()
        if normalize(document.runtime) != self._normalized_runtime:
            raise CheckpointIncompatible("document runtime differs from checkpoint codec runtime")
        request = resources or ResourceRequest(kind="checkpoint")
        if request.kind != "checkpoint":
            raise ValueError("checkpoint staging requires checkpoint resource admission")
        with document.pin(revision_id) as pin:
            with document.admission.admit(request, cancellation=cancellation):
                manifest, native = _manifest(document, pin.revision)
                has_mesh = bool(document._retained_native_mesh_keys(1))
                planning_bytes = (_meshing.MAX_HEADER_BYTES + MAX_MESH_CACHE_INDEX_BYTES
                                  if has_mesh else 0)
                if resources is not None and request.derived_bytes < planning_bytes:
                    raise AdmissionDenied(
                        "checkpoint mesh validation exceeds declared derived-byte resources")
                if resources is None and planning_bytes:
                    planning_request = ResourceRequest(
                        kind="checkpoint", cpu_slots=0, derived_bytes=planning_bytes)
                    with document.admission.admit(planning_request,
                                                  cancellation=cancellation):
                        mesh_plan = _mesh_cache_plan(document, manifest, cancellation)
                else:
                    mesh_plan = _mesh_cache_plan(document, manifest, cancellation)
                payload_size = 0 if mesh_plan is None else mesh_plan.payload_size
                if resources is not None and request.derived_bytes < payload_size:
                    raise AdmissionDenied(
                        "checkpoint mesh payload exceeds declared derived-byte resources")
                final_request = (None if resources is not None or not payload_size else
                                 ResourceRequest(kind="checkpoint", cpu_slots=0,
                                                 derived_bytes=payload_size))
                context = (document.admission.admit(final_request, cancellation=cancellation)
                           if final_request is not None else nullcontext())
                with context:
                    mesh_cache = (None if mesh_plan is None else
                                  _pack_mesh_cache(mesh_plan, cancellation))
                    metadata = {
                        "version": CHECKPOINT_VERSION,
                        "kind": _MAGIC,
                        "evaluation_semantics": EVALUATION_SEMANTICS,
                        "native_runtime": _native_fingerprint(),
                        "runtime": _encode_value(self._normalized_runtime),
                    }
                    payloads = {_MANIFEST_ROLE: _manifest_bytes(manifest),
                                _NATIVE_ROLE: native}
                    if mesh_cache is not None:
                        payloads[_MESH_ROLE] = mesh_cache
                    return self.catalog.stage(document.document_id, metadata, payloads,
                                              seconds=seconds)

    def commit(self, stage: Stage, *, expected_head: str | None) -> bool:
        if not isinstance(stage, Stage):
            raise TypeError("checkpoint commit requires a catalog Stage")
        return self.catalog.checkpoint(stage, expected_head=expected_head)

    def recover(self, document_id: str, revision_id: str | None = None, *,
                seconds: float = 60, admission: ResourceAdmission | None = None,
                resources: ResourceRequest | None = None, cancellation=None
                ) -> RecoveredCheckpoint:
        if type(document_id) is not str or not document_id:
            raise ValueError("checkpoint recovery requires a document identity")
        self._check_runtime()
        selected = self.catalog.head(document_id) if revision_id is None else revision_id
        if selected is None:
            raise KeyError(f"checkpoint document is unavailable: {document_id}")
        if type(selected) is not str or not selected:
            raise TypeError("checkpoint recovery requires an exact catalog revision")
        owner_admission = admission or ResourceAdmission()
        if resources is not None and resources.kind != "checkpoint":
            raise ValueError("checkpoint recovery requires checkpoint resource admission")
        with self.catalog.lease(selected, seconds=seconds) as lease:
            read_plan = self.catalog.plan_partitioned_read(
                lease,
                required_roles=frozenset({_MANIFEST_ROLE, _NATIVE_ROLE}),
                optional_role_limits={_MESH_ROLE: MAX_MESH_CACHE_BYTES},
            )
            optional_size = read_plan.optional_size(_MESH_ROLE)
            derived_demand = (2 * optional_size
                              + (_meshing.MAX_HEADER_BYTES if optional_size else 0))
            request = resources or ResourceRequest(
                kind="checkpoint", derived_bytes=derived_demand)
            if request.derived_bytes < derived_demand:
                raise AdmissionDenied(
                    "checkpoint mesh recovery exceeds declared derived-byte resources")
            with owner_admission.admit(request, cancellation=cancellation):
                checkpoint = self.catalog.read_partitioned(lease, read_plan)
                receipts = self.catalog.exports(lease)
                if checkpoint.document_id != document_id:
                    raise CheckpointCorrupt("catalog checkpoint belongs to another document")
                expected_metadata = {
                    "version": CHECKPOINT_VERSION,
                    "kind": _MAGIC,
                    "evaluation_semantics": EVALUATION_SEMANTICS,
                    "native_runtime": _native_fingerprint(),
                    "runtime": _encode_value(self._normalized_runtime),
                }
                if checkpoint.metadata != expected_metadata:
                    raise CheckpointIncompatible(
                        "checkpoint metadata runtime or schema is incompatible")
                if not {_MANIFEST_ROLE, _NATIVE_ROLE} <= set(checkpoint.payloads):
                    raise CheckpointCorrupt("checkpoint payload roles are invalid")
                document = Document(document_id, runtime=self.runtime,
                                    admission=owner_admission)
                if resources is None:
                    native_request = ResourceRequest(
                        kind="checkpoint", cpu_slots=0,
                        native_bytes=len(checkpoint.payloads[_NATIVE_ROLE]))
                    with owner_admission.admit(native_request, cancellation=cancellation):
                        revision, historical_state, completed, bindings = self._install(
                            document, checkpoint.payloads[_MANIFEST_ROLE],
                            checkpoint.payloads[_NATIVE_ROLE])
                else:
                    revision, historical_state, completed, bindings = self._install(
                        document, checkpoint.payloads[_MANIFEST_ROLE],
                        checkpoint.payloads[_NATIVE_ROLE])
                mesh_cache = checkpoint.payloads.get(_MESH_ROLE)
                if mesh_cache is not None:
                    _install_mesh_cache(document, mesh_cache, bindings, cancellation)
        return RecoveredCheckpoint(document, revision, selected, historical_state,
                                   completed, receipts)

    def _install(self, document: Document, manifest_payload: bytes, native: bytes
                 ) -> tuple[Revision, RevisionState, tuple[str, ...],
                            dict[str, dict[str, Any]]]:
        try:
            def reject_constant(value: str) -> None:
                raise ValueError(f"non-finite JSON constant: {value}")
            manifest = json.loads(manifest_payload, parse_constant=reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise CheckpointCorrupt("checkpoint manifest is not canonical JSON") from exc
        if _manifest_bytes(manifest) != manifest_payload:
            raise CheckpointCorrupt("checkpoint manifest encoding is not canonical")
        manifest = _expect_fields(
            manifest,
            {"magic", "version", "evaluation_semantics", "native_runtime", "runtime",
             "document_id", "native_topology", "prototypes", "allocations", "revision"},
            "checkpoint manifest",
        )
        if (manifest["magic"] != _MAGIC or type(manifest["version"]) is not int
                or manifest["version"] != CHECKPOINT_VERSION
                or manifest["evaluation_semantics"] != EVALUATION_SEMANTICS
                or manifest["native_runtime"] != _native_fingerprint()
                or _decode_value(manifest["runtime"]) != self._normalized_runtime):
            raise CheckpointIncompatible("checkpoint manifest runtime or schema is incompatible")
        if manifest["document_id"] != document.document_id:
            raise CheckpointCorrupt("checkpoint manifest document identity disagrees")
        if type(manifest["prototypes"]) is not list or type(manifest["allocations"]) is not list:
            raise CheckpointCorrupt("checkpoint geometry tables are invalid")
        shapes = _read_native(native, len(manifest["prototypes"]),
                              manifest["native_topology"])

        prototype_rows: dict[str, tuple[_Prototype, list[str]]] = {}
        for ordinal, raw in enumerate(manifest["prototypes"]):
            raw = _expect_fields(raw, {"prototype_id", "key", "history", "auxiliary", "alias_sources",
                                       "shape_index", "shape_digest"}, "prototype")
            prototype_id = _nonempty(raw["prototype_id"], "prototype identity")
            if (prototype_id in prototype_rows or type(raw["shape_index"]) is not int
                    or raw["shape_index"] != ordinal):
                raise CheckpointCorrupt("prototype order or identity is invalid")
            shape_digest = raw["shape_digest"]
            if (type(shape_digest) is not str or len(shape_digest) != 64
                    or any(character not in "0123456789abcdef" for character in shape_digest)
                    or _shape_digest(shapes[ordinal]) != shape_digest):
                raise CheckpointCorrupt("prototype native geometry identity disagrees")
            key_raw = _expect_fields(raw["key"], {"operator", "implementation", "parameters",
                                                   "inputs", "runtime", "volatility",
                                                   "alias_provenance"}, "evaluation key")
            if type(key_raw["inputs"]) is not list:
                raise CheckpointCorrupt("evaluation inputs are invalid")
            if type(key_raw["volatility"]) is not str:
                raise CheckpointCorrupt("invalid evaluation volatility")
            key = EvaluationKey(
                _nonempty(key_raw["operator"], "operator"),
                _nonempty(key_raw["implementation"], "operator implementation"),
                _decode_value(key_raw["parameters"]),
                tuple(EvaluationIdentity(_nonempty(value, "evaluation input"))
                      for value in key_raw["inputs"]),
                _decode_value(key_raw["runtime"]),
                key_raw["volatility"],
                _decode_value(key_raw["alias_provenance"]),
            )
            if key.identity.value != prototype_id:
                raise CheckpointCorrupt("evaluation key does not produce its prototype identity")
            aliases = raw["alias_sources"]
            if (type(aliases) is not list
                    or any(type(index) is not int or index < 0 or index >= len(shapes)
                           for index in aliases)
                    or len(aliases) not in (0, len(key.inputs))):
                raise CheckpointCorrupt("prototype alias sources are invalid")
            for index, identity in zip(aliases, key.inputs):
                target = manifest["prototypes"][index]
                if (type(target) is not dict
                        or target.get("prototype_id") != identity.value):
                    raise CheckpointCorrupt(
                        "prototype alias sources disagree with evaluation inputs"
                    )
            handle = GeometryHandle(document.owner_id, key.identity, prototype_id, "")
            try:
                auxiliary = _freeze_auxiliary(_decode_value(raw["auxiliary"]))
            except (ValueError, TypeError, RecursionError) as error:
                raise CheckpointCorrupt("invalid native result auxiliary data") from error
            prototype = _Prototype(
                handle, key, shapes[ordinal],
                _decode_history(raw["history"], input_count=len(key.inputs)), (),
                tuple(shapes[index] for index in aliases), auxiliary,
            )
            prototype_rows[prototype_id] = (prototype, list(key_raw["inputs"]))

        handles: dict[str, GeometryHandle] = {}
        allocation_inputs: dict[str, list[str]] = {}
        for raw in manifest["allocations"]:
            raw = _expect_fields(raw, {"allocation_id", "prototype_id", "evaluation_id", "inputs"},
                                 "allocation")
            allocation_id = _nonempty(raw["allocation_id"], "allocation identity")
            prototype_id = _nonempty(raw["prototype_id"], "allocation prototype")
            evaluation_id = _nonempty(raw["evaluation_id"], "allocation evaluation")
            if allocation_id in handles or prototype_id not in prototype_rows:
                raise CheckpointCorrupt("allocation identity or prototype is invalid")
            prototype = prototype_rows[prototype_id][0]
            if prototype.handle.evaluation_id.value != evaluation_id:
                raise CheckpointCorrupt("allocation evaluation identity disagrees")
            if type(raw["inputs"]) is not list:
                raise CheckpointCorrupt("allocation inputs are invalid")
            handles[allocation_id] = GeometryHandle(
                document.owner_id, prototype.handle.evaluation_id, prototype_id, allocation_id)
            allocation_inputs[allocation_id] = list(raw["inputs"])
        for allocation_id, input_ids in allocation_inputs.items():
            if any(type(value) is not str or value not in handles for value in input_ids):
                raise CheckpointCorrupt("allocation dependency is unavailable")
            inputs = tuple(handles[value] for value in input_ids)
            handle = handles[allocation_id]
            expected = prototype_rows[handle.prototype_id][0].key.inputs
            if tuple(item.evaluation_id for item in inputs) != expected:
                raise CheckpointCorrupt("allocation dependencies disagree with evaluation key")
        visiting: set[str] = set()
        visited: set[str] = set()
        for root_id in allocation_inputs:
            pending = [(root_id, False)]
            while pending:
                allocation_id, finish = pending.pop()
                if finish:
                    visiting.remove(allocation_id)
                    visited.add(allocation_id)
                    document._register_allocation(handles[allocation_id], tuple(
                        handles[value] for value in allocation_inputs[allocation_id]))
                    continue
                if allocation_id in visited:
                    continue
                if allocation_id in visiting:
                    raise CheckpointCorrupt("allocation dependency graph contains a cycle")
                visiting.add(allocation_id)
                pending.append((allocation_id, True))
                pending.extend((dependency, False)
                               for dependency in reversed(allocation_inputs[allocation_id]))
        representatives = {}
        for handle in handles.values():
            allocation = document._allocations[handle.allocation_id]
            key = prototype_rows[handle.prototype_id][0].key
            if normalize(allocation_provenance(allocation.inputs, document._allocations)) != key.alias_provenance:
                raise CheckpointCorrupt("allocation sharing disagrees with evaluation provenance")
            representatives.setdefault(handle.prototype_id, handle)
        for prototype_id, (prototype, _) in prototype_rows.items():
            representative = representatives.get(prototype_id)
            if representative is None:
                raise CheckpointCorrupt("prototype has no retained allocation")
            dependencies = document._allocations[representative.allocation_id].inputs
            document._prototypes[prototype_id] = _Prototype(
                representative, prototype.key, prototype.shape, prototype.history,
                dependencies, prototype.alias_sources, prototype.auxiliary)

        raw_revision = _expect_fields(
            manifest["revision"],
            {"revision_id", "source_identity", "features", "evaluations", "required_exports",
             "root", "unrepresented_metadata", "request_sequence", "publication_sequence",
             "entry_key", "historical_state", "historical_completed_exports"},
            "revision",
        )
        revision_id = _integer(raw_revision["revision_id"], "revision identity", minimum=1)
        if type(raw_revision["features"]) is not list:
            raise CheckpointCorrupt("revision features are invalid")
        features = {}
        feature_names: set[str] = set()
        for item in raw_revision["features"]:
            if (type(item) is not list or len(item) != 2 or type(item[0]) is not str
                    or not item[0] or item[0] in feature_names
                    or type(item[1]) is not str or item[1] not in handles):
                raise CheckpointCorrupt("revision feature is invalid")
            feature_names.add(item[0])
            features[LogicalIdentity(item[0])] = handles[item[1]]
        evaluations_raw = raw_revision["evaluations"]
        if (type(evaluations_raw) is not list
                or len(set(evaluations_raw)) != len(evaluations_raw)
                or any(type(value) is not str or value not in handles for value in evaluations_raw)):
            raise CheckpointCorrupt("revision evaluations are invalid")
        required = raw_revision["required_exports"]
        if type(required) is not list or any(type(path) is not str or not path for path in required):
            raise CheckpointCorrupt("revision exports are invalid")
        metadata = raw_revision["unrepresented_metadata"]
        if metadata is not None and (type(metadata) is not list
                                     or any(type(field) is not str or not field for field in metadata)):
            raise CheckpointCorrupt("revision metadata coverage is invalid")
        entry_key = raw_revision["entry_key"]
        if entry_key is not None and (type(entry_key) is not str or not entry_key):
            raise CheckpointCorrupt("revision entry key is invalid")
        root = _decode_root(raw_revision["root"], handles)
        if root is not None:
            try:
                validate_root(root, document._get)
            except (TypeError, ValueError) as exc:
                raise CheckpointCorrupt("recovered root does not validate") from exc
        state_raw = raw_revision["historical_state"]
        try:
            historical_state = RevisionState(state_raw)
        except (TypeError, ValueError) as exc:
            raise CheckpointCorrupt("historical revision state is invalid") from exc
        completed_raw = raw_revision["historical_completed_exports"]
        if (type(completed_raw) is not list
                or any(type(path) is not str or path not in required for path in completed_raw)
                or len(set(completed_raw)) != len(completed_raw)):
            raise CheckpointCorrupt("historical completed exports are invalid")
        source_identity = raw_revision["source_identity"]
        if type(source_identity) is not str:
            raise CheckpointCorrupt("revision source identity is invalid")
        request_sequence = _integer(raw_revision["request_sequence"], "request sequence")
        publication_sequence = _integer(raw_revision["publication_sequence"],
                                        "publication sequence")
        revision = Revision(
            revision_id, source_identity, MappingProxyType(features),
            tuple(handles[value] for value in evaluations_raw), tuple(required), root,
            None if metadata is None else tuple(metadata), request_sequence,
            publication_sequence, entry_key,
        )
        document._revisions[revision_id] = revision
        document._states[revision_id] = RevisionState.GEOMETRY_READY
        document._completed_exports[revision_id] = set()
        document._pins[revision_id] = 0
        document._next_revision = revision_id
        document._next_request_sequence = request_sequence
        document._next_publication_sequence = publication_sequence
        if entry_key is None:
            document._head = revision_id
        else:
            document._entry_heads[entry_key] = revision_id
        order = (request_sequence, publication_sequence)
        for path in required:
            document._output_claims[path] = order
        return revision, historical_state, tuple(completed_raw), _mesh_bindings(manifest)
