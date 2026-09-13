#!/usr/bin/env python3
"""Equivalent retained-document reference using FreeCAD's own interpreter.

This reference keeps in-memory document edit, native query, mesh, STEP export,
and cold STEP readback as separate stages. It is not part of the cadgen
source-command timing boundary and it does not exercise a GUI.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time


REPO = Path(__file__).resolve().parents[4]
MODELS = REPO / "models"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def append_jsonl(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def under_models(value: str) -> Path:
    path = Path(value).resolve()
    if not path.is_relative_to(MODELS.resolve()):
        raise ValueError(f"scratch must be below {MODELS}: {path}")
    return path


def worker(plan_path: Path) -> None:
    import FreeCAD as App
    import Import
    import MeshPart
    import Part
    import resource

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    model = plan["model"]
    count = 1 if model == "plate" else 24
    output_dir = Path(plan["outputDirectory"])
    journal = Path(plan["journal"])

    def timed(function):
        started = time.perf_counter()
        value = function()
        return value, (time.perf_counter() - started) * 1000.0

    def make_plate(radius: float):
        if model == "plate":
            width, depth, height, corner = 80.0, 50.0, 6.0, 4.0
            xs, ys = (-28.0, 28.0), (-13.0, 13.0)
        else:
            width, depth, height, corner = 32.0, 22.0, 4.0, 2.5
            xs, ys = (-10.0, 10.0), (-6.0, 6.0)
        shape = Part.makeBox(width, depth, height, App.Vector(-width / 2, -depth / 2, 0))
        vertical = [edge for edge in shape.Edges if edge.BoundBox.ZLength > height - 1e-7]
        shape = shape.makeFillet(corner, vertical)
        for x in xs:
            for y in ys:
                shape = shape.cut(Part.makeCylinder(radius, height + 2, App.Vector(x, y, -1)))
        if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1:
            raise RuntimeError("FreeCAD reference produced invalid plate geometry")
        return shape

    def base_placement(index: int, z: float = 0.0):
        if model == "plate":
            return App.Placement(App.Vector(0, 0, z), App.Rotation())
        row, column = divmod(index, 6)
        return App.Placement(App.Vector(column * 42.0, row * 32.0, z), App.Rotation())

    def describe_objects():
        descriptions = []
        for obj in objects:
            placed = obj.Shape.copy()
            placed.Placement = obj.Placement
            bounds = placed.BoundBox
            descriptions.append({
                "label": obj.Label, "volume": float(placed.Volume),
                "area": float(placed.Area),
                "bounds": [[float(bounds.XMin), float(bounds.YMin), float(bounds.ZMin)],
                           [float(bounds.XMax), float(bounds.YMax), float(bounds.ZMax)]],
                "counts": {"solids": len(placed.Solids), "faces": len(placed.Faces),
                           "edges": len(placed.Edges), "vertices": len(placed.Vertexes)},
                "valid": bool(placed.isValid()),
            })
        return descriptions

    doc = App.newDocument("CadgenDocumentReference")
    try:
        prototype = make_plate(3.0)
        objects = []
        for index in range(count):
            obj = doc.addObject("Part::Feature", f"Plate{index + 1:02d}")
            obj.Label = "drilled_plate" if count == 1 else f"plate_{index + 1:02d}"
            obj.Shape = prototype
            obj.Placement = base_placement(index)
            objects.append(obj)
        doc.recompute()
        rows = []
        for scenario in ("unchanged", "local_geometry", "placement"):
            for sample in range(plan["samples"] + 1):
                for index, obj in enumerate(objects):
                    obj.Shape = prototype
                    obj.Placement = base_placement(index)
                doc.recompute()
                geometry_value = 3.0 if sample == 0 else 3.0 + 0.05 * sample
                placement_value = 0.0 if sample == 0 else 0.5 + 0.25 * (sample - 1)

                def edit():
                    if scenario == "local_geometry":
                        changed = make_plate(geometry_value)
                        for index, obj in enumerate(objects):
                            obj.Shape = changed
                            # Assigning Shape can reset a Part::Feature's
                            # placement in FreeCAD; restore each retained
                            # occurrence explicitly before recompute/export.
                            obj.Placement = base_placement(index)
                    elif scenario == "placement":
                        objects[0].Placement = base_placement(0, placement_value)
                    doc.recompute()

                _, edit_ms = timed(edit)
                volumes, query_ms = timed(lambda: [float(obj.Shape.Volume) for obj in objects])
                if len(volumes) != count or not all(math.isfinite(v) and v > 0 for v in volumes):
                    raise RuntimeError("FreeCAD reference native query failed")
                mesh, mesh_ms = timed(lambda: MeshPart.meshFromShape(
                    Shape=objects[0].Shape, LinearDeflection=0.1,
                    AngularDeflection=0.3, Relative=False,
                ))
                output = output_dir / f"{scenario}-{sample}.step"
                _, export_ms = timed(lambda: Import.export(objects, str(output)))
                digest = hashlib.sha256(output.read_bytes()).hexdigest()
                readback, readback_ms = timed(lambda: Part.read(str(output)))
                expected_volume = sum(volumes)
                if not readback.isValid() or not math.isclose(
                    float(readback.Volume), expected_volume, rel_tol=1e-8, abs_tol=2e-6,
                ):
                    raise RuntimeError("FreeCAD reference STEP readback differs from the document")
                row = {
                    "scenario": scenario, "sample": sample - 1,
                    "measured": sample > 0, "occurrences": count,
                    "geometryValue": geometry_value if scenario == "local_geometry" else 3.0,
                    "placementValue": placement_value if scenario == "placement" else 0.0,
                    "editAndRecomputeMs": edit_ms, "nativeQueryMs": query_ms,
                    "prototypeMeshMs": mesh_ms, "prototypeMeshFacets": mesh.CountFacets,
                    "wholeDocumentStepExportMs": export_ms,
                    "coldStepReadbackMs": readback_ms,
                    "stepBytes": output.stat().st_size, "stepSha256": digest,
                    "documentVolume": expected_volume,
                    "parts": describe_objects(),
                }
                rows.append(row)
                append_jsonl(journal, {"kind": "freecad-sample", **row})
                output.unlink()
        measured = [row for row in rows if row["measured"]]
        stages = ("editAndRecomputeMs", "nativeQueryMs", "prototypeMeshMs",
                  "wholeDocumentStepExportMs", "coldStepReadbackMs")
        summary = {
            scenario: {
                stage: statistics.median(
                    row[stage] for row in measured if row["scenario"] == scenario
                ) for stage in stages
            } for scenario in ("unchanged", "local_geometry", "placement")
        }
        result = {
            "schema": 1, "outcome": "passed", "qualification": "freecad-retained-reference",
            "percentileEvidence": False, "model": model, "samplesPerScenario": plan["samples"],
            "metadata": {"freecad": App.Version(), "occt": Part.OCC_VERSION,
                         "python": sys.version, "platform": platform.platform()},
            "timingBoundary": (
                "retained in-memory FreeCAD document; edit+recompute, exact native query, "
                "prototype mesh, whole-document STEP export and cold STEP readback are separate; no GUI"
            ),
            "geometryEditScope": (
                "whole plate factory (base, four edge fillets, and four through-hole cuts) is rebuilt, "
                "then assigned to retained document occurrences; this is an architecture reference, "
                "not evidence of feature-level dirty-hole recomputation"
            ),
            "meshOptions": {"linearDeflectionMm": 0.1, "angularDeflectionRadians": 0.3,
                            "relative": False},
            "processPeakRssBytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            * (1 if sys.platform == "darwin" else 1024),
            "rows": rows, "summary": summary,
        }
        write_json(Path(plan["workerReport"]), result)
    finally:
        App.closeDocument(doc.Name)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freecad", required=True, help="FreeCADCmd executable")
    parser.add_argument("--model", choices=("plate", "assembly24"), required=True)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--scratch", required=True, help="new private directory below models/")
    parser.add_argument("--report", required=True)
    parser.add_argument("--cadgen-report", required=True,
                        help="complete cadgen harness report used for geometry parity")
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()
    if not 1 <= args.samples <= 10:
        parser.error("--samples must be 1..10")
    if not 1 <= args.timeout <= 600:
        parser.error("--timeout must be 1..600 seconds")
    freecad = Path(args.freecad).resolve()
    if not freecad.is_file():
        raise FileNotFoundError(f"FreeCADCmd not found: {freecad}")
    scratch = under_models(args.scratch)
    report = Path(args.report).resolve()
    journal = report.with_suffix(report.suffix + ".samples.jsonl")
    if scratch.exists() or report.exists() or journal.exists():
        raise FileExistsError("scratch, report, and journal must be new paths")
    scratch.mkdir(parents=True)
    append_jsonl(journal, {"kind": "freecad-run-start", "qualification": "incomplete"})
    with tempfile.TemporaryDirectory(prefix="freecad-document-", dir=scratch) as temporary:
        private = Path(temporary)
        plan = {
            "model": args.model, "samples": args.samples,
            "outputDirectory": str(private), "workerReport": str(private / "result.json"),
            "journal": str(journal),
        }
        plan_path = private / "plan.json"
        write_json(plan_path, plan)
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env["CADGEN_FREECAD_DOCUMENT_PLAN"] = str(plan_path)
        completed = subprocess.run(
            [str(freecad), "-u", str(private / "user.cfg"), "-s", str(private / "system.cfg"),
             str(Path(__file__).resolve())],
            env=env, text=True, capture_output=True, timeout=args.timeout, check=False,
        )
        worker_report = Path(plan["workerReport"])
        if completed.returncode or not worker_report.is_file():
            append_jsonl(journal, {"kind": "freecad-run-incomplete", "outcome": "incomplete",
                                   "exitCode": completed.returncode})
            raise RuntimeError(
                f"FreeCAD reference failed ({completed.returncode}):\n"
                f"{completed.stdout[-2000:]}\n{completed.stderr[-2000:]}"
            )
        result = json.loads(worker_report.read_text(encoding="utf-8"))
        cadgen_path = Path(args.cadgen_report).resolve()
        cadgen = json.loads(cadgen_path.read_text(encoding="utf-8"))
        if cadgen.get("outcome") != "passed":
            raise AssertionError("cadgen comparison report is not complete and passing")

        def close(actual, expected, label):
            if not math.isclose(actual, expected, rel_tol=1e-8, abs_tol=2e-6):
                raise AssertionError(f"cross-engine {label}: {actual} != {expected}")

        cadgen_rows = {}
        for session in cadgen["sessions"]:
            if session["model"] == args.model:
                for row in session["rows"]:
                    cadgen_rows[(session["scenario"], row["sample"])] = row
        checked = 0
        for freecad_row in result["rows"]:
            if not freecad_row["measured"]:
                continue
            key = (freecad_row["scenario"], freecad_row["sample"])
            if key not in cadgen_rows:
                raise AssertionError(f"cadgen report lacks matched sample {key}")
            expected_parts = {part["label"]: part for part in cadgen_rows[key]["oracle"]["parts"]}
            actual_parts = {part["label"]: part for part in freecad_row["parts"]}
            if expected_parts.keys() != actual_parts.keys():
                raise AssertionError(f"cross-engine labels differ for {key}")
            for label in expected_parts:
                expected, actual = expected_parts[label], actual_parts[label]
                if expected["counts"] != actual["counts"] or not actual["valid"]:
                    raise AssertionError(f"cross-engine topology differs for {key}/{label}")
                close(actual["volume"], expected["volume"], f"{key}/{label}.volume")
                close(actual["area"], expected["area"], f"{key}/{label}.area")
                for corner in (0, 1):
                    for axis in range(3):
                        close(actual["bounds"][corner][axis], expected["bounds"][corner][axis],
                              f"{key}/{label}.bounds[{corner}][{axis}]")
                checked += 1
        result["crossEngineGeometryOracle"] = {
            "passed": True, "cadgenReport": str(cadgen_path),
            "matchedOccurrences": checked,
            "fields": ["labels", "validity", "volume", "area", "bounds",
                       "solid/face/edge/vertex counts"],
        }
        result["freecadExecutable"] = str(freecad)
        result["controller"] = {"python": sys.version, "platform": platform.platform()}
        result["rawSampleJournal"] = str(journal)
        write_json(report, result)
        append_jsonl(journal, {"kind": "freecad-run-complete", "outcome": "passed",
                               "report": str(report)})
    print(json.dumps({"outcome": "passed", "report": str(report),
                      "summary": result["summary"]}, indent=2))


if os.environ.get("CADGEN_FREECAD_DOCUMENT_PLAN"):
    worker(Path(os.environ["CADGEN_FREECAD_DOCUMENT_PLAN"]))
elif __name__ == "__main__":
    main()
