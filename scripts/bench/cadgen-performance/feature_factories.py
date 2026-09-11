#!/usr/bin/env python3
"""Bounded public-build comparison for opt-in pure intermediate factories.

The outer process enforces a wall-clock deadline. Fixtures/outputs live under
models/; the report contains timing and identity evidence, never CAD payloads.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FACTORY = """\
from cadgen import build123d as bd
from cadgen import feature

@feature
def plate(width, holes):
    with bd.BuildPart() as p:
        bd.Box(width, 20, 6)
        for i in range(holes):
            with bd.Locations((-width/2 + 5 + i*(width-10)/(holes-1), 0, 0)):
                bd.Cylinder(1.5, 10, mode=bd.Mode.SUBTRACT)
    return p.part
"""
PARENT = """\
from cadgen import build123d as bd
from cadgen import step
from feature_geometry import plate

REQUEST = {request}
SHIFT = {shift}

@step
def assembly():
    parts = []
    for i in range({count}):
        part = bd.Pos((i % 8)*90, (i // 8)*35 + SHIFT, 0) * plate(70.0 + (i % 3)*4, 6 + (i % 2)*6)
        part.label = 'plate-' + str(i)
        parts.append(part)
    return bd.Compound(children=parts, label='assembly')

if __name__ == '__main__':
    assembly()
"""
GEOMETRY_PARENT = PARENT.replace(
    "plate(70.0 + (i % 3)*4,",
    "plate((70.0 + {width_delta}) if i == 0 else 70.0 + (i % 3)*4,",
)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--scenario", choices=("placement", "local-geometry"), default="placement")
    result.add_argument("--parts", nargs="+", type=int)
    result.add_argument("--repeats", type=int, default=3)
    result.add_argument("--timeout", type=float, default=90)
    result.add_argument("--output", type=Path, default=REPO / "models/tmp/feature-factories-benchmark")
    result.add_argument("--report", type=Path, required=True)
    result.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    return result


def run(args):
    from cadgen.daemon.worker import _warm_imports

    # Reproduce the worker's real pre-authored initialization. Direct/embedded
    # run_model_argv callers have no witness and deliberately cannot reuse.
    _warm_imports()
    from cadgen import features
    from cadgen.cli._run_model import run_model_argv
    from cadgen.daemon import executors
    from cadgen.store.records import read_record
    from cadgen.store.trees import get_tree

    if not features._reuse_trusted:
        raise RuntimeError("fresh worker did not establish the feature witness")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    geometry_edit = args.scenario == "local-geometry"
    # Novel width arguments must really miss on every invocation, including a
    # repeated benchmark command in the same output directory.
    store_name = f"store-local-geometry-{time.time_ns()}" if geometry_edit else "store"
    os.environ["CADGEN_CACHE_DIR"] = str(output / store_name)
    os.environ["CADGEN_DAEMON"] = "0"
    os.environ["CADGEN_OP_MEMO"] = "1"
    os.environ["CADGEN_OP_MEMO_DISK"] = "1"
    helper = output / "feature_geometry.py"
    helper.write_text(FACTORY, encoding="utf-8")
    request = 0
    records = []

    def build(count, shift, enabled, measured, width_delta=0):
        nonlocal request
        request += 1
        script = output / f"assembly_{count}.py"
        # REQUEST deliberately changes source identity while retaining identical
        # geometry, so both members of a matched pair execute through the gate.
        template = GEOMETRY_PARENT if geometry_edit else PARENT
        script.write_text(template.format(count=count, shift=shift, request=request,
                                          width_delta=width_delta), encoding="utf-8")
        os.environ["CADGEN_FEATURE_CACHE"] = "1" if enabled else "0"
        before = dict(features._stats)
        events = []
        started = time.perf_counter()
        executors.set_event_sink(lambda event: events.append(((time.perf_counter() - started)*1000, event)))
        log = io.StringIO()
        try:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                code = run_model_argv([str(script)])
        finally:
            executors.set_event_sink(None)
        elapsed = (time.perf_counter() - started)*1000
        if code:
            raise RuntimeError(log.getvalue())
        record = read_record(script)
        step = script.with_suffix(".step")
        payload = step.read_bytes()
        delta = {name: value - before[name] for name, value in features._stats.items()}
        row = {"parts": count, "shift": shift, "reuse": enabled, "measured": measured,
               "completeMs": elapsed,
               "previewMs": next((ms for ms, event in events if event.get("preview")), None),
               "sourceResultMs": next((ms for ms, event in events if event.get("sourceResult")), None),
               "features": delta, "tree": record["tree"], "stepBytes": len(payload),
               "stepSha256": hashlib.sha256(payload).hexdigest()}
        if geometry_edit:
            tree = get_tree(record["tree"])
            occurrences = {
                item["name"]: {"component": item["component"], "transform": item["transform"],
                               "brep": tree["components"][item["component"]]["brep"]}
                for item in tree["occurrences"]
            }
            if set(occurrences) != {f"plate-{index}" for index in range(count)}:
                raise RuntimeError("unexpected occurrence names in source result")
            row.update(firstWidth=70.0 + width_delta, occurrences=occurrences)
        if measured:
            misses = 1 if enabled and geometry_edit else (0 if enabled else count)
            expected = {"hits": count - misses, "misses": misses, "declined": 0, "unstorable": 0}
            if delta != expected:
                raise RuntimeError(f"expected feature counters {expected}, got {delta}")
        records.append(row)
        return row

    summaries = []
    for count in args.parts:
        # Prime kernel operations, feature entries and the ordinary writer.
        baseline = build(count, 0, True, False)
        build(count, 0 if geometry_edit else 1, False, False)
        if geometry_edit and baseline["features"]["misses"] != 6:
            raise RuntimeError("baseline did not prime exactly six unique feature inputs")
        pairs = []
        for index in range(args.repeats):
            shift = 0 if geometry_edit else 2 + index
            # Alternate ordering to avoid giving one mode all second-in-pair
            # saved-byte/readback reuse. Every source revision is still new.
            order = (False, True) if index % 2 == 0 else (True, False)
            pair = {}
            for position, enabled in enumerate(order):
                row = build(count, shift, enabled, True, width_delta=index + 1 if geometry_edit else 0)
                if geometry_edit:
                    row.update(pair=index + 1, orderInPair=position + 1)
                    changed = [name for name, value in row["occurrences"].items()
                               if value["component"] != baseline["occurrences"][name]["component"]]
                    if changed != ["plate-0"]:
                        raise RuntimeError(f"expected only occurrence 0 geometry to change, got {changed}")
                    for name, value in row["occurrences"].items():
                        original = baseline["occurrences"][name]
                        if value["transform"] != original["transform"]:
                            raise RuntimeError(f"geometry edit changed placement for {name}")
                        if (value["brep"] != original["brep"]) != (name == "plate-0"):
                            raise RuntimeError(f"unexpected geometry-byte identity change for {name}")
                    row["changedComponents"] = changed
                pair[enabled] = row
            if any(pair[False][key] != pair[True][key] for key in ("tree", "stepSha256", "stepBytes")):
                raise RuntimeError("matched source builds produced different trees or STEP bytes")
            pairs.append(pair)
        summary = {"parts": count, "stepBytes": pairs[0][False]["stepBytes"], "pairs": len(pairs)}
        if geometry_edit:
            summary.update(changedOccurrences=1, unchangedOccurrences=count - 1)
        for phase in ("sourceResultMs", "previewMs", "completeMs"):
            before = statistics.median(pair[False][phase] for pair in pairs)
            after = statistics.median(pair[True][phase] for pair in pairs)
            summary[phase] = {"before": before, "after": after, "speedup": before/after}
        summaries.append(summary)

    from importlib.metadata import version
    provenance = {}
    for relative in ("packages/cadgen/src/cadgen/features.py", "packages/cadgen/src/cadgen/_internal/op_memo.py",
                     "packages/cadgen/src/cadgen/_internal/generation_runner.py", "packages/cadgen/src/cadgen/daemon/worker.py"):
        provenance[relative] = hashlib.sha256((REPO / relative).read_bytes()).hexdigest()
    report = {"boundary": "Warm worker bootstrap, normal public source builds, baseline op_memo primed in both modes; source writes excluded. Preview event is not a browser frame. STEP completion includes ordinary persistence/readback.",
              "scenario": ("One occurrence changes width; eight retain baseline arguments. Each pair uses a novel width and verifies only occurrence 0 geometry changes."
                           if geometry_edit else "Placement-only revisions of repeated pure feature parts; REQUEST causes both matched variants to rebuild identical geometry."),
              "orderQualification": "Each pair alternates cache-off/cache-on order. The second build can reuse the first build's saved-byte/readback results and kernel operations; novel geometry is not separately primed. Individual order and rows are retained for the local-geometry scenario.",
              "platform": platform.platform(), "python": platform.python_version(),
              "versions": {name: version(name) for name in ("build123d", "cadquery-ocp-novtk")},
              "sourceSha256": provenance, "helperSha256": hashlib.sha256(FACTORY.encode()).hexdigest(),
              "summaries": summaries, "runs": records}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summaries, indent=2))


def main():
    args = parser().parse_args()
    if args.parts is None:
        args.parts = [9] if args.scenario == "local-geometry" else [3, 9, 24]
    if not 1 <= args.repeats <= 5 or not args.parts or any(not 1 <= count <= 32 for count in args.parts):
        raise SystemExit("Use 1–32 parts and 1–5 repetitions; this harness is intentionally bounded.")
    if not 1 <= args.timeout <= 120:
        raise SystemExit("Use a wall-clock budget of at most 120 seconds.")
    if args.scenario == "local-geometry" and (args.parts != [9] or args.repeats > 3 or args.timeout > 60):
        raise SystemExit("Local geometry edits use nine parts, at most three pairs and a timeout of at most 60 seconds.")
    if not args.output.resolve().is_relative_to(REPO / "models"):
        raise SystemExit("CAD fixtures and outputs must live under models/.")
    if args.worker:
        run(args)
    else:
        completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--worker"],
                                   timeout=args.timeout)
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
