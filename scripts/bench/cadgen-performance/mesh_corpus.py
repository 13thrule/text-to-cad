#!/usr/bin/env python3
"""Build a small private BREP/SURF view for meshing quality comparisons.

This deliberately bypasses model/store publication: both candidates receive
the same freshly serialized exact shape, and every artifact stays in models/.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from common import model_path, sha256, write_json


def shapes():
    import build123d as bd

    yield "sphere_poles", bd.Solid.make_sphere(10)
    yield "cone_apex", bd.Solid.make_cone(8, 0, 12)
    yield "torus_seams", bd.Solid.make_torus(10, 2)
    plate = bd.Solid.make_cylinder(52.5, 4)
    for x, y in [(-21, -21 * 3 ** 0.5), (42, 0), (-21, 21 * 3 ** 0.5)]:
        plate = plate.cut(bd.Solid.make_cylinder(3.2, 6).moved(bd.Location((x, y, -1))))
    yield "perforated_plate", plate
    with bd.BuildPart() as loft:
        with bd.BuildSketch(bd.Plane.XY):
            bd.Rectangle(12, 8)
        with bd.BuildSketch(bd.Plane.XY.offset(12)):
            bd.Circle(3)
        bd.loft(ruled=False)
    yield "bspline_loft", loft.part
    yield "trimmed_bspline", loft.part.cut(bd.Solid.make_cylinder(1.25, 20).moved(bd.Location((3, 0, -1))))
    with bd.BuildPart() as revolved:
        with bd.BuildSketch(bd.Plane.XZ):
            with bd.BuildLine():
                bd.Spline((8, -2), (10.5, 0), (8, 2))
                bd.Line((8, 2), (8, -2))
            bd.make_face()
        bd.revolve(axis=bd.Axis.Z)
    yield "spline_revolution_seam", revolved.part


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", required=True, type=Path)
    args = parser.parse_args()
    view = model_path(args.view)
    if view.exists():
        parser.error("--view must not already exist")
    from cadgen._internal.component_package import _shape_brep_bytes
    from cadgen._internal.surface_extract import extract_surface_component, read_surf

    components, occurrences = {}, []
    (view / "components").mkdir(parents=True)
    for name, solid in shapes():
        brep = _shape_brep_bytes(solid.wrapped)
        surf = extract_surface_component(solid.wrapped)
        index, _ = read_surf(surf)
        cid = sha256(brep)[:16]
        (view / "components" / f"{cid}.brep").write_bytes(brep)
        (view / "components" / f"{cid}.surf").write_bytes(surf)
        components[cid] = {"brepSha256": sha256(brep), "surfSha256": sha256(surf),
                           "surfaceTypes": sorted({face["surface"]["kind"] for face in index["faces"]})}
        occurrences.append({"id": name, "name": name, "component": cid})
    write_json(view / "assembly.json", {"components": components, "occurrences": occurrences})
    print(view)


if __name__ == "__main__":
    main()
