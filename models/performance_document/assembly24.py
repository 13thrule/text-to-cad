"""Twenty-four occurrences of one plate prototype for document-edit timing."""

from __future__ import annotations

import json
import os
from pathlib import Path

from cadgen import build123d as bd
from cadgen import step


HOLE_RADIUS = 3.0  # BENCH_GEOMETRY
PLACEMENT_Z = 0.0  # BENCH_PLACEMENT


def make_plate():
    body = bd.Box(
        32.0,
        22.0,
        4.0,
        align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
    )
    body = bd.fillet(body.edges().filter_by(bd.Axis.Z), radius=2.5)
    for x in (-10.0, 10.0):
        for y in (-6.0, 6.0):
            tool = bd.Pos(x, y, -1.0) * bd.Cylinder(
                HOLE_RADIUS,
                6.0,
                align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
            )
            body = body - tool
    return body


@step(out="assembly24.step")
def assembly24():
    prototype = make_plate()
    prototype_volume = float(prototype.volume)  # Native query; no benchmark utility API.
    if not prototype.is_valid or prototype_volume <= 0.0:
        raise AssertionError("assembly prototype produced invalid geometry")
    children = []
    for index in range(24):
        row, column = divmod(index, 6)
        z = PLACEMENT_Z if index == 0 else 0.0
        child = prototype.moved(bd.Location((column * 42.0, row * 32.0, z)))
        child.label = f"plate_{index + 1:02d}"
        children.append(child)
    result = bd.Compound(children=children, label="plate_assembly_24")
    trace = os.environ.get("CADGEN_DOCUMENT_BENCH_SOURCE_TRACE")
    if trace:
        with Path(trace).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "model": "assembly24",
                "prototypeVolume": prototype_volume,
                "occurrences": len(children),
            }) + "\n")
    return result


if __name__ == "__main__":
    assembly24()
