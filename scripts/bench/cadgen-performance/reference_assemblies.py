#!/usr/bin/env python3
"""Bounded paired reference-assembly source-preview and complete-save timings.

Run from the repository with PYTHONPATH=packages/cadgen/src:. and a CAD Python.
Each invocation has an 85-second alarm, uses a fresh models/tmp directory, and
compares exact output bytes with the private optimization enabled and disabled.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import statistics
import time
from unittest import mock

from common import REPO, model_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=("small", "planetary"), required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--planetary-source", type=model_path,
                        default=REPO / "models/examples/performance/planetary_split/src")
    args = parser.parse_args()
    signal.alarm(85)

    from tests.python.support.tmp_root import generated_cad_directory
    from cadgen.cli._run_model import run_model_argv
    from cadgen.store import _references
    from cadgen.store.records import read_record, remove_record
    from cadgen._internal import component_package, surface_extract
    from cadgen import step_export
    from cadgen.daemon import executors

    lazy = importlib.import_module("cadgen.store.lazy")
    rows, faces = [], None
    models = {
        "block": "bd.Solid.make_box(8, 6, 4)",
        "ring": "bd.Solid.make_torus(7, 1)",
        "bore": "bd.Solid.make_box(10, 10, 5).cut(bd.Solid.make_cylinder(2, 8, plane=bd.Plane((5, 5, -1))))",
    }
    with generated_cad_directory(prefix="reference-benchmark-") as directory:
        root = Path(directory)
        os.environ.update(CADGEN_CACHE_DIR=str(root / "store"), CADGEN_DAEMON="0", CADGEN_JOBS="1")
        log = io.StringIO()
        if args.fixture == "small":
            seeds = []
            for name, geometry in models.items():
                path = root / f"{name}.py"
                path.write_text(f"from cadgen import step, build123d as bd\n@step\ndef {name}():\n    return {geometry}\n")
                seeds.append(path)
            counts = (2, 9, 24)
        else:
            shutil.copytree(args.planetary_source, root / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            parent = root / "src/planetary_gear_assembly.py"
            source = parent.read_text()
            source = source.replace("bd.Compound(obj=parts, children=parts,", "bd.Compound(children=parts,")
            if "CARRIER_OFFSET_Z = 0.0" not in source or "bd.Compound(children=parts," not in source:
                raise ValueError("Planetary source changed; review the workload before updating the benchmark")
            names = ("carrier_plate", "ring_gear", "sun_gear", "planet_gear_1", "planet_pin_1",
                     "planet_gear_2", "planet_pin_2", "planet_gear_3", "planet_pin_3")
            seeds = [root / "src" / f"{name}.py" for name in names]
            counts = (9,)
        for path in seeds:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                assert run_model_argv([str(path), "--json"]) == 0, log.getvalue()

        def run(path, output, enabled):
            remove_record(path)
            counters = dict(native_decodes=0, brep_serializations=0, xcaf_documents=0,
                            child_materializations=0, surfaces=0)
            checkpoints = {}

            def counted(key, original):
                def invoke(*values, **kwargs):
                    counters[key] += 1
                    return original(*values, **kwargs)
                return invoke

            original_emit = executors.emit_event

            def emit(event):
                if event.get("preview", {}).get("output") == str(output):
                    checkpoints["preview_ms"] = (time.perf_counter() - start) * 1000
                    checkpoints["at_preview"] = dict(counters)
                return original_emit(event)

            with mock.patch.object(_references, "_ENABLED", enabled), \
                    mock.patch.object(component_package, "_decode_brep", counted("native_decodes", component_package._decode_brep)), \
                    mock.patch.object(component_package, "_shape_brep_bytes", counted("brep_serializations", component_package._shape_brep_bytes)), \
                    mock.patch.object(step_export, "_create_bin_xcaf_doc", counted("xcaf_documents", step_export._create_bin_xcaf_doc)), \
                    mock.patch.object(lazy, "_materialize_tree", counted("child_materializations", lazy._materialize_tree)), \
                    mock.patch.object(surface_extract, "extract_surface_component", counted("surfaces", surface_extract.extract_surface_component)), \
                    mock.patch.object(executors, "emit_event", emit), \
                    contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                start = time.perf_counter()
                code = run_model_argv([str(path), "--json"])
                elapsed = (time.perf_counter() - start) * 1000
            assert code == 0 and "preview_ms" in checkpoints, log.getvalue()
            return dict(enabled=enabled, complete_ms=elapsed, counts=counters, **checkpoints,
                        tree=read_record(path)["tree"], step_sha=hashlib.sha256(output.read_bytes()).hexdigest())

        for count in counts:
            for revision in range(3):
                if args.fixture == "small":
                    parent = root / f"assembly_{count}.py"
                    children = [f"bd.Pos({index * 17 + revision}, {index % 3 * 11}, 0) * {list(models)[index % 3]}()"
                                for index in range(count)]
                    parent.write_text("from cadgen import step, build123d as bd\n"
                                      "from block import block\nfrom ring import ring\nfrom bore import bore\n"
                                      f"@step\ndef assembly_{count}():\n"
                                      f"    return bd.Compound(children=[{', '.join(children)}], label='assembly')\n")
                    output = parent.with_suffix(".step")
                else:
                    parent.write_text(source.replace("CARRIER_OFFSET_Z = 0.0", f"CARRIER_OFFSET_Z = {revision}.0"))
                    output = root / "STEP/planetary.step"
                run(parent, output, True)  # Equal exact-revision artifact readback/scalar cache state.
                order = (False, True) if revision % 2 == 0 else (True, False)
                pair = [run(parent, output, enabled) for enabled in order]
                assert pair[0]["tree"] == pair[1]["tree"]
                assert pair[0]["step_sha"] == pair[1]["step_sha"]
                rows.extend(dict(occurrences=count, revision=revision, **value) for value in pair)
        if args.fixture == "planetary":
            from cadgen.store.materialize import materialize

            faces = len(materialize(read_record(parent)["tree"]).faces())

    summary = []
    for count in counts:
        entry = {"occurrences": count}
        for enabled in (False, True):
            samples = [row for row in rows if row["occurrences"] == count and row["enabled"] == enabled]
            entry["reference" if enabled else "ordinary"] = {
                "preview_ms": statistics.median(row["preview_ms"] for row in samples),
                "complete_ms": statistics.median(row["complete_ms"] for row in samples),
                "at_preview": samples[0]["at_preview"], "counts": samples[0]["counts"],
            }
        summary.append(entry)
    result = dict(summary=summary, samples=rows, timed_calls=len(rows), prewarm_calls=len(rows) // 2,
                  fixture=args.fixture, faces=faces,
                  method="Actual run_model_argv, warm kernels/current children, three paired placement revisions, alternating enabled/disabled order; each exact revision prewarms artifact readback. CLI-call to source-preview and complete-save elapsed; no browser first-frame claim.")
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
