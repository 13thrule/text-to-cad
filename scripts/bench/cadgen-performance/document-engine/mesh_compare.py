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
from dataclasses import dataclass
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
MAX_FACE_SAMPLES = 24


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


def _mesh_quality(mesh: Mesh, exact: dict[str, Any]) -> dict[str, Any]:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopoDS import TopoDS

    face_map, edge_map = exact["faceMap"], exact["edgeMap"]
    face_ords = {row[0] for row in mesh.faces}
    expected_faces = set(range(1, face_map.Extent() + 1))
    face_area_errors = []
    sampled_errors = []
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
                sampled_errors.append(_point_distance(centroid, face))
                sampled += 1
        mesh_area += area
        face_area_errors.append(abs(area - exact_area) / max(exact_area, 1e-12))

    exact_edge_ords = set(range(1, edge_map.Extent() + 1))
    represented_edge_ords = {ordinal for ordinal, _ in mesh.edges}
    edge_errors = []
    for ordinal, points in mesh.edges:
        edge = edge_map.FindKey(ordinal)
        step = max(1, len(points) // 12)
        edge_errors.extend(_point_distance(point, edge) for point in points[::step])
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
        "sampledEdgeErrorMax": max(edge_errors, default=0.),
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
            if key not in {"faceMap", "edgeMap"}}


def _quality_pass(quality: dict[str, Any], exact: dict[str, Any],
                  degenerate_edges: set[int]) -> tuple[bool, list[str]]:
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
    if quality["signedVolume"] <= 0 and exact["volume"] > 0:
        failures.append("closed solid has nonpositive signed mesh volume")
    if quality["volumeRelativeError"] > .01:
        failures.append("mesh volume differs by more than 1%")
    if quality["totalAreaRelativeError"] > .02:
        failures.append("mesh area differs by more than 2%")
    if quality["sampledFaceError"]["max"] > quality["targetAbsoluteChord"] * 2:
        failures.append("sampled face error exceeds twice requested chord target")
    if quality["axisSilhouetteExtentErrorMax"] > quality["targetAbsoluteChord"] * 2:
        failures.append("axis silhouette extent exceeds twice requested chord target")
    return not failures, failures


def run_case(name: str, folder: Path, worker: NodeWorker, args) -> dict[str, Any]:
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS
    from cadgen._document.meshing import MeshOptions, _mesh_private
    from cadgen._document.native import copy_shape
    from cadgen._internal.surface_extract import extract_surface_component

    case_started = time.monotonic()
    started = time.monotonic()
    shape = FACTORIES[name]()
    fixture_ms = (time.monotonic() - started) * 1000
    exact = _exact(shape)
    if not exact["valid"] or exact["solidsCount"] < 1:
        raise RuntimeError(f"{name} fixture is not a valid solid")

    started = time.monotonic()
    native_input = copy_shape(shape)
    native_copy_ms = (time.monotonic() - started) * 1000
    started = time.monotonic()
    native_packet = _mesh_private(
        native_input, MeshOptions(args.native_relative_chord, args.angular, True))
    native_tess_pack_ms = (time.monotonic() - started) * 1000
    native_path = folder / f"{name}.native.cgmesh"
    started = time.monotonic()
    native_path.write_bytes(native_packet)
    native_write_ms = (time.monotonic() - started) * 1000

    started = time.monotonic()
    surface_input = copy_shape(shape)
    surface_copy_ms = (time.monotonic() - started) * 1000
    started = time.monotonic()
    surf = extract_surface_component(surface_input)
    surface_extract_pack_ms = (time.monotonic() - started) * 1000
    surf_path = folder / f"{name}.surf"
    started = time.monotonic()
    surf_path.write_bytes(surf)
    surf_write_ms = (time.monotonic() - started) * 1000
    tess_path = folder / f"{name}.tess"
    node = worker.run(surf_path, tess_path, chord=args.js_chord,
                      loop=args.js_loop, angular=args.angular)

    native_mesh = _native_mesh(native_packet)
    js_mesh = _js_mesh(tess_path, args.js_chord, node["scale"])
    native_quality = _mesh_quality(native_mesh, exact)
    js_quality = _mesh_quality(js_mesh, exact)
    degenerate_edges = {ordinal for ordinal in range(1, exact["edgeMap"].Extent() + 1)
                        if BRep_Tool.Degenerated_s(
                            TopoDS.Edge_s(exact["edgeMap"].FindKey(ordinal)))}
    native_pass, native_failures = _quality_pass(native_quality, exact, degenerate_edges)
    js_pass, js_failures = _quality_pass(js_quality, exact, degenerate_edges)
    omitted = node["omittedEdges"]
    if ({item["ord"] for item in omitted} != degenerate_edges
            or any(item["hasCurve"] for item in omitted)):
        js_pass = False
        js_failures.append("JS omitted edges are not exactly explicit degenerates")
    elapsed = time.monotonic() - case_started
    if elapsed > args.timeout:
        raise TimeoutError(f"{name} exceeded the bounded {args.timeout:g}s fixture budget")
    ratio = (js_quality["sampledFaceError"]["max"]
             / max(native_quality["sampledFaceError"]["max"], 1e-15))
    return {
        "case": name,
        "status": "passed" if native_pass and js_pass else "failed",
        "elapsedDiagnosticMs": elapsed * 1000,
        "exact": _strip_exact(exact),
        "geometryInput": {
            "sameFactoryInstance": True,
            "pipelineInputsAreIndependentNativeCopies": True,
            "units": "millimetres",
            "nativeShapeSha256": _native_shape_digest(shape),
            "surfacePayloadSha256": hashlib.sha256(surf).hexdigest(),
        },
        "native": {
            "stagesMs": {"copy": native_copy_ms,
                         "tessellateAndPack": native_tess_pack_ms,
                         "artifactWrite": native_write_ms},
            "quality": native_quality,
            "failures": native_failures,
        },
        "javascript": {
            "stagesMs": {"copy": surface_copy_ms,
                         "surfaceExtractAndPack": surface_extract_pack_ms,
                         "surfArtifactWrite": surf_write_ms,
                         **node["stagesMs"]},
            "coverageFromSource": {key: node[key] for key in (
                "sourceFaceOrds", "meshFaceOrds", "sourceEdgeOrds",
                "meshEdgeOrds", "omittedEdges")},
            "quality": js_quality,
            "failures": js_failures,
        },
        "qualityComparison": {
            "sampledFaceMaxErrorRatioJsToNative": ratio,
            "nativeSampledMaxOverChordTarget": (
                native_quality["sampledFaceError"]["max"]
                / native_quality["targetAbsoluteChord"]),
            "jsSampledMaxOverChordTarget": (
                js_quality["sampledFaceError"]["max"]
                / js_quality["targetAbsoluteChord"]),
            "bothSampledMaxWithinChordTarget": (
                native_quality["sampledFaceError"]["max"]
                <= native_quality["targetAbsoluteChord"]
                and js_quality["sampledFaceError"]["max"]
                <= js_quality["targetAbsoluteChord"]),
            "targetsAreEqualNumericRelativeChord": (
                args.native_relative_chord == args.js_chord),
            "triangleCountsAreEvidenceOnly": True,
        },
        "fixtureBuildDiagnosticMs": fixture_ms,
        "artifacts": {
            "native": str(native_path.relative_to(ROOT)),
            "surf": str(surf_path.relative_to(ROOT)),
            "tess": str(tess_path.relative_to(ROOT)),
        },
    }


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
    parser.add_argument("--timeout", type=float, default=60.)
    parser.add_argument("--serial-window", action="store_true",
                        help="attest that this run had an externally reserved serial window")
    args = parser.parse_args(argv)
    cases = tuple(item.strip() for item in args.cases.split(",") if item.strip())
    if not cases or any(item not in FACTORIES for item in cases):
        parser.error(f"--cases must select from {','.join(ALL_CASES)}")
    for value in (args.native_relative_chord, args.js_chord, args.js_loop, args.angular):
        if not math.isfinite(value) or value <= 0:
            parser.error("mesh tolerances must be positive finite values")
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 60:
        parser.error("--timeout must be positive and at most 60 seconds")

    scratch = _safe_scratch(args.scratch)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    folder = scratch / stamp
    folder.mkdir(parents=True)
    sources_before = _source_fingerprints()
    import_started = time.monotonic()
    import OCP
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
        "schema": 1,
        "kind": "cadgen-document-mesh-comparison",
        "status": "passed" if all(row["status"] == "passed" for row in rows) else "failed",
        "createdUtc": datetime.now(timezone.utc).isoformat(),
        "timingEvidence": ("reserved-serial-window" if args.serial_window
                           else "diagnostic-concurrent-functional-only"),
        "boundaries": {
            "pythonCadModuleImportMs": python_cad_import_ms,
            "nodeColdProcessAndModuleSetupMs": worker.setup_ms,
            "warmStagesArePerRequest": True,
            "pythonInterpreterLaunchExcluded": True,
            "nodeRequestStagesExcludeColdSetup": True,
        },
        "runtime": {"python": sys.version, "ocp": OCP.__version__,
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
            "maximumFaceCentroidSamplesPerFace": MAX_FACE_SAMPLES,
            "fixtureTimeoutSeconds": args.timeout,
        },
        "limitations": [
            "Sampled centroid-to-trimmed-face distance is evidence, not a global "
            "Hausdorff bound.",
            "Axis support extents are silhouette evidence, not full hidden-line or "
            "occluding-contour comparison.",
            "Equal tolerance values and triangle counts do not establish equal mesh quality.",
            "Diagnostic timings are not performance claims unless timingEvidence records "
            "a reserved serial window.",
            "Python interpreter launch and artifact write costs are outside the common "
            "warm meshing boundary.",
        ],
        "cases": rows,
    }
    report_path = folder / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(str(report_path.relative_to(ROOT)))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
