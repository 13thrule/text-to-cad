"""Exact resident-revision inspection, independent of exchange files and meshes.

Face/edge ordinals are zero-based TopExp kind-map ordinals, exactly as in the
native mesh packet. References are coordinates, not security capabilities or
persistent names: every query validates owner, revision, path and prototype.
Native history uses a different, one-based all-topology map. Crossing revisions
requires an explicit evaluation/input correspondence; this API never guesses it.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal
from types import MappingProxyType

from .consumers import OccurrencePath, RevisionConsumer, StaleOccurrencePath
from .resources import ResourceRequest
from .roots import IDENTITY_TRANSFORM

MAX_BATCH = 64
MAX_TOPOLOGY = 100_000
Kind = Literal["component", "face", "edge"]


class InvalidTopologyReference(ValueError):
    """A reference does not identify topology in this exact pinned revision."""


@dataclass(frozen=True)
class TopologyReference:
    path: OccurrencePath
    prototype_id: str
    kind: Kind = "component"
    ordinal: int | None = None

    def __post_init__(self):
        if type(self.path) is not OccurrencePath or type(self.prototype_id) is not str or not 0 < len(self.prototype_id) <= 1024:
            raise TypeError("topology references require an exact occurrence path and prototype")
        self.path.__post_init__()
        if (len(self.path.owner_id) > 1024 or len(self.path.nodes) > 128
                or any(len(node) > 1024 for node in self.path.nodes)):
            raise InvalidTopologyReference("topology reference path exceeds the limit")
        if type(self.kind) is not str or self.kind not in {"component", "face", "edge"}:
            raise InvalidTopologyReference("unsupported topology reference kind")
        if self.kind == "component":
            if self.ordinal is not None:
                raise InvalidTopologyReference("component references have no ordinal")
        elif type(self.ordinal) is not int or not 0 <= self.ordinal < MAX_TOPOLOGY:
            raise InvalidTopologyReference("face/edge references require a bounded zero-based ordinal")

    def to_value(self):
        return MappingProxyType({"version": 1, "owner": self.path.owner_id,
                                 "revision": self.path.revision_id, "path": self.path.nodes,
                                 "prototype": self.prototype_id, "kind": self.kind, "ordinal": self.ordinal})

    @classmethod
    def from_value(cls, value):
        """Decode the closed JSON reference schema at the worker boundary."""
        if (type(value) not in (dict, MappingProxyType)
                or set(value) != {"version", "owner", "revision", "path", "prototype", "kind", "ordinal"}
                or type(value["version"]) is not int or value["version"] != 1
                or type(value["path"]) not in (tuple, list) or not 0 < len(value["path"]) <= 128):
            raise InvalidTopologyReference("invalid topology reference value schema")
        return cls(OccurrencePath(value["owner"], value["revision"], tuple(value["path"])),
                   value["prototype"], value["kind"], value["ordinal"])


def _validate(consumer, ref):
    if type(ref) is not TopologyReference:
        raise TypeError("inspection requires immutable TopologyReference values")
    # Also validate the constructor contract for deserializers bypassing init.
    ref.__post_init__()
    try:
        occurrence = consumer.occurrence(ref.path.nodes)
    except StaleOccurrencePath as error:
        raise InvalidTopologyReference("occurrence is absent from the pinned revision") from error
    if ref.path != occurrence.path or ref.prototype_id != occurrence.prototype_id:
        raise InvalidTopologyReference("reference owner, revision or prototype does not match")


def reference(consumer: RevisionConsumer, path: OccurrencePath,
              kind: Kind = "component", ordinal: int | None = None) -> TopologyReference:
    """Validate a selected mesh ordinal against actual native topology."""
    if type(path) is not OccurrencePath:
        raise TypeError("a topology reference requires an exact OccurrencePath")
    occurrence = consumer.occurrence(path.nodes)
    ref = TopologyReference(path, occurrence.prototype_id, kind, ordinal)
    _validate(consumer, ref)
    if kind != "component":
        consumer.query_value(path, lambda shape, _: _check_ordinal(shape, kind, ordinal),
                             resources=ResourceRequest(kind="query", native_bytes=64 * 1024**2))
    else:
        consumer.checkpoint()
    return ref


def _map(shape, kind):
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_SOLID, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape
    mapping = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, {"face": TopAbs_FACE, "edge": TopAbs_EDGE,
                              "solid": TopAbs_SOLID, "vertex": TopAbs_VERTEX}[kind], mapping)
    if mapping.Extent() > MAX_TOPOLOGY:
        raise ValueError("inspection exceeds the topology limit")
    return mapping


def _check_ordinal(shape, kind, ordinal):
    if ordinal >= _map(shape, kind).Extent():
        raise InvalidTopologyReference("topology ordinal is absent from the native prototype")
    return None


def _placed(shape, matrix):
    """Share immutable geometry for OCCT placements; copy general affine work."""
    if not all(math.isfinite(value) for value in matrix):
        raise ValueError("world inspection requires a finite composed occurrence transform")
    if matrix == IDENTITY_TRANSFORM:
        return shape
    from OCP.gp import gp_GTrsf, gp_Mat, gp_XYZ, gp_Trsf, gp_Other
    from OCP.TopLoc import TopLoc_Location
    from OCP.BRepBuilderAPI import BRepBuilderAPI_GTransform, BRepBuilderAPI_Transform
    linear = gp_Mat(*(matrix[row * 4 + col] for row in range(3) for col in range(3)))
    if linear.IsSingular():
        raise ValueError("world inspection requires a nonsingular occurrence transform")
    general = gp_GTrsf(linear, gp_XYZ(matrix[3], matrix[7], matrix[11]))
    general.SetForm()
    if general.Form() == gp_Other:
        # Never hand the retained prototype to a mutating transform. The
        # builder creates a private transformed result; no copy is retained.
        builder = BRepBuilderAPI_GTransform(shape, general, True)
        if not builder.IsDone():
            raise RuntimeError("native inspection transform did not complete")
        return builder.Shape()
    placement = gp_Trsf()
    placement.SetValues(*matrix[:12])
    if placement.IsNegative() or placement.ScaleFactor() != 1.:
        builder = BRepBuilderAPI_Transform(shape, placement, True)
        if not builder.IsDone():
            raise RuntimeError("native inspection transform did not complete")
        return builder.Shape()
    return shape.Moved(TopLoc_Location(placement), False)


def _bounds(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    if box.IsVoid():
        return None
    if box.IsOpen():
        raise ValueError("inspection requires finite native geometry")
    values = box.Get()
    return {"min": values[:3], "max": values[3:]}


def _measure(shape, dimension):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    if dimension == "area":
        BRepGProp.SurfaceProperties_s(shape, props, True, False)
    elif dimension == "length":
        BRepGProp.LinearProperties_s(shape, props, True, False)
    else:
        BRepGProp.VolumeProperties_s(shape, props, True, True, False)
    magnitude = abs(props.Mass())
    return magnitude, tuple(props.CentreOfMass().Coord()) if magnitude > 0 else None


def _facts(shape, kind, checkpoint):
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopoDS import TopoDS
    result = {"bounds": _bounds(shape), "units": {"length": "mm", "area": "mm²", "volume": "mm³"}}
    if kind == "face":
        face = TopoDS.Face_s(shape)
        result["geometry_kind"] = BRepAdaptor_Surface(face).GetType().name.removeprefix("GeomAbs_").lower()
        result["area"], result["centroid"] = _measure(face, "area")
        result["centroid_basis"] = "area" if result["centroid"] is not None else None
        result["orientation"] = face.Orientation().name.removeprefix("TopAbs_").lower()
    elif kind == "edge":
        edge = TopoDS.Edge_s(shape)
        degenerate = BRep_Tool.Degenerated_s(edge)
        result["geometry_kind"] = "degenerate" if degenerate else BRepAdaptor_Curve(edge).GetType().name.removeprefix("GeomAbs_").lower()
        result["length"], result["centroid"] = (0., None) if degenerate else _measure(edge, "length")
        result["centroid_basis"] = "length" if result["centroid"] is not None else None
        result["closed"] = BRep_Tool.IsClosed_s(edge)
    else:
        result["geometry_kind"] = shape.ShapeType().name.removeprefix("TopAbs_").lower()
        mappings = {key: _map(shape, key) for key in ("solid", "face", "edge", "vertex")}
        result["counts"] = {key: mapping.Extent() for key, mapping in mappings.items()}
        area, area_center = _measure(shape, "area")
        length, length_center = _measure(shape, "length")
        result.update(area=area, edge_length=length, volume=None, volume_status="no-solid")
        # Volume is the sum of valid solids, not an implicit boolean union.
        # Evaluate solids separately so reversed orientations cannot cancel mass.
        volumes = []
        for i in range(1, mappings["solid"].Extent() + 1):
            checkpoint()
            solid = mappings["solid"].FindKey(i)
            if not BRepCheck_Analyzer(solid).IsValid():
                result["volume_status"] = "invalid-solid"
                break
            volume, center = _measure(solid, "volume")
            if center is None:
                result["volume_status"] = "zero-volume-solid"
                break
            volumes.append((volume, center))
        else:
            if volumes:
                result["volume"] = sum(volume for volume, _ in volumes)
                result["volume_status"] = "sum-of-solids"
        if result["volume"] is not None:
            result["centroid"] = tuple(sum(v * c[a] for v, c in volumes) / result["volume"] for a in range(3))
            result["centroid_basis"] = "volume"
        else:
            result["centroid"] = area_center if area > 0 else length_center
            result["centroid_basis"] = "area" if area > 0 else "length" if length > 0 else None
    return result


def inspect_batch(consumer: RevisionConsumer, requests: tuple[TopologyReference, ...], *,
                  space: Literal["world", "prototype"] = "world") -> tuple:
    """Return an ordered immutable batch, or fail without a partial result.

    Work is synchronous on the consumer's owner thread. Grouping by occurrence
    shares topology maps; repeated references compute once. Native calls finish
    before cancellation checkpoints. Admission bounds are estimates, not a hard
    OCCT allocator limit. Units follow cadgen's model convention of millimetres.
    """
    if type(requests) is not tuple or not 0 < len(requests) <= MAX_BATCH:
        raise ValueError(f"inspection requires an immutable batch of 1..{MAX_BATCH} references")
    if type(space) is not str or space not in {"world", "prototype"}:
        raise ValueError("inspection space must be world or prototype")
    grouped = {}
    for ref in requests:
        _validate(consumer, ref)
        grouped.setdefault(ref.path, {})[ref] = None
    results = {}
    for path, unique in grouped.items():
        refs = tuple(unique)
        def query(shape, placement):
            maps = {kind: _map(shape, kind) for kind in {ref.kind for ref in refs} - {"component"}}
            for ref in refs:
                if ref.kind != "component" and ref.ordinal >= maps[ref.kind].Extent():
                    raise InvalidTopologyReference("topology ordinal is absent from the native prototype")
            values = []
            for ref in refs:
                consumer.checkpoint()
                selected = shape if ref.kind == "component" else maps[ref.kind].FindKey(ref.ordinal + 1)
                native = _placed(selected, placement) if space == "world" else selected
                facts = _facts(native, ref.kind, consumer.checkpoint)
                facts.update(space=space, reference=ref.to_value())
                values.append(facts)
            consumer.checkpoint()
            return values
        values = consumer.query_value(path, query, resources=ResourceRequest(kind="query", native_bytes=64 * 1024**2))
        results.update(zip(refs, values))
    return tuple(results[ref] for ref in requests)
