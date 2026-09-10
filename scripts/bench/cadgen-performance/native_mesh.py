#!/usr/bin/env python3
"""Compare OCCT and current JS tessellation on the same component BREP/SURF.

Evidence only: all candidate mesh bytes stay in a private benchmark directory,
never in cadgen's mesh index. Native meshing owns a fresh BREP reconstruction
for every sample. The controller repeats each algorithm in fresh processes.
"""
from __future__ import annotations

import argparse
from array import array
import gzip
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time

from common import REPO, metadata, model_path, peak_rss_bytes, sha256, source_fingerprint, write_json
from mesh_audit import decode_candidate, sample_surface_deviation


def milliseconds(start):
    return (time.perf_counter() - start) * 1000


def encode(mesh: dict, index: dict) -> bytes:
    """Use the existing TESS v3 transport layout for a fair payload-size audit.

    This does not give native output the canonical mesher's cache identity.
    Native candidates have private filenames and never write index/mesh.
    """
    header = {
        "partColor": index.get("partColor"),
        "edgeClasses": [[edge["ord"], edge.get("class", "none")] for edge in index["edges"]],
        "faceRanges": mesh["faceRanges"], "bounds": mesh["bounds"], "scale": mesh["scale"],
        "positionCount": len(mesh["positions"]), "normalCount": len(mesh["normals"]),
        "faceOrdCount": len(mesh["faceOrds"]), "indexCount": len(mesh["indices"]), "sideOrdCount": len(mesh["sideOrds"]),
        "edges": [{"ord": edge["ord"], "visibilityClass": edge["visibilityClass"], "count": len(edge["polyline"])} for edge in mesh["edges"]],
    }
    raw = json.dumps(header, separators=(",", ":")).encode()
    raw += b" " * (-len(raw) % 4)
    output = bytearray(struct.pack("<III", 0x53534554, 3, len(raw)) + raw)
    for values in [mesh[key] for key in ("positions", "normals", "faceOrds", "indices", "sideOrds")] + [edge["polyline"] for edge in mesh["edges"]]:
        if sys.byteorder != "little":
            values = values[:]
            values.byteswap()
        output.extend(values.tobytes())
    return bytes(output)


def native_worker(plan: Path, report: Path, view: Path, cache: Path, iterations: int, chord_scale: float):
    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS, TopoDS_Shape
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_REVERSED
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.TopLoc import TopLoc_Location
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from cadgen._internal.component_package import _shape_brep_bytes
    from cadgen._internal.surface_extract import read_surf

    rows = []
    cache.mkdir(parents=True, exist_ok=True)
    for reference in json.loads(plan.read_text())["rows"]:
        cid, chord = reference["cid"], reference["chordTolerance"]
        brep_path = view / "components" / f"{cid}.brep"
        source = brep_path.read_bytes()
        if sha256(source) != reference["brepSha256"]:
            raise RuntimeError(f"BREP changed during benchmark: {cid}")
        surf = (view / "components" / f"{cid}.surf").read_bytes()
        index, _ = read_surf(surf)
        if sha256(surf) != reference["surfSha256"]:
            raise RuntimeError("SURF changed during benchmark")
        classes = {edge["ord"]: edge.get("class", "none") for edge in index["edges"]}
        colors = {face["ord"]: face.get("color") for face in index["faces"]}
        hashes, samples, identities = [], [], []
        for iteration in range(iterations):
            start = time.perf_counter()
            payload = brep_path.read_bytes()
            read_ms = milliseconds(start)
            start = time.perf_counter()
            shape = TopoDS_Shape()
            BinTools.Read_s(shape, io.BytesIO(payload))
            reconstruct_ms = milliseconds(start)
            # A private shape only. Remove any stored mesh before timing a
            # cold triangulation; never mutate shared materialization handles.
            BRepTools.Clean_s(shape)
            identity_before = sha256(_shape_brep_bytes(shape))
            faces, edges = TopTools_IndexedMapOfShape(), TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
            TopExp.MapShapes_s(shape, TopAbs_EDGE, edges)
            props = GProp_GProps()
            BRepGProp.VolumeProperties_s(shape, props)
            truth = {"volume": abs(props.Mass()), "faceAreas": {}}
            for ordinal in range(1, faces.Extent() + 1):
                face_props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(TopoDS.Face_s(faces.FindKey(ordinal)), face_props)
                truth["faceAreas"][ordinal] = face_props.Mass()
            identity_before_mesh = sha256(_shape_brep_bytes(shape))
            start = time.perf_counter()
            mesher = BRepMesh_IncrementalMesh(shape, reference["absoluteChordMm"] * chord_scale, False,
                                           reference["options"]["angleTolerance"], False)
            mesh_ms = milliseconds(start)
            if not mesher.IsDone():
                raise RuntimeError(f"OCCT meshing failed: {cid}")
            identity_after_mesh = sha256(_shape_brep_bytes(shape))
            start = time.perf_counter()
            positions, normals, face_ords = array("f"), array("f"), array("f")
            triangles, side_ords = array("I"), array("I")
            ranges, polylines = [], {}
            missing_normals = 0
            collapsed_triangles = 0
            for ordinal in range(1, faces.Extent() + 1):
                face = TopoDS.Face_s(faces.FindKey(ordinal))
                location = TopLoc_Location()
                tri = BRep_Tool.Triangulation_s(face, location)
                if tri is None:
                    raise RuntimeError(f"No triangulation for {cid} face {ordinal}")
                transform = location.Transformation()
                reversed_face = face.Orientation() == TopAbs_REVERSED
                base, first_index = len(positions) // 3, len(triangles)
                surface = BRepAdaptor_Surface(face)
                properties = BRepLProp_SLProps(surface, 1, 1e-9)
                for node in range(1, tri.NbNodes() + 1):
                    point = tri.Node(node).Transformed(transform)
                    positions.extend((point.X(), point.Y(), point.Z()))
                    uv = tri.UVNode(node)
                    properties.SetParameters(uv.X(), uv.Y())
                    if properties.IsNormalDefined():
                        normal = properties.Normal()
                        sign = -1 if reversed_face else 1
                        normals.extend((sign * normal.X(), sign * normal.Y(), sign * normal.Z()))
                    else:
                        missing_normals += 1
                        normals.extend((0, 0, 0))
                    face_ords.append(ordinal)
                boundary = {}
                explorer = TopExp_Explorer(face, TopAbs_EDGE)
                while explorer.More():
                    edge = TopoDS.Edge_s(explorer.Current())
                    edge_ord = edges.FindIndex(edge)
                    polygon = BRep_Tool.PolygonOnTriangulation_s(edge, tri, location)
                    if polygon is not None:
                        nodes = [base + polygon.Node(i) - 1 for i in range(1, polygon.NbNodes() + 1)]
                        for a, b in zip(nodes, nodes[1:]):
                            boundary[tuple(sorted((a, b)))] = edge_ord
                        if edge_ord not in polylines:
                            polyline = array("f")
                            for node in nodes:
                                polyline.extend(positions[node * 3:node * 3 + 3])
                            polylines[edge_ord] = {"ord": edge_ord, "visibilityClass": classes.get(edge_ord, "none"), "polyline": polyline}
                    explorer.Next()
                for triangle in range(1, tri.NbTriangles() + 1):
                    a, b, c = tri.Triangle(triangle).Get()
                    ids = [base + a - 1, base + c - 1, base + b - 1] if reversed_face else [base + a - 1, base + b - 1, base + c - 1]
                    pa, pb, pc = [positions[node * 3:node * 3 + 3] for node in ids]
                    u, v = [pb[d] - pa[d] for d in range(3)], [pc[d] - pa[d] for d in range(3)]
                    area_squared = sum(value * value for value in (u[1] * v[2] - u[2] * v[1],
                        u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]))
                    # OCCT emits repeated pole/apex triangles that collapse
                    # in the shared Float32 transport. This extraction step
                    # is timed and reported, not credited to kernel meshing.
                    if area_squared < reference["scale"] ** 4 * 1e-24:
                        collapsed_triangles += 1
                        continue
                    triangles.extend(ids)
                    # The renderer associates side i with the edge opposite
                    # barycentric vertex i: (b,c), (c,a), (a,b).
                    side_ords.extend(boundary.get(tuple(sorted((ids[(i + 1) % 3], ids[(i + 2) % 3]))), 0) for i in range(3))
                ranges.append({"ord": ordinal, "color": colors.get(ordinal), "indexStart": first_index, "indexCount": len(triangles) - first_index})
            mesh = {"positions": positions, "normals": normals, "faceOrds": face_ords,
                    "indices": triangles, "sideOrds": side_ords, "faceRanges": ranges,
                    "edges": [polylines[key] for key in sorted(polylines)], "scale": reference["scale"],
                    "bounds": {"min": [min(positions[d::3]) for d in range(3)], "max": [max(positions[d::3]) for d in range(3)]}}
            extract_ms = milliseconds(start)
            start = time.perf_counter()
            encoded = encode(mesh, index)
            encode_ms = milliseconds(start)
            identity_after = sha256(_shape_brep_bytes(shape))
            if brep_path.read_bytes() != source:
                raise RuntimeError("Native meshing changed its input file")
            identities.append({"beforeProperties": identity_before, "beforeMesh": identity_before_mesh,
                               "afterMesh": identity_after_mesh, "afterExtraction": identity_after})
            hashes.append(sha256(encoded))
            samples.append({"readMs": read_ms, "reconstructMs": reconstruct_ms, "meshMs": mesh_ms,
                            "extractMs": extract_ms, "encodeMs": encode_ms})
        cache_path = cache / f"native-experiment-{cid}-{chord}.tess"
        cache_path.write_bytes(encoded)
        native_deviation = sample_surface_deviation(mesh, faces)
        js_deviation = sample_surface_deviation(decode_candidate(Path(reference["cachePath"])), faces)
        rows.append({"cid": cid, "name": reference["name"], "chordTolerance": chord,
                     "absoluteChordMm": reference["absoluteChordMm"] * chord_scale,
                     "referenceChordMm": reference["absoluteChordMm"], "chordScale": chord_scale,
                     "angleTolerance": reference["options"]["angleTolerance"],
                     "relative": False, "parallel": False, "vertices": len(positions) // 3,
                     "triangles": len(triangles) // 3, "encodedBytes": len(encoded), "gzipBytes": len(gzip.compress(encoded, mtime=0)),
                     "meshHash": hashes[0], "repeatDeterministic": len(set(hashes)) == 1,
                     "inputBrepUnchanged": True, "privateBrepIdentityUnchanged": all(item["beforeMesh"] == item["afterMesh"] for item in identities),
                     "privateBrepIdentities": identities, "inputSha256": sha256(source), "surfSha256": sha256(surf),
                     "faceCount": faces.Extent(), "edgeCount": edges.Extent(), "edgePolylines": len(polylines),
                     "undefinedNormalNodes": missing_normals, "droppedCollapsedTriangles": collapsed_triangles,
                     "truth": truth, "samples": samples, "cachePath": str(cache_path),
                     "sampledDeviation": native_deviation, "jsSampledDeviation": js_deviation})
    write_json(report, {"timingBoundary": "fresh private BREP per sample; OCCT meshing excludes reconstruction, Python array/normal extraction and codec",
                        "processPeakRssBytes": peak_rss_bytes(), "rows": rows})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--chords", default="0.003,0.0015")
    parser.add_argument("--native-chord-scale", type=float, default=1.0,
                        help="multiply OCCT's physical chord input while keeping the JS reference settings")
    parser.add_argument("--native-worker", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    view = model_path(args.view)
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    if not 0 < args.native_chord_scale <= 1:
        parser.error("--native-chord-scale must be positive and at most 1")
    if args.native_worker:
        native_worker(args.native_worker, args.report, view, model_path(args.cache_dir), args.iterations, args.native_chord_scale)
        return
    script = Path(__file__).resolve()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    result = {"metadata": metadata(), "view": str(view), "iterations": args.iterations,
              "qualityScope": "same BREP/SURF and angular input; native chord scale is explicit; all vertices, triangle-edge midpoints and centroids are projected onto exact OCCT face surfaces outside timed work; sampled deviation is not a continuous bound or visual-quality proof",
              "nativeChordScale": args.native_chord_scale,
              "processes": []}
    with tempfile.TemporaryDirectory(prefix="native-meshing-", dir=view.parent) as scratch:
        for process in range(2):
            cache = Path(scratch) / str(process)
            cache.mkdir()
            js_report = args.report.with_name(args.report.stem + f"-js-{process}.json")
            native_report = args.report.with_name(args.report.stem + f"-occt-{process}.json")
            decode_report = args.report.with_name(args.report.stem + f"-occt-decode-{process}.json")
            subprocess.run(["node", str(script.with_name("js_mesh.mjs")), "--view", str(view), "--report", str(js_report),
                            "--cache-dir", str(cache), "--iterations", str(args.iterations), "--chords", args.chords], check=True, cwd=REPO)
            subprocess.run([sys.executable, str(script), "--view", str(view), "--report", str(native_report), "--native-worker", str(js_report),
                            "--cache-dir", str(cache), "--iterations", str(args.iterations),
                            "--native-chord-scale", str(args.native_chord_scale)], check=True, cwd=REPO)
            subprocess.run(["node", str(script.with_name("js_mesh.mjs")), "--decode-native", str(native_report), "--report", str(decode_report),
                            "--cache-dir", str(cache), "--iterations", str(args.iterations)], check=True, cwd=REPO)
            js, native, decoded = [json.loads(path.read_text()) for path in (js_report, native_report, decode_report)]
            rows = []
            for current, candidate, audit in zip(js["rows"], native["rows"], decoded["rows"], strict=True):
                candidate["quality"] = audit["quality"]
                candidate["cachedSamples"] = audit["samples"]
                current["sampledDeviation"] = candidate.pop("jsSampledDeviation")
                for mesh in (current, candidate):
                    truth = candidate["truth"]
                    mesh["quality"]["volumeRelativeError"] = abs(abs(mesh["quality"]["signedVolume"]) - truth["volume"]) / max(truth["volume"], 1e-12)
                    errors = [abs(area - mesh["quality"]["faceAreas"].get(ordinal, 0)) / max(area, 1e-12) for ordinal, area in truth["faceAreas"].items()]
                    mesh["quality"]["maxFaceAreaRelativeError"] = max(errors, default=0)
                rows.append({"cid": current["cid"], "chordTolerance": current["chordTolerance"], "js": current, "native": candidate})
            result["processes"].append({"rows": rows, "jsPeakRssBytes": js["processPeakRssBytes"], "nativePeakRssBytes": native["processPeakRssBytes"]})
        first, second = result["processes"]
        result["freshProcessDeterminism"] = {name: all(a[name]["meshHash"] == b[name]["meshHash"] for a, b in zip(first["rows"], second["rows"], strict=True)) for name in ("js", "native")}
    result["runtimeUnchangedDuringStudy"] = source_fingerprint() == result["metadata"]["sourceFingerprint"]
    write_json(args.report, result)
    print(json.dumps({"report": str(args.report), "freshProcessDeterminism": result["freshProcessDeterminism"],
                      "runtimeUnchangedDuringStudy": result["runtimeUnchangedDuringStudy"]}), flush=True)


if __name__ == "__main__":
    main()
