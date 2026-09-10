"""Untimed geometry audits shared by the private meshing experiments."""
from __future__ import annotations

from array import array
import json
from pathlib import Path
import struct
import sys


def decode_candidate(path: Path) -> dict:
    """Read the candidate TESS v3 arrays for audit only, not runtime loading."""
    data = path.read_bytes()
    magic, version, header_bytes = struct.unpack_from("<III", data)
    if (magic, version) != (0x53534554, 3):
        raise ValueError("expected the experiment's TESS v3 candidate")
    header = json.loads(data[12:12 + header_bytes])
    offset = 12 + header_bytes
    result = {"faceRanges": header["faceRanges"]}
    for name, count_name, kind in [
        ("positions", "positionCount", "f"), ("normals", "normalCount", "f"),
        ("faceOrds", "faceOrdCount", "f"), ("indices", "indexCount", "I"),
    ]:
        count = header[count_name]
        values = array(kind)
        values.frombytes(data[offset:offset + count * 4])
        if sys.byteorder != "little":
            values.byteswap()
        result[name] = values
        offset += count * 4
    return result


def sample_surface_deviation(mesh: dict, faces) -> dict:
    """Project all vertices, triangle-edge midpoints and centroids onto OCCT.

    The result bounds these samples, not the continuous facets or screen-space
    appearance. Projection is to each triangle's exact underlying face surface;
    trim correctness is separately checked by area, winding and edge audits.
    """
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt

    positions, indices = mesh["positions"], mesh["indices"]
    rows = []
    for face_range in mesh["faceRanges"]:
        ordinal = face_range["ord"]
        face = TopoDS.Face_s(faces.FindKey(ordinal))
        projector = GeomAPI_ProjectPointOnSurf()
        surface = BRep_Tool.Surface_s(face)
        u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
        projector.Init(surface, u0, u1, v0, v1, 1e-9)
        corners = [surface.Value(u, v) for u in (u0, u1) for v in (v0, v1)]
        distances = {}
        fallbacks = 0

        def distance(point, vertex=False):
            nonlocal fallbacks
            if point in distances:
                return distances[point]
            p = gp_Pnt(*point)
            projector.Perform(p)
            if projector.NbPoints():
                # At a pole the nearest point is a singular boundary point,
                # not an interior stationary point found by the projector.
                result = min(projector.LowerDistance(), *(p.Distance(corner) for corner in corners))
            else:
                result = float("inf")
            # A transported vertex can lie one ULP outside a trimmed UV bound.
            # Surface extrema may then miss the boundary and return a distant
            # stationary point (notably a cone's base circle). Verify such
            # vertex results against the exact bounded face.
            if not projector.NbPoints() or (vertex and result > max(1, *(abs(x) for x in point)) * 2 ** -20):
                exact = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(p).Vertex(), face)
                if not exact.IsDone():
                    raise RuntimeError(f"exact projection failed for face {ordinal}: {point}")
                result = min(result, exact.Value())
                fallbacks += 1
            distances[point] = result
            return result

        vertex_max = facet_max = 0.0
        first = face_range["indexStart"]
        last = first + face_range["indexCount"]
        for index in range(first, last, 3):
            points = [tuple(positions[indices[index + j] * 3 + d] for d in range(3)) for j in range(3)]
            vertex_max = max(vertex_max, *(distance(point, vertex=True) for point in points))
            for a, b in ((0, 1), (1, 2), (2, 0)):
                facet_max = max(facet_max, distance(tuple((points[a][d] + points[b][d]) / 2 for d in range(3))))
            facet_max = max(facet_max, distance(tuple(sum(point[d] for point in points) / 3 for d in range(3))))
        rows.append({"face": ordinal, "vertexMaxMm": vertex_max, "facetSamplesMaxMm": facet_max,
                     "samples": len(distances), "trimDistanceFallbacks": fallbacks})
    return {"method": "all used vertices, all triangle-edge midpoints and all triangle centroids projected onto each exact OCCT face surface",
            "continuousBound": False, "faces": rows,
            "vertexMaxMm": max((row["vertexMaxMm"] for row in rows), default=0),
            "facetSamplesMaxMm": max((row["facetSamplesMaxMm"] for row in rows), default=0),
            "samples": sum(row["samples"] for row in rows),
            "trimDistanceFallbacks": sum(row["trimDistanceFallbacks"] for row in rows)}
