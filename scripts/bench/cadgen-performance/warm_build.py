#!/usr/bin/env python3
"""Unprofiled in-process edit timings, with normal stage logs and preview events.

Run with the checkout's cadgen on PYTHONPATH. The default substitutions target
the repository's nine-part planetary fixture; other models supply exact pairs.
The source is restored in finally, including when a build fails.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import statistics
import tempfile
import time
from pathlib import Path
from unittest import mock

from common import metadata, model_path, peak_rss_bytes, sha256, source_fingerprint, write_json


def summary(values):
    return {"count": len(values), "minMs": min(values), "medianMs": statistics.median(values), "maxMs": max(values)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--store", required=True, help="Dedicated benchmark store under models/; never deleted")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--geometry-from", default="CARRIER_DIAMETER = 105.0")
    parser.add_argument("--geometry-to", default="CARRIER_DIAMETER = 106.0")
    parser.add_argument("--placement-from", default="        _make_carrier_plate(),")
    parser.add_argument("--placement-to", default="        _make_carrier_plate().moved(bd.Location((0.0, 0.0, -0.5))),")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    model, store = model_path(args.model), model_path(args.store)
    original, original_stat = model.read_bytes(), model.stat()
    baseline = original.decode("utf-8")
    for old, new in ((args.geometry_from, args.geometry_to), (args.placement_from, args.placement_to)):
        if baseline.count(old) != 1 or old == new:
            parser.error(f"Substitution must match exactly once and change the source: {old!r}")
    variants = {"baseline": baseline, "geometry": baseline.replace(args.geometry_from, args.geometry_to),
                "placement": baseline.replace(args.placement_from, args.placement_to)}
    store.mkdir(parents=True, exist_ok=True)
    os.environ.update(CADGEN_CACHE_DIR=str(store), CADGEN_DAEMON="0", CADGEN_EVENTS="1", PYTHONDONTWRITEBYTECODE="1")
    from cadgen.cli._run_model import run_model_argv
    from cadgen.daemon import executors
    from cadgen._internal import op_memo
    from cadgen.store.records import read_record
    from cadgen.store.trees import flatten
    from cadgen.step_scene import read_step
    import build123d  # noqa: F401 - exclude kernel startup from timed runs

    report = {"metadata": metadata(), "model": str(model), "sourceSha256": sha256(original),
              "store": str(store), "timingBoundary": "same interpreter, kernel imported; excludes startup, source writes and daemon IPC; no profiler",
              "substitutions": {"geometry": [args.geometry_from, args.geometry_to],
                                "placement": [args.placement_from, args.placement_to]}, "runs": []}
    logs = args.report.resolve().with_suffix("").with_name(args.report.stem + "-logs")
    logs.mkdir(parents=True, exist_ok=True)

    def run(label: str, variant: str, *, measured: bool):
        model.write_bytes(variants[variant].encode("utf-8"))
        events = []
        before_ops = op_memo.stats()
        started = time.perf_counter()

        def event_sink(event):
            events.append({"elapsedMs": (time.perf_counter() - started) * 1000, **event})

        executors.set_event_sink(event_sink)
        log_path = logs / f"{len(report['runs']):02d}-{label}.log"
        with log_path.open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            code = run_model_argv([str(model), "--verbose"])
        elapsed = (time.perf_counter() - started) * 1000
        after_ops = op_memo.stats()
        record = read_record(model) or {}
        tree = flatten(record["tree"]) if record.get("tree") else {}
        stage_pattern = r"^\[cadgen\] (.+?) completed in ([0-9.]+)(ms|s)$"
        stages = [{"label": match[0], "milliseconds": float(match[1]) * (1000 if match[2] == "s" else 1)}
                  for match in re.findall(stage_pattern, log_path.read_text(), flags=re.MULTILINE)]
        previews = [event for event in events if event.get("preview")]
        saves = [event for event in events if event.get("saved")]
        row = {"run": label, "variant": variant, "measured": measured, "milliseconds": elapsed, "exit": code,
               "ops": {key: value - before_ops.get(key, 0) for key, value in after_ops.items()},
               "events": events, "stages": stages, "tree": record.get("tree"), "documentHash": record.get("stepHash"),
               "components": sorted((tree.get("components") or {}).keys()), "occurrences": len(tree.get("occurrences") or []),
               "firstPreviewMs": previews[0]["elapsedMs"] if previews else None,
               "savedMs": saves[-1]["elapsedMs"] if saves else None,
               "processPeakRssBytes": peak_rss_bytes()}
        report["runs"].append(row)
        write_json(args.report, report)
        print(json.dumps({key: row[key] for key in ("run", "milliseconds", "exit", "firstPreviewMs", "savedMs")}), flush=True)
        if code:
            raise RuntimeError(f"{label} failed; see {log_path}")
        return record

    try:
        for variant in ("baseline", "geometry", "baseline", "placement", "baseline"):
            run(f"prime-{variant}", variant, measured=False)
        for iteration in range(args.iterations):
            for name, variant in (("unchanged", "baseline"), ("geometry", "geometry"),
                                  ("restore-geometry", "baseline"), ("placement", "placement"), ("restore-placement", "baseline")):
                record = run(f"{name}-{iteration + 1}", variant, measured=not name.startswith("restore"))
        steps = [Path(path) for path in record.get("outputs", {}) if Path(path).suffix.lower() in {".step", ".stp"}]
        if len(steps) != 1:
            raise RuntimeError("Benchmark expects exactly one STEP output")
        step = steps[0]
        imports = []
        # A separate empty import cache proves publication of a first read.
        # Its compile subprocess startup is included and labelled explicitly.
        with tempfile.TemporaryDirectory(prefix="import-benchmark-", dir=store.parent) as scratch:
            scratch_path = Path(scratch)
            imported = scratch_path / "input.step"
            shutil.copyfile(step, imported)
            os.environ["CADGEN_CACHE_DIR"] = str(scratch_path / "store")
            for index in range(args.iterations + 1):
                started = time.perf_counter()
                guard = mock.patch.object(executors, "submit_compile", side_effect=AssertionError("cached import requested a compile")) if index else contextlib.nullcontext()
                with guard:
                    shape = read_step(imported)
                imports.append({"cache": "cold" if index == 0 else "warm", "milliseconds": (time.perf_counter() - started) * 1000,
                                "volume": shape.volume, "compileForbidden": bool(index)})
                del shape
            report["imports"] = {"inputSha256": sha256(imported.read_bytes()), "inputBytes": imported.stat().st_size,
                                 "coldIncludesCompileProcessStartup": True, "runs": imports}
        report["summary"] = {
            label: summary([row["milliseconds"] for row in report["runs"] if row["measured"] and row["run"].startswith(label + "-")])
            for label in ("unchanged", "geometry", "placement")}
        report["imports"]["warmSummary"] = summary([row["milliseconds"] for row in imports if row["cache"] == "warm"])
        return 0
    finally:
        model.write_bytes(original)
        os.utime(model, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        os.environ["CADGEN_CACHE_DIR"] = str(store)
        executors.set_event_sink(None)
        report["sourceRestored"] = model.read_bytes() == original
        report["runtimeUnchangedDuringStudy"] = source_fingerprint() == report["metadata"]["sourceFingerprint"]
        write_json(args.report, report)


if __name__ == "__main__":
    raise SystemExit(main())
