"""Native prototype meshing and a bounded packed transfer format.

The producer receives a private native copy from RevisionConsumer: OCCT is
allowed to attach triangulation there. It emits value bytes, never a native
pointer or a mutable scene. Occurrence placement and appearance are absent
from the mesh key. This candidate does not replace the public mesher until
the quality and end-to-end comparisons pass.
"""
from __future__ import annotations

from array import array
from dataclasses import asdict, dataclass
import io
import json
import math
import struct
import sys

from .resources import ResourceRequest


MAGIC = b"CGMESH\x00\x02"
VERSION = 2
MAX_HEADER_BYTES = 16 * 1024**2
MAX_PACKET_BYTES = 128 * 1024**2
MAX_TOPOLOGY_ROWS = 100_000
_EDGE_CLASSES = {"free", "boundary", "nonmanifold", "sharp", "smooth", "seam", "degenerate"}
_LAYOUT = (("positions", "f", 3), ("normals", "f", 3),
           ("indices", "I", 1), ("edgePositions", "f", 3))


@dataclass(frozen=True)
class MeshOptions:
    relative_chord: float = .0015
    angular: float = .35
    edges: bool = True

    def __post_init__(self):
        for name, maximum in (("relative_chord", 1.), ("angular", math.pi)):
            value = getattr(self, name)
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not 0 < value <= maximum):
                raise ValueError(f"mesh {name} must be positive, finite and at most {maximum}")
        if type(self.edges) is not bool:
            raise TypeError("mesh edges must be a bool")


def mesh_for_occurrence(consumer, path, options: MeshOptions = MeshOptions()) -> bytes:
    if type(options) is not MeshOptions:
        raise TypeError("meshing requires MeshOptions")
    return consumer.derive(path, f"native-mesh-{VERSION}", asdict(options),
                           lambda shape: _mesh_private(shape, options, consumer.checkpoint),
                           resources=ResourceRequest(kind="mesh", native_bytes=64 * 1024**2,
                                                     derived_bytes=2 * MAX_PACKET_BYTES))


def _pack(header, buffers, checkpoint=lambda: None):
    # Preflight before copying any attribute. Joining contiguous byte views
    # allocates the final immutable packet once (no per-attribute byte copies).
    offset = 0
    header["buffers"] = {}
    chunks = []
    for name, code, width in _LAYOUT:
        checkpoint()
        values = buffers[name]
        if values.typecode != code or values.itemsize != 4:
            raise RuntimeError("mesh transfer requires 32-bit native arrays")
        size = len(values) * 4
        offset += size
        if offset + 12 > MAX_PACKET_BYTES:
            raise ValueError("mesh exceeds the transfer limit")
        if sys.byteorder != "little":
            values.byteswap()
        header["buffers"][name] = {"offset": offset - size, "bytes": size,
                                   "count": len(values), "type": code, "width": width}
        chunks.append(memoryview(values).cast("B"))
    encoded_stream = io.BytesIO()
    for index, part in enumerate(json.JSONEncoder(separators=(",", ":"), allow_nan=False).iterencode(header)):
        if index % 1024 == 0:
            checkpoint()
        part = part.encode("utf-8")
        if encoded_stream.tell() + len(part) > MAX_HEADER_BYTES:
            raise ValueError("mesh descriptor exceeds the transfer limit")
        encoded_stream.write(part)
    encoded = encoded_stream.getvalue()
    padding = (-len(encoded)) % 4
    if 12 + len(encoded) + padding + offset > MAX_PACKET_BYTES:
        raise ValueError("mesh exceeds the transfer limit")
    checkpoint()
    packet = b"".join([MAGIC, struct.pack("<I", len(encoded)), encoded, b" " * padding, *chunks])
    checkpoint()
    return packet


def unpack_mesh(packet: bytes):
    """Validate framing and typed ranges before exposing immutable byte views."""
    if type(packet) is not bytes or not 12 <= len(packet) <= MAX_PACKET_BYTES:
        raise ValueError("invalid mesh packet length")
    if packet[:8] != MAGIC:
        raise ValueError("unsupported mesh packet")
    length, = struct.unpack_from("<I", packet, 8)
    start = 12 + length + (-length) % 4
    if not 0 < length <= MAX_HEADER_BYTES or start > len(packet):
        raise ValueError("invalid mesh descriptor length")
    try:
        header = json.loads(packet[12:12 + length])
        if type(header) is not dict or type(header["version"]) is not int or header["version"] != VERSION:
            raise ValueError("unsupported mesh descriptor")
        options = header["options"]
        if type(options) is not dict or set(options) != {"relative_chord", "angular", "edges"}:
            raise ValueError("invalid mesh options")
        MeshOptions(**options)
        deflection = header["linearDeflection"]
        if type(deflection) not in (int, float) or not math.isfinite(deflection) or deflection <= 0:
            raise ValueError("invalid mesh deflection")
        discarded = header["discardedZeroAreaTriangles"]
        if type(discarded) is not int or discarded < 0:
            raise ValueError("invalid discarded triangle count")
        rows = header["buffers"]
        if type(rows) is not dict or set(rows) != {name for name, _, _ in _LAYOUT}:
            raise ValueError("invalid mesh buffers")
        views = {}
        offset = 0
        for name, code, width in _LAYOUT:
            row = rows[name]
            if (type(row) is not dict or row.get("type") != code or type(row.get("width")) is not int or row.get("width") != width
                    or type(row.get("count")) is not int or row["count"] < 0
                    or row["count"] % width or type(row.get("offset")) is not int
                    or type(row.get("bytes")) is not int
                    or row["offset"] != offset or row["bytes"] != row["count"] * 4):
                raise ValueError("invalid mesh buffer range")
            end = offset + row["bytes"]
            if start + end > len(packet):
                raise ValueError("truncated mesh buffer")
            views[name] = memoryview(packet)[start + offset:start + end]
            offset = end
        if start + offset != len(packet):
            raise ValueError("unexpected trailing mesh data")
        if (rows["positions"]["count"] < 9 or rows["indices"]["count"] < 3
                or rows["positions"]["count"] != rows["normals"]["count"] or rows["indices"]["count"] % 3):
            raise ValueError("inconsistent mesh attribute counts")
        for key in ("origin", "min", "max"):
            vector = header["bounds"][key] if key != "origin" else header[key]
            if (type(vector) is not list or len(vector) != 3
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)):
                raise ValueError("invalid mesh bounds")
        if any(low > high for low, high in zip(header["bounds"]["min"], header["bounds"]["max"])):
            raise ValueError("inverted mesh bounds")
        vertex_count = rows["positions"]["count"] // 3
        for index, in struct.iter_unpack("<I", views["indices"]):
            if index >= vertex_count:
                raise ValueError("mesh index exceeds vertex count")
        for name in ("positions", "normals", "edgePositions"):
            if any(not math.isfinite(v) for v, in struct.iter_unpack("<f", views[name])):
                raise ValueError("nonfinite mesh coordinate")
        _validate_ranges(header["faces"], vertex_count, rows["indices"]["count"])
        _validate_ranges(header["edges"], rows["edgePositions"]["count"] // 3)
        for _, first, count, start_index, index_count in header["faces"]:
            face_indices = views["indices"][start_index * 4:(start_index + index_count) * 4]
            if any(not first <= value < first + count for value, in struct.iter_unpack("<I", face_indices)):
                raise ValueError("mesh face references another face's vertices")
    except (KeyError, TypeError, UnicodeError, OverflowError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError("invalid mesh descriptor") from error
    return header, views


def _validate_ranges(rows, vertex_count, index_count=None):
    if type(rows) is not list or len(rows) > MAX_TOPOLOGY_ROWS:
        raise ValueError("invalid mesh topology ranges")
    vertex_offset = index_offset = 0
    for ordinal, row in enumerate(rows):
        expected = 5 if index_count is not None else 4
        if type(row) is not list or len(row) != expected:
            raise ValueError("invalid mesh topology range")
        numeric = row if index_count is not None else row[:3]
        if any(type(value) is not int or value < 0 for value in numeric):
            raise ValueError("invalid mesh topology ordinal")
        if row[0] != ordinal or row[1] != vertex_offset:
            raise ValueError("noncontiguous mesh topology")
        vertex_offset += row[2]
        if vertex_offset > vertex_count:
            raise ValueError("mesh topology exceeds vertex count")
        if index_count is not None:
            if row[3] != index_offset or row[4] % 3 or row[2] < 3 or row[4] < 3:
                raise ValueError("invalid mesh face indices")
            index_offset += row[4]
            if index_offset > index_count:
                raise ValueError("mesh topology exceeds index count")
        elif (row[3] not in _EDGE_CLASSES
              or (row[2] != 0 if row[3] == "degenerate" else row[2] < 2)):
            raise ValueError("invalid mesh edge class or point count")
    if vertex_offset != vertex_count or (index_count is not None and index_offset != index_count):
        raise ValueError("incomplete mesh topology coverage")


def _mesh_private(shape, options, checkpoint=lambda: None):
    """Mesh an exclusively owned shape, checking cancellation between native calls.

    Deflection is an absolute OCCT target derived from the world bounding
    diagonal, clamped at native tolerance. It is not a proven global surface
    error bound; float32 encoding adds its own quantization error. Native OCCT
    meshing/sampling scratch is an admission estimate, not a hard allocator cap.
    """
    from OCP.Bnd import Bnd_Box
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepLib import BRepLib_ToolTriangulatedShape
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.GCPnts import GCPnts_TangentialDeflection
    from OCP.GeomAbs import GeomAbs_C0
    from OCP.IMeshTools import IMeshTools_Parameters
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopTools import TopTools_IndexedMapOfShape, TopTools_IndexedDataMapOfShapeListOfShape
    from OCP.TopoDS import TopoDS

    checkpoint()
    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, bounds, False, False)
    if bounds.IsVoid() or bounds.IsOpen():
        raise ValueError("meshing requires finite nonempty geometry")
    values = bounds.Get()
    diagonal = math.dist(values[:3], values[3:])
    if not math.isfinite(diagonal) or diagonal <= 0:
        raise ValueError("meshing requires a positive finite bounding diagonal")
    origin = tuple(values[i] * .5 + values[i + 3] * .5 for i in range(3))
    linear = max(diagonal * options.relative_chord, 1e-7)
    BRepTools.Clean_s(shape)
    parameters = IMeshTools_Parameters()
    parameters.Deflection = parameters.DeflectionInterior = linear
    parameters.Angle = parameters.AngleInterior = options.angular
    parameters.Relative = parameters.InParallel = False
    parameters.ControlSurfaceDeflection = True
    parameters.EnableControlSurfaceDeflectionAllSurfaces = True
    checkpoint()
    mesher = BRepMesh_IncrementalMesh(shape, parameters)
    checkpoint()
    if not mesher.IsDone():
        raise RuntimeError("native tessellation did not complete")
    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
    if faces.Extent() > MAX_TOPOLOGY_ROWS:
        raise ValueError("mesh exceeds the topology limit")
    buffers = {name: array(code) for name, code, _ in _LAYOUT}
    positions, normals, indices = (buffers[key] for key in ("positions", "normals", "indices"))
    def reserve(byte_count):
        checkpoint()
        if sum(len(v) * 4 for v in buffers.values()) + byte_count + 12 > MAX_PACKET_BYTES:
            raise ValueError("mesh exceeds the transfer limit")

    face_ranges = []
    discarded_zero_area = 0
    for ordinal in range(faces.Extent()):
        checkpoint()
        face = TopoDS.Face_s(faces.FindKey(ordinal + 1))
        location = TopLoc_Location()
        triangles = BRep_Tool.Triangulation_s(face, location)
        if triangles is None or not triangles.NbTriangles():
            raise RuntimeError(f"native tessellation omitted face {ordinal}")
        reserve(triangles.NbNodes() * 24 + triangles.NbTriangles() * 12)
        BRepLib_ToolTriangulatedShape.ComputeNormals_s(face, triangles)
        if not triangles.HasNormals():
            raise RuntimeError(f"native tessellation has no surface normals for face {ordinal}")
        transform = location.Transformation()
        reversed_face = face.Orientation() == TopAbs_REVERSED
        sign = -1 if reversed_face else 1
        reverse_winding = reversed_face != transform.IsNegative()
        # OCCT can retain pole/sliver triangles whose distinct native nodes
        # become identical or collinear only after the required float32
        # transport. Test the actual transported, origin-relative positions;
        # an exactly zero cross product contributes no surface and makes the
        # packet topologically misleading. Compacting afterward removes its
        # orphan pole nodes while preserving every finite-area OCCT triangle.
        face_positions, face_normals = array("f"), array("f")
        for index in range(1, triangles.NbNodes() + 1):
            if index % 1024 == 1:
                checkpoint()
            point = triangles.Node(index).Transformed(transform)
            normal = triangles.Normal(index).Transformed(transform)
            face_positions.extend(
                (point.X() - origin[0], point.Y() - origin[1], point.Z() - origin[2]))
            face_normals.extend(
                (normal.X() * sign, normal.Y() * sign, normal.Z() * sign))
        kept_triangles = array("I")
        referenced_nodes = bytearray(triangles.NbNodes())
        for index in range(1, triangles.NbTriangles() + 1):
            if index % 1024 == 1:
                checkpoint()
            a, b, c = triangles.Triangle(index).Get()
            if reverse_winding:
                b, c = c, b
            a, b, c = a - 1, b - 1, c - 1
            pa = face_positions[a * 3:a * 3 + 3]
            pb = face_positions[b * 3:b * 3 + 3]
            pc = face_positions[c * 3:c * 3 + 3]
            ux, uy, uz = (pb[axis] - pa[axis] for axis in range(3))
            vx, vy, vz = (pc[axis] - pa[axis] for axis in range(3))
            cross = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
            if cross == (0., 0., 0.):
                discarded_zero_area += 1
                continue
            kept_triangles.extend((a, b, c))
            referenced_nodes[a] = referenced_nodes[b] = referenced_nodes[c] = 1
        if not kept_triangles:
            raise RuntimeError(f"native tessellation face {ordinal} has no finite-area triangles")
        vertex_start, index_start = len(positions) // 3, len(indices)
        remap = array("I", [0]) * triangles.NbNodes()
        referenced_count = 0
        for source, referenced in enumerate(referenced_nodes):
            if not referenced:
                continue
            remap[source] = vertex_start + referenced_count
            referenced_count += 1
            positions.extend(face_positions[source * 3:source * 3 + 3])
            normals.extend(face_normals[source * 3:source * 3 + 3])
        for offset in range(0, len(kept_triangles), 3):
            a, b, c = kept_triangles[offset:offset + 3]
            indices.extend((remap[a], remap[b], remap[c]))
        face_ranges.append([ordinal, vertex_start, referenced_count,
                            index_start, len(indices) - index_start])
    if not face_ranges:
        raise ValueError("meshing requires geometry containing faces")

    edge_ranges = []
    if options.edges:
        edges = TopTools_IndexedMapOfShape()
        adjacent = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapes_s(shape, TopAbs_EDGE, edges)
        TopExp.MapShapesAndUniqueAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, adjacent)
        if edges.Extent() > MAX_TOPOLOGY_ROWS:
            raise ValueError("mesh exceeds the topology limit")
        lines = buffers["edgePositions"]
        for ordinal in range(edges.Extent()):
            checkpoint()
            edge = TopoDS.Edge_s(edges.FindKey(ordinal + 1))
            start = len(lines) // 3
            if BRep_Tool.Degenerated_s(edge):
                edge_ranges.append([ordinal, start, 0, "degenerate"])
                continue
            parents = []
            parent_count = 0
            if adjacent.Contains(edge):
                # Read endpoints: OCP's Python iterator has material
                # per-list startup cost even for tiny native collections.
                collection = adjacent.FindFromKey(edge)
                parent_count = collection.Extent()
                if parent_count:
                    parents = [TopoDS.Face_s(collection.First())]
                if parent_count == 2:
                    parents.append(TopoDS.Face_s(collection.Last()))
            if parent_count > 2:
                kind = "nonmanifold"
            elif parent_count == 0:
                kind = "free"
            elif any(BRep_Tool.IsClosed_s(edge, face) for face in parents):
                kind = "seam"
            elif len(parents) < 2:
                kind = "boundary"
            elif BRep_Tool.Continuity_s(edge, *parents) == GeomAbs_C0:
                kind = "sharp"
            else:
                kind = "smooth"
            curve = BRepAdaptor_Curve(edge)
            points = GCPnts_TangentialDeflection(curve, options.angular, linear)
            reserve(points.NbPoints() * 12)
            for index in range(1, points.NbPoints() + 1):
                if index % 1024 == 1:
                    checkpoint()
                point = points.Value(index)
                lines.extend((point.X() - origin[0], point.Y() - origin[1], point.Z() - origin[2]))
            if len(lines) // 3 - start < 2:
                raise RuntimeError(f"native tessellation omitted edge {ordinal}")
            edge_ranges.append([ordinal, start, len(lines) // 3 - start, kind])
    return _pack({"version": VERSION, "options": asdict(options),
                  "linearDeflection": linear, "origin": origin,
                  "discardedZeroAreaTriangles": discarded_zero_area,
                  "bounds": {"min": values[:3], "max": values[3:]},
                  "faces": face_ranges, "edges": edge_ranges}, buffers, checkpoint)
