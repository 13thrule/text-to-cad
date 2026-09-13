"""Bounded plate/hole/fillet fixture for the retained-document benchmark."""

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
        80.0,
        50.0,
        6.0,
        align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
    )
    body = bd.fillet(body.edges().filter_by(bd.Axis.Z), radius=4.0)
    for x in (-28.0, 28.0):
        for y in (-13.0, 13.0):
            tool = bd.Pos(x, y, -1.0) * bd.Cylinder(
                HOLE_RADIUS,
                8.0,
                align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
            )
            body = body - tool
    body.label = "drilled_plate"
    return body


@step(out="plate.step")
def plate():
    result = bd.Pos(0.0, 0.0, PLACEMENT_Z) * make_plate()
    volume = float(result.volume)  # A geometry-dependent native query is in the corpus.
    if not result.is_valid or volume <= 0.0:
        raise AssertionError("plate fixture produced invalid geometry")
    trace = os.environ.get("CADGEN_DOCUMENT_BENCH_SOURCE_TRACE")
    if trace:
        with Path(trace).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"model": "plate", "volume": volume}) + "\n")
    return bd.Compound(children=[result], label="plate_benchmark")


if __name__ == "__main__":
    plate()
