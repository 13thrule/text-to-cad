#!/usr/bin/env python3
"""Compare completed monolithic/split planetary builds before timing them.

Reads existing records only to locate the explicit saved artifacts. Geometry
checks then forbid model-record reads, STEP parsing and compilation. No model
is built by this command.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from unittest import mock

from common import metadata, model_path, sha256, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monolithic-model", required=True, type=model_path)
    parser.add_argument("--split-model", required=True, type=model_path)
    parser.add_argument("--store", required=True, type=model_path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    os.environ["CADGEN_CACHE_DIR"] = str(args.store)
    from cadgen.store import records
    from cadgen.store.trees import flatten
    from cadgen.daemon import executors
    from cadgen._internal import step_scene_package
    from cadgen.step_scene import read_step
    import build123d

    report = {"metadata": metadata(), "models": {}, "checks": {}}
    for name, model in (("monolithic", args.monolithic_model), ("split", args.split_model)):
        record = records.read_record(model) or {}
        outputs = [Path(path) for path in record.get("outputs", {}) if Path(path).suffix.lower() in {".step", ".stp"}]
        if len(outputs) != 1 or not record.get("documentTree"):
            raise ValueError(f"Build {model} into the supplied store first; expected one saved STEP and documentTree")
        step = outputs[0]
        document = flatten(record["documentTree"])
        authored = flatten(record["tree"])
        if document is None or authored is None:
            raise ValueError(f"Missing saved/authored tree for {model}")
        with mock.patch.object(records, "read_record", side_effect=AssertionError("saved reader consulted source record")), \
             mock.patch.object(step_scene_package, "_load_step_scene_text", side_effect=AssertionError("saved reader parsed STEP")), \
             mock.patch.object(build123d, "import_step", side_effect=AssertionError("saved reader used raw STEP fallback")), \
             mock.patch.object(executors, "submit_compile", side_effect=AssertionError("saved reader compiled STEP")):
            shape = read_step(step)
        bounds = shape.bounding_box()
        occurrences = {item["name"]: {key: item.get(key) for key in ("component", "transform", "color")}
                       for item in document["occurrences"]}
        report["models"][name] = {
            "model": str(model), "sourceSha256": sha256(model.read_bytes()), "step": str(step),
            "stepSha256": sha256(step.read_bytes()), "stepBytes": step.stat().st_size,
            "authoredTree": record["tree"], "documentTree": record["documentTree"],
            "sourceComponentIds": sorted(authored["components"]), "savedComponentIds": sorted(document["components"]),
            "occurrences": occurrences, "occurrenceCount": len(document["occurrences"]),
            "volume": shape.volume, "solidCount": len(shape.solids()), "faceCount": len(shape.faces()),
            "bbox": {"min": list(bounds.min), "max": list(bounds.max)},
            "valid": bool(shape.is_valid), "childPins": record.get("children") or [],
            "savedReadGuardsPassed": True,
        }

    mono, split = report["models"]["monolithic"], report["models"]["split"]
    checks = report["checks"]
    checks["bothHaveNineSolidsOccurrencesComponents"] = all(
        item["solidCount"] == item["occurrenceCount"] == len(item["savedComponentIds"]) == 9
        for item in (mono, split))
    checks["bothValid"] = mono["valid"] and split["valid"]
    checks["volumeMatches"] = math.isclose(mono["volume"], split["volume"], rel_tol=1e-12, abs_tol=1e-7)
    checks["bboxMatches"] = all(math.isclose(a, b, rel_tol=0, abs_tol=1e-7)
                               for key in ("min", "max") for a, b in zip(mono["bbox"][key], split["bbox"][key]))
    checks["savedComponentsIdentical"] = mono["savedComponentIds"] == split["savedComponentIds"]
    checks["savedNamesColorsPlacementsAndComponentsIdentical"] = mono["occurrences"] == split["occurrences"]
    checks["splitHasNineChildPins"] = len(split["childPins"]) == 9
    report["savedStepBytesIdentical"] = mono["stepSha256"] == split["stepSha256"]
    report["savedTreeIdentical"] = mono["documentTree"] == split["documentTree"]
    report["passed"] = all(checks.values())
    write_json(args.report, report)
    print(json.dumps({"passed": report["passed"], "checks": checks,
                      "savedStepBytesIdentical": report["savedStepBytesIdentical"],
                      "savedTreeIdentical": report["savedTreeIdentical"]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
