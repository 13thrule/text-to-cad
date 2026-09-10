#!/usr/bin/env python3
"""Measure retained-document edits separately from STEP persistence in FreeCAD.

The controller needs standard Python and an installed FreeCADCmd. The worker
uses FreeCAD's own Python/kernel, isolated settings, and a private document.
The carrier replacement matches warm_build.py's planetary fixture. This is a
headless architecture comparison, not a GUI latency or mesh-quality benchmark.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time


def worker(plan_path: Path):
    import FreeCAD as App
    import Import
    import MeshPart
    import Part
    import platform
    import resource

    plan = json.loads(plan_path.read_text())
    source = Path(plan["step"])
    original = source.read_bytes()
    destination = Path(plan["directory"])
    rows = []

    def timed(fn):
        start = time.perf_counter()
        result = fn()
        return result, (time.perf_counter() - start) * 1000

    def carrier(diameter):
        plate = Part.makeCylinder(diameter / 2, 4, App.Vector(0, 0, -5))
        for index in range(3):
            angle = math.tau * index / 3
            hole = Part.makeCylinder(3.2, 4.2, App.Vector(42 * math.cos(angle), 42 * math.sin(angle), -5.1))
            plate = plate.cut(hole)
        return plate

    doc = App.newDocument("CadgenFreeCADBenchmark")
    try:
        _, import_ms = timed(lambda: Import.insert(str(source), doc.Name))
        parts = [obj for obj in doc.Objects if obj.TypeId == "Part::Feature"]
        targets = [obj for obj in parts if obj.Label == "carrier_plate"]
        if len(parts) != 9 or len(targets) != 1:
            raise ValueError("Expected the nine-part planetary fixture with one carrier_plate")
        target = targets[0]
        rest = target.Shape.copy()
        roots = [obj for obj in doc.RootObjects if obj.TypeId == "App::Part"] or parts
        for kind in ("geometry", "placement"):
            for sample in range(plan["iterations"] + 1):
                target.Shape = rest.copy()
                target.Placement = App.Placement()
                doc.recompute()
                unchanged = [(obj, obj.Shape) for obj in parts if obj is not target]

                def edit():
                    if kind == "geometry":
                        target.Shape = carrier(106)
                    else:
                        target.Placement = App.Placement(App.Vector(0, 0, -0.5), App.Rotation())
                    doc.recompute()

                _, edit_ms = timed(edit)
                if not all(obj.Shape.isSame(shape) for obj, shape in unchanged):
                    raise RuntimeError("An unchanged imported part lost its retained topology")
                # This explicitly extracts a new native display mesh. The GUI
                # can retain triangles on placement edits; this is a separate
                # cost, not added to the in-memory placement edit above.
                mesh, mesh_ms = timed(lambda: MeshPart.meshFromShape(
                    Shape=target.Shape, LinearDeflection=0.1,
                    AngularDeflection=0.3, Relative=False,
                ))
                output = destination / f"{kind}-{sample}.step"
                _, export_ms = timed(lambda: Import.export(roots, str(output)))
                retained_after_export = sum(obj.Shape.isSame(shape) for obj, shape in unchanged)
                readback, readback_ms = timed(lambda: Part.read(str(output)))
                expected_volume = sum(obj.Shape.Volume for obj in parts)
                if not math.isclose(readback.Volume, expected_volume, rel_tol=1e-8, abs_tol=1e-6):
                    raise RuntimeError("Saved STEP volume differs from the edited document")
                rows.append({
                    "kind": kind, "measured": sample > 0, "sample": sample,
                    "editAndRecomputeMs": edit_ms, "changedPartMeshMs": mesh_ms,
                    "wholeAssemblyExportMs": export_ms, "wholeAssemblyReadbackMs": readback_ms,
                    "changedPartFacets": mesh.CountFacets, "outputBytes": output.stat().st_size,
                    "savedVolume": readback.Volume, "unchangedPartsRetained": len(unchanged),
                    "unchangedPartsRetainedAfterExport": retained_after_export,
                })
                output.unlink()
        result = {
            "metadata": {"freecad": App.Version(), "occt": Part.OCC_VERSION,
                         "python": sys.version, "platform": platform.platform()},
            "inputSha256": hashlib.sha256(original).hexdigest(), "inputBytes": len(original),
            "inputUnchanged": source.read_bytes() == original, "importMs": import_ms,
            "processPeakRssBytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),
            "timingBoundary": "kernel imported; retained FreeCAD document; geometry edit regenerates only carrier; placement edit retains all part topology; mesh, export and readback timed separately; no GUI",
            "meshOptions": {"LinearDeflectionMm": 0.1, "AngularDeflectionRadians": 0.3, "Relative": False},
            "rows": rows,
            "summary": {
                kind: {
                    key: statistics.median(row[key] for row in rows if row["kind"] == kind and row["measured"])
                    for key in ("editAndRecomputeMs", "changedPartMeshMs", "wholeAssemblyExportMs", "wholeAssemblyReadbackMs")
                } for kind in ("geometry", "placement")
            },
        }
        Path(plan["workerReport"]).write_text(json.dumps(result, indent=2) + "\n")
    finally:
        App.closeDocument(doc.Name)


def main():
    import argparse
    import subprocess
    import tempfile
    from common import metadata, model_path, write_json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freecad", type=Path, required=True, help="FreeCADCmd executable")
    parser.add_argument("--step", required=True, help="Prepared nine-part planetary.step")
    parser.add_argument("--directory", required=True, help="Private scratch directory under models/")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    source, directory = model_path(args.step), model_path(args.directory)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="freecad-", dir=directory) as temporary:
        scratch = Path(temporary)
        plan = {"step": str(source), "directory": str(scratch), "iterations": args.iterations,
                "workerReport": str(scratch / "result.json")}
        plan_path = scratch / "plan.json"
        write_json(plan_path, plan)
        env = dict(os.environ, CADGEN_FREECAD_BENCH_PLAN=str(plan_path))
        # Use FreeCAD's own interpreter/dependencies, not the controller's CAD
        # environment, and do not read or rewrite the user's FreeCAD settings.
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        run = subprocess.run([str(args.freecad.resolve()), "-u", str(scratch / "user.cfg"),
                              "-s", str(scratch / "system.cfg"), str(Path(__file__).resolve())],
                             env=env, capture_output=True, text=True, timeout=120)
        if run.returncode or not Path(plan["workerReport"]).is_file():
            raise RuntimeError(f"FreeCAD benchmark failed ({run.returncode}):\n{run.stdout}\n{run.stderr}")
        result = json.loads(Path(plan["workerReport"]).read_text())
        result["controllerMetadata"] = metadata()
        result["freecadExecutable"] = str(args.freecad.resolve())
        result["iterations"] = args.iterations
        write_json(args.report, result)
        print(json.dumps(result["summary"], indent=2))


if os.environ.get("CADGEN_FREECAD_BENCH_PLAN"):
    worker(Path(os.environ["CADGEN_FREECAD_BENCH_PLAN"]))
elif __name__ == "__main__":
    main()
