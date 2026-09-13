#!/usr/bin/env python3
"""Bounded correctness comparison for retained native and legacy JS meshes.

This is benchmark-only tooling.  It deliberately imports the candidate private
OCCT mesher and the retired SURF/JavaScript path as two independent consumers
of the same freshly constructed native shape.  It is not a production fallback
and its diagnostic stage times are not benchmark evidence unless the report was
created during a separately recorded serial measurement window.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import select
import struct
import subprocess
import sys
import time
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[4]
WORKER = Path(__file__).with_name("mesh_compare_worker.mjs")
DEFAULT_SCRATCH = ROOT / "models/tmp/document-engine-mesh-compare"
ALL_CASES = ("plate", "cylinder", "sphere", "torus", "trimmed_cut", "curved")
TESS_MAGIC = 0x53534554
TESS_VERSION = 4
MAX_FACE_SAMPLES = 64
FACE_GRID = 9
EDGE_SAMPLES = 65
MAX_TRIANGLES = 250_000
RUNG_FACTORS = (1., .5, .25)


def _check(deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError("mesh comparison exceeded its original fixture budget")


@dataclass(frozen=True)
class Mesh:
    positions: tuple[tuple[float, float, float], ...]
    normals: tuple[tuple[float, float, float], ...]
    indices: tuple[int, ...]
    faces: tuple[tuple[int, int, int], ...]  # ordinal, index start, index count
    edges: tuple[tuple[int, tuple[tuple[float, float, float], ...]], ...]
    bounds: dict[str, list[float]]
    target: float
    producer_discarded_zero_area: int
    packet_bytes: int


class NodeWorker:
    def __init__(self, timeout: float):
        started = time.monotonic()
        self.process = subprocess.Popen(
            ["node", str(WORKER)], cwd=ROOT, text=True, bufsize=1,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.timeout = timeout
        ready = self._read()
        self.setup_ms = (time.monotonic() - started) * 1000
        if ready.get("ready") is not True:
            self.close(force=True)
            raise RuntimeError(f"JS comparison worker did not start: {ready}")
        self.runtime = ready
        self.sequence = 0

    def _read(self) -> dict[str, Any]:
        assert self.process.stdout is not None
        readable, _, _ = select.select([self.process.stdout], [], [], self.timeout)
        if not readable:
            self.close(force=True)
            raise TimeoutError(f"JS comparison worker exceeded {self.timeout:g}s")
        line = self.process.stdout.readline()
        if not line:
            assert self.process.stderr is not None
            error = self.process.stderr.read()
            raise RuntimeError(f"JS comparison worker exited: {error.strip()}")
        return json.loads(line)

    def run(self, source: Path, output: Path, *, chord: float,
            loop: float, angular: float) -> dict[str, Any]:
        self.sequence += 1
        request = {
            "id": self.sequence,
            "input": str(source),
            "output": str(output),
            "chordTolerance": chord,
            "loopTolerance": loop,
            "angleTolerance": angular,
        }
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        response = self._read()
        if response.get("id") != self.sequence or response.get("error"):
            raise RuntimeError(f"JS comparison request failed: {response}")
        return response

    def close(self, force: bool = False) -> None:
        if self.process.poll() is not None:
            return
        if not force:
            try:
                assert self.process.stdin is not None
                self.sequence += 1
                self.process.stdin.write(json.dumps(
                    {"id": self.sequence, "command": "close"}) + "\n")
                self.process.stdin.flush()
                self._read()
                self.process.wait(timeout=2)
                return
            except Exception:
                pass
        self.process.kill()
        self.process.wait(timeout=2)


def _built(builder: Any, label: str) -> Any:
    if hasattr(builder, "Build"):
        builder.Build()
    if hasattr(builder, "IsDone") and not builder.IsDone():
        raise RuntimeError(f"fixture operation failed: {label}")
    shape = builder.Shape()
    if shape.IsNull():
        raise RuntimeError(f"fixture operation returned null geometry: {label}")
    return shape


def _plate() -> Any:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    base = BRepPrimAPI_MakeBox(gp_Pnt(-40., -25., 0.), 80., 50., 6.).Shape()
    fillet = BRepFilletAPI_MakeFillet(base)
    edges = TopExp_Explorer(base, TopAbs_EDGE)
    while edges.More():
        edge = TopoDS.Edge_s(edges.Current())
        curve = BRepAdaptor_Curve(edge)
        a, b = curve.Value(curve.FirstParameter()), curve.Value(curve.LastParameter())
        if abs(a.Z() - b.Z()) > 5.9:
            fillet.Add(4., edge)
        edges.Next()
    shape = _built(fillet, "plate fillets")
    for x in (-28., 28.):
        for y in (-13., 13.):
            tool = BRepPrimAPI_MakeCylinder(
                gp_Ax2(gp_Pnt(x, y, -1.), gp_Dir(0., 0., 1.)), 3., 8.).Shape()
            shape = _built(BRepAlgoAPI_Cut(shape, tool), "plate through hole")
    return shape


def _cylinder() -> Any:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Trsf, gp_Vec

    shape = BRepPrimAPI_MakeCylinder(10., 20.).Shape()
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(25., -8., 4.))
    return shape.Moved(TopLoc_Location(transform))


def _sphere() -> Any:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
    return BRepPrimAPI_MakeSphere(10.).Shape()


def _torus() -> Any:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeTorus
    return BRepPrimAPI_MakeTorus(15., 4.).Shape()


def _trimmed_cut() -> Any:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    box = BRepPrimAPI_MakeBox(20., 15., 10.).Shape()
    fillet = BRepFilletAPI_MakeFillet(box)
    edges = TopExp_Explorer(box, TopAbs_EDGE)
    while edges.More():
        fillet.Add(1., TopoDS.Edge_s(edges.Current()))
        edges.Next()
    rounded = _built(fillet, "trimmed fixture fillets")
    tool = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(2., 7., -2.), gp_Dir(0., 0., 1.)), 4., 14.).Shape()
    return _built(BRepAlgoAPI_Cut(rounded, tool), "trimmed side cut")


def _curved() -> Any:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeSphere
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    shape = BRepPrimAPI_MakeCylinder(6., 30.).Shape()
    shape = _built(BRepAlgoAPI_Fuse(
        shape, BRepPrimAPI_MakeSphere(gp_Pnt(0., 0., 0.), 6.).Shape()),
        "curved lower cap")
    shape = _built(BRepAlgoAPI_Fuse(
        shape, BRepPrimAPI_MakeSphere(gp_Pnt(0., 0., 30.), 6.).Shape()),
        "curved upper cap")
    bore = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(-8., 0., 15.), gp_Dir(1., 0., 0.)), 2., 16.).Shape()
    return _built(BRepAlgoAPI_Cut(shape, bore), "curved transverse bore")


FACTORIES: dict[str, Callable[[], Any]] = {
    "plate": _plate,
    "cylinder": _cylinder,
    "sphere": _sphere,
    "torus": _torus,
    "trimmed_cut": _trimmed_cut,
    "curved": _curved,
}


def _f32(data: memoryview | bytes) -> tuple[float, ...]:
    return tuple(value for value, in struct.iter_unpack("<f", data))


def _u32(data: memoryview | bytes) -> tuple[int, ...]:
    return tuple(value for value, in struct.iter_unpack("<I", data))


def _points(values: tuple[float, ...], origin=(0., 0., 0.)) -> tuple[tuple[float, float, float], ...]:
    return tuple((values[index] + origin[0], values[index + 1] + origin[1],
                  values[index + 2] + origin[2])
                 for index in range(0, len(values), 3))


def _native_mesh(packet: bytes) -> Mesh:
    from cadgen._document.meshing import unpack_mesh

    header, views = unpack_mesh(packet)
    positions = _points(_f32(views["positions"]), tuple(header["origin"]))
    normals = _points(_f32(views["normals"]))
    indices = _u32(views["indices"])
    edge_values = _points(_f32(views["edgePositions"]), tuple(header["origin"]))
    edges = tuple((row[0] + 1, edge_values[row[1]:row[1] + row[2]])
                  for row in header["edges"] if row[2])
    faces = tuple((row[0] + 1, row[3], row[4]) for row in header["faces"])
    return Mesh(positions, normals, indices, faces, edges, header["bounds"],
                float(header["linearDeflection"]),
                int(header["discardedZeroAreaTriangles"]), len(packet))


def _js_mesh(path: Path, chord: float, scale: float) -> Mesh:
    payload = path.read_bytes()
    if len(payload) < 12:
        raise ValueError("truncated TESS packet")
    magic, version, header_length = struct.unpack_from("<III", payload)
    if magic != TESS_MAGIC or version != TESS_VERSION or 12 + header_length > len(payload):
        raise ValueError("unsupported TESS packet")
    header = json.loads(payload[12:12 + header_length])
    offset = 12 + header_length

    def take(count: int, kind: str) -> tuple[Any, ...]:
        nonlocal offset
        end = offset + count * 4
        if end > len(payload):
            raise ValueError("truncated TESS array")
        result = _f32(payload[offset:end]) if kind == "f" else _u32(payload[offset:end])
        offset = end
        return result

    positions = _points(take(header["positionCount"], "f"))
    normals = _points(take(header["normalCount"], "f"))
    take(header["faceOrdCount"], "f")
    indices = take(header["indexCount"], "I")
    take(header["sideOrdCount"], "I")
    edges = []
    for edge in header["edges"]:
        edges.append((edge["ord"], _points(take(edge["count"], "f"))))
    if offset != len(payload):
        raise ValueError("unexpected TESS packet tail")
    faces = tuple((row["ord"], row["indexStart"], row["indexCount"])
                  for row in header["faceRanges"])
    return Mesh(positions, normals, indices, faces, tuple(edges), header["bounds"],
                chord * scale, 0, len(payload))


def _cross(a, b, c):
    u = tuple(b[i] - a[i] for i in range(3))
    v = tuple(c[i] - a[i] for i in range(3))
    return (u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0])


def _norm(value) -> float:
    return math.sqrt(sum(component * component for component in value))


def _exact(shape) -> dict[str, Any]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    maps = {}
    for name, kind in (("faces", TopAbs_FACE), ("edges", TopAbs_EDGE),
                       ("solids", TopAbs_SOLID)):
        mapped = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, kind, mapped)
        maps[name] = mapped
    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, bounds, False, False)
    raw = bounds.Get()
    volume_props, area_props = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, volume_props)
    BRepGProp.SurfaceProperties_s(shape, area_props)
    return {
        "valid": bool(BRepCheck_Analyzer(shape).IsValid()),
        "bounds": {"min": list(raw[:3]), "max": list(raw[3:])},
        "diagonal": math.dist(raw[:3], raw[3:]),
        "volume": float(volume_props.Mass()),
        "area": float(area_props.Mass()),
        **{f"{name}Count": mapped.Extent() for name, mapped in maps.items()},
        "faceMap": maps["faces"],
        "edgeMap": maps["edges"],
    }


def _native_shape_digest(shape) -> str:
    from OCP.BinTools import BinTools, BinTools_FormatVersion

    stream = BytesIO()
    BinTools.Write_s(shape, stream, False, False,
                     BinTools_FormatVersion.BinTools_FormatVersion_VERSION_4)
    return hashlib.sha256(stream.getvalue()).hexdigest()


def _point_distance(point, target) -> float:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt

    distance = BRepExtrema_DistShapeShape(
        BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex(), target)
    if not distance.IsDone():
        raise RuntimeError("exact point distance failed")
    return float(distance.Value())


def _copy_input(shape, exact):
    """Prove each copied ordinal's source identity through OCCT copy history."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    started = time.perf_counter()
    copier = BRepBuilderAPI_Copy(shape, True, False)
    copied = copier.Shape()
    copy_ms = (time.perf_counter() - started) * 1000
    correspondence = {}
    for name, kind in (("face", TopAbs_FACE), ("edge", TopAbs_EDGE)):
        mapped = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(copied, kind, mapped)
        source = exact[name + "Map"]
        inverse = {}
        for ordinal in range(1, source.Extent() + 1):
            image = copier.ModifiedShape(source.FindKey(ordinal))
            index = mapped.FindIndex(image)
            if image.IsNull() or index <= 0 or index in inverse:
                raise RuntimeError("copy has no exact one-to-one topology correspondence")
            inverse[index] = ordinal
        if len(inverse) != mapped.Extent():
            raise RuntimeError("copy topology correspondence is incomplete")
        correspondence[name] = inverse
    return copied, correspondence, copy_ms


def _source_ordinals(mesh, correspondence):
    return replace(mesh, faces=tuple((correspondence["face"][ordinal], start, count)
                                    for ordinal, start, count in mesh.faces),
                   edges=tuple((correspondence["edge"][ordinal], points)
                               for ordinal, points in mesh.edges))


def _distance_to_segments(point, starts, ends):
    import numpy as np
    vectors = ends - starts
    denominator = np.einsum("ij,ij->i", vectors, vectors)
    fraction = np.divide(np.einsum("ij,ij->i", point - starts, vectors), denominator,
                         out=np.zeros(len(starts)), where=denominator > 0)
    residual = point - (starts + np.clip(fraction, 0, 1)[:, None] * vectors)
    return np.einsum("ij,ij->i", residual, residual)


def _distance_to_triangles(points, triangles, deadline):
    """Independent Euclidean point/triangle distances; bounded one-point blocks."""
    import numpy as np
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    ab, ac = b - a, c - a
    normals = np.cross(ab, ac)
    squared = np.einsum("ij,ij->i", normals, normals)
    aa = np.einsum("ij,ij->i", ab, ab)
    bb = np.einsum("ij,ij->i", ac, ac)
    mixed = np.einsum("ij,ij->i", ab, ac)
    denominator = aa * bb - mixed * mixed
    result = []
    for point in points:
        _check(deadline)
        delta = point - a
        signed = np.einsum("ij,ij->i", delta, normals)
        projection = delta - np.divide(signed, squared, out=np.zeros(len(a)), where=squared > 0)[:, None] * normals
        pa = np.einsum("ij,ij->i", projection, ab)
        pc = np.einsum("ij,ij->i", projection, ac)
        u = np.divide(bb * pa - mixed * pc, denominator, out=np.zeros(len(a)), where=denominator > 0)
        v = np.divide(aa * pc - mixed * pa, denominator, out=np.zeros(len(a)), where=denominator > 0)
        inside = (denominator > 0) & (u >= 0) & (v >= 0) & (u + v <= 1)
        distances = np.divide(signed * signed, squared, out=np.full(len(a), np.inf), where=inside)
        distances = np.minimum(distances, _distance_to_segments(point, a, b))
        distances = np.minimum(distances, _distance_to_segments(point, b, c))
        distances = np.minimum(distances, _distance_to_segments(point, c, a))
        result.append(math.sqrt(max(0., float(distances.min()))))
    return result


def _oracle_self_test():
    import numpy as np
    triangle = np.array([[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]])
    points = np.array([[.25, .25, 0.], [.25, .25, 2.], [-1., 0., 0.], [1., 1., 0.], [0., 0., 0.]])
    expected = [0., 2., 1., math.sqrt(.5), 0.]
    shift = np.array([25., -8., 4.])
    variants = ((points, triangle), (points, triangle[:, ::-1]), (points + shift, triangle + shift))
    for samples, triangles in variants:
        actual = _distance_to_triangles(samples, triangles, time.monotonic() + 2)
        if not np.allclose(actual, expected, rtol=1e-12, atol=1e-12):
            raise RuntimeError(f"independent triangle-distance oracle self-test failed: {actual}")
    degenerate = np.array([[[0., 0., 0.], [0., 0., 0.], [1., 0., 0.]]])
    if _distance_to_triangles(np.array([[1., 1., 0.]]), degenerate, time.monotonic() + 2) != [1.]:
        raise RuntimeError("degenerate triangle-distance oracle self-test failed")
    return {"passed": True, "checks": 16, "coverage": ["interior", "plane distance", "edge", "vertex", "reversal", "translation", "degenerate triangle"]}


def _surface_oracle(face):
    """Independent closed-form oracle for the four exact corpus surface types."""
    import numpy as np
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools
    from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Sphere, GeomAbs_Torus
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.gp import gp_Pnt, gp_Vec

    surface = BRepAdaptor_Surface(face, True)
    kind = surface.GetType()
    names = {GeomAbs_Plane: "plane", GeomAbs_Cylinder: "cylinder",
             GeomAbs_Sphere: "sphere", GeomAbs_Torus: "torus"}
    if kind not in names:
        raise RuntimeError(f"corpus surface {kind} has no independent analytic oracle")
    primitive = getattr(surface, names[kind].title())()
    center = np.array(primitive.Location().Coord())
    axis = np.array(primitive.Axis().Direction().Coord()) if kind != GeomAbs_Sphere else None
    sign = -1. if face.Orientation() == TopAbs_REVERSED else 1.
    # Fillet cylinders may have a left-handed native parametric frame. Its
    # normal is dU×dV, so radial-outward alone is not the surface orientation.
    if not primitive.Position().Direct():
        sign = -sign

    def evaluate(points):
        delta = np.asarray(points) - center
        if kind == GeomAbs_Plane:
            return np.abs(delta @ axis), np.broadcast_to(axis * sign, delta.shape)
        if kind == GeomAbs_Sphere:
            length = np.linalg.norm(delta, axis=1)
            normals = delta / length[:, None]
            distance = np.abs(length - primitive.Radius())
        else:
            radial = delta - (delta @ axis)[:, None] * axis
            length = np.linalg.norm(radial, axis=1)
            normals = radial / length[:, None]
            if kind == GeomAbs_Cylinder:
                distance = np.abs(length - primitive.Radius())
            else:
                tube = delta - primitive.MajorRadius() * normals
                radius = np.linalg.norm(tube, axis=1)
                normals = tube / radius[:, None]
                distance = np.abs(radius - primitive.MinorRadius())
        return distance, normals * sign
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    point, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
    surface.D1(u0 + (u1 - u0) * .381966, v0 + (v1 - v0) * .381966, point, du, dv)
    derivative_normal = np.array(du.Crossed(dv).Coord())
    length = float(np.linalg.norm(derivative_normal))
    if not math.isfinite(length) or length <= 0:
        raise RuntimeError("native parametric derivative normal is undefined at oracle control point")
    derivative_normal *= (-1. if face.Orientation() == TopAbs_REVERSED else 1.) / length
    _, analytic_normal = evaluate([point.Coord()])
    if float(analytic_normal[0] @ derivative_normal) < 1 - 1e-9:
        raise RuntimeError("analytic normal oracle disagrees with exact native surface derivatives")
    return surface, names[kind], evaluate


def _independent_face_points(face, surface):
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON
    from OCP.gp import gp_Pnt2d
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    if not all(map(math.isfinite, (u0, u1, v0, v1))):
        raise RuntimeError("corpus face has unbounded UV domain")
    points = []
    for i in range(FACE_GRID):
        for j in range(FACE_GRID):
            u, v = u0 + (u1 - u0) * (i + .5) / FACE_GRID, v0 + (v1 - v0) * (j + .5) / FACE_GRID
            if BRepClass_FaceClassifier(face, gp_Pnt2d(u, v), 1e-9).State() in (TopAbs_IN, TopAbs_ON):
                points.append(surface.Value(u, v).Coord())
    if not points:
        raise RuntimeError("independent trimmed face grid contains no valid sample")
    return points


def _mesh_quality(mesh: Mesh, exact: dict[str, Any], deadline: float) -> dict[str, Any]:
    import numpy as np
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopoDS import TopoDS

    face_map, edge_map = exact["faceMap"], exact["edgeMap"]
    if not mesh.indices or len(mesh.indices) % 3 or len(mesh.indices) // 3 > MAX_TRIANGLES:
        raise ValueError("mesh exceeds the bounded triangle inventory")
    positions, normals = np.asarray(mesh.positions), np.asarray(mesh.normals)
    if (positions.shape != normals.shape or positions.ndim != 2 or positions.shape[1] != 3
            or not np.isfinite(positions).all() or not np.isfinite(normals).all()
            or min(mesh.indices) < 0 or max(mesh.indices) >= len(positions)):
        raise ValueError("invalid finite mesh buffers")
    offset = 0
    for ordinal, start, count in sorted(mesh.faces, key=lambda row: row[1]):
        if (not 1 <= ordinal <= face_map.Extent() or start != offset or count <= 0 or count % 3):
            raise ValueError("face ranges do not partition the mesh")
        offset += count
    if len({row[0] for row in mesh.faces}) != len(mesh.faces) or offset != len(mesh.indices):
        raise ValueError("face ranges do not partition the mesh")
    face_ords = {row[0] for row in mesh.faces}
    expected_faces = set(range(1, face_map.Extent() + 1))
    face_area_errors = []
    sampled_errors = []
    reverse_errors = []
    analytic_errors = []
    analytic_winding_disagreements = 0
    maximum_normal_angle = 0.
    maximum_vertex_normal_angle = 0.
    surface_types = {}
    mesh_area = 0.
    signed_volume = 0.
    zero_area = sub_quantization_area = disagreements = near_orthogonal = 0
    disagreement_faces: set[int] = set()
    minimum_twice_area = math.inf
    min_normal_cosine = 1.
    quantization = max(exact["diagonal"] * 2 ** -20, 1e-9)
    welded_edges: dict[tuple[Any, Any], list[int]] = {}

    def key(point):
        return tuple(round(value / quantization) for value in point)

    for ordinal, start, count in mesh.faces:
        _check(deadline)
        props = GProp_GProps()
        face = TopoDS.Face_s(face_map.FindKey(ordinal))
        BRepGProp.SurfaceProperties_s(face, props)
        exact_area = float(props.Mass())
        area = 0.
        triangle_count = count // 3
        sample_step = max(1, math.ceil(triangle_count / MAX_FACE_SAMPLES))
        sampled = 0
        for local in range(0, count, 3):
            ids = mesh.indices[start + local:start + local + 3]
            a, b, c = (mesh.positions[index] for index in ids)
            cross = _cross(a, b, c)
            twice_area = _norm(cross)
            minimum_twice_area = min(minimum_twice_area, twice_area)
            area += twice_area / 2
            signed_volume += sum((
                a[0] * (b[1] * c[2] - b[2] * c[1]),
                a[1] * (b[2] * c[0] - b[0] * c[2]),
                a[2] * (b[0] * c[1] - b[1] * c[0]),
            )) / 6
            if twice_area == 0:
                zero_area += 1
            elif twice_area <= quantization * quantization:
                sub_quantization_area += 1
            else:
                average_normal = tuple(sum(mesh.normals[index][axis] for index in ids)
                                       for axis in range(3))
                normal_length = _norm(average_normal)
                cosine = (sum(cross[axis] * average_normal[axis] for axis in range(3))
                          / (twice_area * normal_length)) if normal_length else -1.
                min_normal_cosine = min(min_normal_cosine, cosine)
                near_orthogonal += abs(cosine) <= 1e-6
                if cosine < -1e-6:
                    disagreements += 1
                    disagreement_faces.add(ordinal)
            for first, second in ((a, b), (b, c), (c, a)):
                ka, kb = key(first), key(second)
                identity = (ka, kb) if ka < kb else (kb, ka)
                row = welded_edges.setdefault(identity, [0, 0])
                row[0] += 1
                row[1] += 1 if ka < kb else -1
            if local // 3 % sample_step == 0 and sampled < MAX_FACE_SAMPLES:
                centroid = tuple((a[axis] + b[axis] + c[axis]) / 3 for axis in range(3))
                mids = [tuple((first[axis] + second[axis]) / 2 for axis in range(3))
                        for first, second in ((a, b), (b, c), (c, a))]
                sampled_errors.extend(_point_distance(point, face) for point in (centroid, *mids))
                sampled += 1
        mesh_area += area
        face_area_errors.append(abs(area - exact_area) / max(exact_area, 1e-12))
        surface, kind, oracle = _surface_oracle(face)
        surface_types[ordinal] = kind
        triangles = positions[np.asarray(mesh.indices[start:start + count]).reshape((-1, 3))]
        centroids = triangles.mean(axis=1)
        probes = np.concatenate((centroids, (triangles[:, 0] + triangles[:, 1]) * .5,
                                 (triangles[:, 1] + triangles[:, 2]) * .5,
                                 (triangles[:, 2] + triangles[:, 0]) * .5))
        errors, _ = oracle(probes)
        if not np.isfinite(errors).all():
            raise RuntimeError("analytic oracle returned a non-finite surface distance")
        analytic_errors.extend(errors.tolist())
        exact_points = _independent_face_points(face, surface)
        self_errors, _ = oracle(exact_points)
        if float(self_errors.max()) > exact["diagonal"] * 1e-10:
            raise RuntimeError("analytic oracle disagrees with exact native surface points")
        reverse_errors.extend(_distance_to_triangles(np.asarray(exact_points), triangles, deadline))
        cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        lengths = np.linalg.norm(cross, axis=1)
        reliable = lengths > quantization * quantization
        _, analytic_normals = oracle(centroids)
        cosines = np.einsum("ij,ij->i", cross[reliable] / lengths[reliable, None], analytic_normals[reliable])
        if len(cosines):
            analytic_winding_disagreements += int((cosines <= 0).sum())
            maximum_normal_angle = max(maximum_normal_angle, float(np.arccos(np.clip(cosines, -1, 1)).max()))
        vertex_ids = np.unique(mesh.indices[start:start + count])
        _, expected_normals = oracle(positions[vertex_ids])
        normal_cosines = np.einsum("ij,ij->i", normals[vertex_ids], expected_normals)
        if not np.isfinite(cosines).all() or not np.isfinite(normal_cosines).all():
            raise RuntimeError("analytic oracle returned a non-finite surface normal")
        maximum_vertex_normal_angle = max(maximum_vertex_normal_angle, float(np.arccos(np.clip(normal_cosines, -1, 1)).max()))

    exact_edge_ords = set(range(1, edge_map.Extent() + 1))
    represented_edge_ords = {ordinal for ordinal, _ in mesh.edges}
    if (len(represented_edge_ords) != len(mesh.edges)
            or represented_edge_ords - exact_edge_ords):
        raise ValueError("display edge identity inventory is invalid")
    edge_errors = []
    reverse_edge_errors = []
    for ordinal, points in mesh.edges:
        _check(deadline)
        if len(points) < 2:
            raise ValueError("represented display edge contains no segment")
        edge = TopoDS.Edge_s(edge_map.FindKey(ordinal))
        values = np.asarray(points)
        if values.shape != (len(points), 3) or not np.isfinite(values).all():
            raise ValueError("display edge coordinates are not finite 3D points")
        mids = (values[:-1] + values[1:]) * .5
        # Every displayed segment's midpoint is checked; vertices alone can be
        # exact while a coarse chord crosses far away from its native curve.
        edge_errors.extend(_point_distance(point, edge) for point in np.concatenate((values, mids)))
        curve = BRepAdaptor_Curve(edge)
        first, last = curve.FirstParameter(), curve.LastParameter()
        for parameter in np.linspace(first, last, EDGE_SAMPLES):
            point = np.array(curve.Value(float(parameter)).Coord())
            reverse_edge_errors.append(math.sqrt(float(_distance_to_segments(point, values[:-1], values[1:]).min())))
    non_two = sum(count != 2 for count, _ in welded_edges.values())
    winding_mismatch = sum(count == 2 and winding != 0
                           for count, winding in welded_edges.values())
    actual_bounds = {
        "min": [min(point[axis] for point in mesh.positions) for axis in range(3)],
        "max": [max(point[axis] for point in mesh.positions) for axis in range(3)],
    }
    support_errors = [
        abs(actual_bounds[side][axis] - exact["bounds"][side][axis])
        for side in ("min", "max") for axis in range(3)
    ]
    return {
        "vertices": len(mesh.positions),
        "triangles": len(mesh.indices) // 3,
        "packetBytes": mesh.packet_bytes,
        "producerDiscardedZeroAreaTriangles": mesh.producer_discarded_zero_area,
        "targetAbsoluteChord": mesh.target,
        "faceCoverage": {
            "expected": sorted(expected_faces), "represented": sorted(face_ords),
            "complete": face_ords == expected_faces,
        },
        "edgeCoverage": {
            "expected": sorted(exact_edge_ords),
            "represented": sorted(represented_edge_ords),
            "missing": sorted(exact_edge_ords - represented_edge_ords),
        },
        "sampledFaceError": {
            "samples": len(sampled_errors),
            "max": max(sampled_errors, default=0.),
            "rms": math.sqrt(sum(value * value for value in sampled_errors)
                             / max(1, len(sampled_errors))),
        },
        "analyticSurfaceError": {"samples": len(analytic_errors), "max": max(analytic_errors, default=0.),
                                 "surfaceTypes": surface_types, "normalOracleCheckedAgainstNativeDerivatives": True},
        "exactFaceToMeshError": {"samples": len(reverse_errors), "max": max(reverse_errors, default=0.)},
        "sampledEdgeErrorMax": max(edge_errors, default=0.),
        "exactEdgeToPolylineErrorMax": max(reverse_edge_errors, default=0.),
        "exactEdgeSamples": len(reverse_edge_errors),
        "displayEdgeSamples": len(edge_errors),
        "meshArea": mesh_area,
        "totalAreaRelativeError": abs(mesh_area - exact["area"]) / max(exact["area"], 1e-12),
        "maxFaceAreaRelativeError": max(face_area_errors, default=0.),
        "signedVolume": signed_volume,
        "volumeRelativeError": abs(signed_volume - exact["volume"]) / max(exact["volume"], 1e-12),
        "normalWinding": {
            "zeroAreaTriangles": zero_area,
            "subQuantizationAreaTriangles": sub_quantization_area,
            "minimumTwiceArea": minimum_twice_area,
            "disagreements": disagreements,
            "disagreementFaces": sorted(disagreement_faces),
            "nearOrthogonalTriangles": near_orthogonal,
            "minimumCosine": min_normal_cosine,
            "analyticOrientationDisagreements": analytic_winding_disagreements,
            "maximumTriangleToAnalyticNormalAngle": maximum_normal_angle,
            "maximumVertexToAnalyticNormalAngle": maximum_vertex_normal_angle,
            "maximumNormalLengthError": float(np.abs(np.linalg.norm(normals, axis=1) - 1).max()),
        },
        "weldedTopology": {
            "quantization": quantization,
            "nonTwoIncidentSegments": non_two,
            "orientationMismatchSegments": winding_mismatch,
        },
        "axisSilhouetteExtentErrorMax": max(support_errors),
        "meshBounds": actual_bounds,
    }


def _strip_exact(exact: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in exact.items()
            if key not in {"faceMap", "edgeMap", "degenerateEdges"}}


def _quality_pass(quality: dict[str, Any], exact: dict[str, Any],
                  degenerate_edges: set[int], target: float, angular: float) -> tuple[bool, list[str]]:
    failures = []
    if not quality["faceCoverage"]["complete"]:
        failures.append("incomplete face coverage")
    missing = set(quality["edgeCoverage"]["missing"])
    if missing - degenerate_edges:
        failures.append("nondegenerate edge coverage missing")
    if quality["normalWinding"]["zeroAreaTriangles"]:
        failures.append("zero-area triangles")
    if quality["normalWinding"]["disagreements"]:
        failures.append("winding disagrees with vertex normals")
    if quality["normalWinding"]["analyticOrientationDisagreements"]:
        failures.append("triangle orientation disagrees with exact outward surface normals")
    if quality["normalWinding"]["maximumNormalLengthError"] > 1e-5:
        failures.append("transported vertex normals are not unit length")
    if (quality["normalWinding"]["maximumTriangleToAnalyticNormalAngle"] > angular
            or quality["normalWinding"]["maximumVertexToAnalyticNormalAngle"] > angular):
        failures.append("normal fidelity exceeds common angular target")
    if quality["weldedTopology"]["nonTwoIncidentSegments"]:
        failures.append("coordinate-welded mesh is not closed with two incident triangles")
    if quality["weldedTopology"]["orientationMismatchSegments"]:
        failures.append("coordinate-welded segment orientations disagree")
    if quality["signedVolume"] <= 0 and exact["volume"] > 0:
        failures.append("closed solid has nonpositive signed mesh volume")
    if quality["volumeRelativeError"] > .01:
        failures.append("mesh volume differs by more than 1%")
    if quality["totalAreaRelativeError"] > .02:
        failures.append("mesh area differs by more than 2%")
    if quality["maxFaceAreaRelativeError"] > .02:
        failures.append("a corresponding face area differs by more than 2%")
    for name, error in (("sampled trimmed-face", quality["sampledFaceError"]["max"]),
                        ("all-triangle analytic surface", quality["analyticSurfaceError"]["max"]),
                        ("independent exact-face-to-mesh", quality["exactFaceToMeshError"]["max"]),
                        ("display-edge-to-native-curve", quality["sampledEdgeErrorMax"]),
                        ("independent exact-edge-to-polyline", quality["exactEdgeToPolylineErrorMax"]),
                        ("axis support extent", quality["axisSilhouetteExtentErrorMax"])):
        if not math.isfinite(error) or error > target:
            failures.append(f"{name} error exceeds common absolute target")
    return not failures, failures


def _produce(producer, shape, exact, folder, stem, worker, options, deadline):
    from cadgen._document.meshing import MeshOptions, _mesh_private
    from cadgen._internal.surface_extract import extract_surface_component

    _check(deadline)
    copied, correspondence, copy_ms = _copy_input(shape, exact)
    artifacts = {}
    coverage = None
    if producer == "native":
        started = time.perf_counter()
        payload = _mesh_private(copied, MeshOptions(options["chord"], options["angular"], True))
        produced = time.perf_counter()
        path = folder / (stem + ".cgmesh")
        path.write_bytes(payload)
        if path.read_bytes() != payload:
            raise RuntimeError("native comparison artifact differs from the produced bytes")
        mesh = _source_ordinals(_native_mesh(payload), correspondence)
        stages = {"copy": copy_ms, "tessellateAndPack": (produced - started) * 1000}
        artifacts["packet"] = str(path.relative_to(ROOT))
    else:
        started = time.perf_counter()
        surf = extract_surface_component(copied)
        produced = time.perf_counter()
        surf_path = folder / (stem + ".surf")
        surf_path.write_bytes(surf)
        path = folder / (stem + ".tess")
        node = worker.run(surf_path, path, chord=options["chord"], loop=options["loop"], angular=options["angular"])
        payload = path.read_bytes()
        if node["sourceSha256"] != hashlib.sha256(surf).hexdigest() or node["packetSha256"] != hashlib.sha256(payload).hexdigest():
            raise RuntimeError("JS comparison transfer differs from the captured source/output bytes")
        mesh = _source_ordinals(_js_mesh(path, options["chord"], node["scale"]), correspondence)
        stages = {"copy": copy_ms, "surfaceExtractAndPack": (produced - started) * 1000,
                  **{key: node["stagesMs"][key] for key in ("decode", "tessellate", "pack")}}
        coverage = {key: node[key] for key in ("sourceFaceOrds", "meshFaceOrds", "sourceEdgeOrds", "meshEdgeOrds", "omittedEdges")}
        artifacts.update(packet=str(path.relative_to(ROOT)), surf=str(surf_path.relative_to(ROOT)),
                         surfaceSha256=hashlib.sha256(surf).hexdigest())
    # Native-history correspondence, artifact IO and the independent quality
    # oracle are outside the production boundary, on both sides.
    compute_ms = sum(stages.values())
    _check(deadline)
    quality = _mesh_quality(mesh, exact, deadline)
    passed, failures = _quality_pass(quality, exact, exact["degenerateEdges"],
                                     exact["commonTarget"], exact["commonAngular"])
    if producer == "javascript":
        omitted = coverage["omittedEdges"]
        omitted_source = {correspondence["edge"][row["ord"]] for row in omitted}
        if omitted_source != exact["degenerateEdges"] or any(row["hasCurve"] for row in omitted):
            passed = False
            failures.append("JS omitted edges are not exactly explicit degenerates")
    return {"options": options, "passed": passed, "failures": failures, "quality": quality,
            "packetSha256": hashlib.sha256(payload).hexdigest(), "artifacts": artifacts,
            "stagesDiagnosticMs": stages, "productionDiagnosticMs": compute_ms,
            "coverageFromSource": coverage,
            "copyToSourceOrdinals": {key: [value[i] for i in sorted(value)] for key, value in correspondence.items()}}


def run_case(name: str, folder: Path, worker: NodeWorker, args) -> dict[str, Any]:
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS
    import statistics

    case_started = time.monotonic()
    deadline = case_started + args.timeout
    shape = FACTORIES[name]()
    exact = _exact(shape)
    if not exact["valid"] or exact["solidsCount"] != 1:
        raise RuntimeError(f"{name} fixture is not one valid solid")
    before = _native_shape_digest(shape)
    exact["degenerateEdges"] = {ordinal for ordinal in range(1, exact["edgeMap"].Extent() + 1)
                                if BRep_Tool.Degenerated_s(TopoDS.Edge_s(exact["edgeMap"].FindKey(ordinal)))}
    exact["commonTarget"] = exact["diagonal"] * args.target_relative_error
    exact["commonAngular"] = args.target_angular_error
    calibration, selected = {}, {}
    for producer, chord, loop in (("native", args.native_relative_chord, None),
                                   ("javascript", args.js_chord, args.js_loop)):
        calibration[producer] = []
        for rung, factor in enumerate(RUNG_FACTORS):
            options = {"chord": chord * factor, "angular": args.angular * math.sqrt(factor),
                       "loop": None if loop is None else loop * factor}
            sample = _produce(producer, shape, exact, folder, f"{name}.{producer}.calibration-{rung}",
                              worker, options, deadline)
            calibration[producer].append(sample)
            if sample["passed"]:
                selected[producer] = sample
                break
    paired = set(selected) == {"native", "javascript"}
    measured = []
    measurement_failures = []
    if paired and args.serial_window:
        # Coarsest passing rung is fixed before timing; performance never picks
        # quality. One explicit per-case primer precedes five measured pairs.
        for iteration in range(args.iterations + 1):
            samples = {}
            order = ("native", "javascript") if iteration % 2 == 0 else ("javascript", "native")
            for producer in order:
                sample = _produce(producer, shape, exact, folder,
                                  f"{name}.{producer}.{'prime' if iteration == 0 else iteration}",
                                  worker, selected[producer]["options"], deadline)
                failures = list(sample["failures"])
                if sample["packetSha256"] != selected[producer]["packetSha256"]:
                    failures.append("packed output differs from its calibrated immutable bytes")
                if failures:
                    measurement_failures.append({"producer": producer, "iteration": iteration, "failures": failures})
                samples[producer] = {"productionMs": sample["productionDiagnosticMs"],
                                     "stagesMs": sample["stagesDiagnosticMs"],
                                     "packetSha256": sample["packetSha256"],
                                     "quality": sample["quality"], "failures": failures}
            if iteration:
                measured.append({"order": order, **samples})
    stable = before == _native_shape_digest(shape)
    if not stable:
        raise RuntimeError("a pipeline mutated the shared native source shape")
    qualified = paired and not measurement_failures
    timing = None
    if qualified and args.serial_window:
        medians = {producer: statistics.median(row[producer]["productionMs"] for row in measured)
                   for producer in ("native", "javascript")}
        timing = {"mediansMs": medians,
                  "javascriptToNativeRatio": medians["javascript"] / medians["native"]}
    _check(deadline)
    return {"case": name, "status": "matched" if qualified else "unsupported-quality",
            "exact": _strip_exact(exact), "commonAbsoluteErrorTarget": exact["commonTarget"],
            "geometryInput": {"sameFactoryInstance": True, "independentPrivateCopies": True,
                              "completeCopyHistoryCorrespondence": True, "originalBytesUnchanged": stable,
                              "nativeShapeSha256": before, "units": "millimetres"},
            "calibration": calibration,
            "selectedOptions": {producer: sample["options"] for producer, sample in selected.items()},
            "qualityQualifiedPair": qualified, "measurementFailures": measurement_failures,
            "measuredSamples": measured,
            "qualifiedTiming": timing,
            "elapsedDiagnosticMs": (time.monotonic() - case_started) * 1000}


def _safe_scratch(path: str) -> Path:
    result = Path(path)
    if not result.is_absolute():
        result = ROOT / result
    result = result.resolve()
    try:
        result.relative_to((ROOT / "models/tmp").resolve())
    except ValueError as exc:
        raise ValueError("mesh comparison artifacts must stay under models/tmp") from exc
    return result


def _source_fingerprints() -> dict[str, str]:
    paths = {
        "candidate": ROOT / "packages/cadgen/src/cadgen/_document/meshing.py",
        "surfaceExtractor": ROOT / "packages/cadgen/src/cadgen/_internal/surface_extract.py",
        "javascriptTessellator": ROOT / "packages/cadgen-js/src/lib/surf/tessellate.js",
        "javascriptCodec": ROOT / "packages/cadgen-js/src/lib/surf/tessellationCache.js",
        "javascriptEvaluator": ROOT / "packages/cadgen-js/src/lib/surf/evaluate.js",
        "javascriptContainer": ROOT / "packages/cadgen-js/src/lib/surf/container.js",
        "javascriptDependencies": ROOT / "packages/cadgen-js/package-lock.json",
        "threeModule": ROOT / "packages/cadgen-js/node_modules/three/build/three.module.js",
        "threeCore": ROOT / "packages/cadgen-js/node_modules/three/build/three.core.js",
        "harness": Path(__file__).resolve(),
        "worker": WORKER,
    }
    return {name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in paths.items()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", default=str(DEFAULT_SCRATCH.relative_to(ROOT)))
    parser.add_argument("--cases", default=",".join(ALL_CASES))
    parser.add_argument("--native-relative-chord", type=float, default=.0015)
    parser.add_argument("--js-chord", type=float, default=.0015)
    parser.add_argument("--js-loop", type=float, default=.0005)
    parser.add_argument("--angular", type=float, default=.35)
    parser.add_argument("--target-relative-error", type=float, default=.0015,
                        help="common absolute-error target divided by exact native diagonal")
    parser.add_argument("--target-angular-error", type=float, default=.35)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=60.)
    parser.add_argument("--serial-window", action="store_true",
                        help="attest that this run had an externally reserved serial window")
    parser.add_argument("--self-test", action="store_true", help="test the independent numerical distance oracle without source/kernel/browser work")
    args = parser.parse_args(argv)
    oracle_tests = _oracle_self_test()
    if args.self_test:
        print(json.dumps(oracle_tests, sort_keys=True))
        return 0
    cases = tuple(item.strip() for item in args.cases.split(",") if item.strip())
    if not cases or any(item not in FACTORIES for item in cases):
        parser.error(f"--cases must select from {','.join(ALL_CASES)}")
    for value in (args.native_relative_chord, args.js_chord, args.js_loop, args.angular,
                  args.target_relative_error, args.target_angular_error):
        if not math.isfinite(value) or value <= 0:
            parser.error("mesh tolerances must be positive finite values")
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 60:
        parser.error("--timeout must be positive and at most 60 seconds")
    if not 1 <= args.iterations <= 9:
        parser.error("--iterations must be within 1..9")

    scratch = _safe_scratch(args.scratch)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    folder = scratch / stamp
    folder.mkdir(parents=True)
    sources_before = _source_fingerprints()
    import_started = time.monotonic()
    import OCP
    import numpy
    from cadgen._document import meshing as _candidate_meshing  # noqa: F401
    from cadgen._internal import surface_extract as _comparison_surface  # noqa: F401
    python_cad_import_ms = (time.monotonic() - import_started) * 1000
    worker = NodeWorker(args.timeout)
    try:
        rows = [run_case(name, folder, worker, args) for name in cases]
    finally:
        worker.close()
    sources_after = _source_fingerprints()
    if sources_after != sources_before:
        raise RuntimeError("mesh comparison runtime source changed during the run")
    report = {
        "schema": 2,
        "kind": "cadgen-document-mesh-comparison",
        "numericalOracleSelfTest": oracle_tests,
        "status": "passed" if all(row["qualityQualifiedPair"] for row in rows) else "unsupported-quality-cases",
        "createdUtc": datetime.now(timezone.utc).isoformat(),
        "timingEvidence": ("reserved-serial-window" if args.serial_window
                           else "diagnostic-concurrent-functional-only"),
        "boundaries": {
            "pythonCadModuleImportMs": python_cad_import_ms,
            "nodeColdProcessAndModuleSetupMs": worker.setup_ms,
            "warmStagesArePerRequest": True,
            "pythonInterpreterLaunchExcluded": True,
            "nodeRequestStagesExcludeColdSetup": True,
            "nativeProduction": "private native copy + tessellate + packed CGMESH extraction/encoding",
            "javascriptProduction": "private native copy + SURF extraction/encoding + JS decode + tessellate + packed TESS encoding",
            "bothExclude": ["fixture construction", "copy-history correspondence proof", "artifact IO", "IPC", "quality oracle"],
            "parameterSelection": "first passing fixed refinement rung, before timed samples",
            "oneExplicitPrimerPerQualifiedCase": True,
            "alternatingProducerOrder": True,
        },
        "runtime": {"python": sys.version, "ocp": OCP.__version__, "numpy": numpy.__version__,
                    "node": worker.runtime,
                    "gitHead": subprocess.run(
                        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                        capture_output=True, text=True).stdout.strip(),
                    "sourceFingerprints": sources_before,
                    "sourceFingerprintsStable": True},
        "parameters": {
            "nativeRelativeChord": args.native_relative_chord,
            "jsChord": args.js_chord,
            "jsLoop": args.js_loop,
            "angular": args.angular,
            "commonRelativeError": args.target_relative_error,
            "commonAngularError": args.target_angular_error,
            "refinementRungFactors": RUNG_FACTORS,
            "maximumTrimmedFaceTrianglesSampledPerFace": MAX_FACE_SAMPLES,
            "samplesPerSelectedTriangle": 4,
            "analyticSamplesPerTriangle": 4,
            "independentTrimmedUvGridSide": FACE_GRID,
            "independentUniformParameterSamplesPerEdge": EDGE_SAMPLES,
            "maximumTrianglesPerPacket": MAX_TRIANGLES,
            "measuredRepetitions": args.iterations,
            "fixtureTimeoutSeconds": args.timeout,
        },
        "limitations": [
            "Sampled two-way surface/edge distances are evidence, not a global "
            "Hausdorff bound.",
            "Axis support extents are silhouette evidence, not full hidden-line or "
            "occluding-contour comparison.",
            "Equal tolerance values and triangle counts do not establish equal mesh quality.",
            "The closed-form numerical oracle covers only the four analytic surface types in this bounded corpus.",
            "Coordinate welding uses exactDiagonal * 2^-20; this is numerical closure evidence, not native topology identity.",
            "Three fixed parameter rungs do not establish that a failing producer can never meet a quality target.",
            "Speed ratios exist only for fixtures where both producers and every measured sample pass the same target.",
            "Diagnostic timings are not performance claims unless timingEvidence records "
            "a reserved serial window.",
            "Python interpreter launch and artifact write costs are outside the common "
            "warm meshing boundary.",
        ],
        "cases": rows,
    }
    report_path = folder / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(str(report_path.relative_to(ROOT)))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
