#!/usr/bin/env python3
"""Prepare and validate the imported nine-part STEP edit benchmark.

This is fixture support, not a runtime path or a timing wrapper. Use the
unchanged warm_build.py harness for measurements after validation finishes.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import importlib.util
import math
import os
from pathlib import Path
import sys
import tempfile

from common import REPO, metadata, model_path, sha256, write_json

MODEL = "src/planetary_gear_assembly.py"
VARIANTS = {
    "baseline": None,
    "geometry": ("CARRIER_DIAMETER = 105.0", "CARRIER_DIAMETER = 106.0"),
    "placement": ("CARRIER_OFFSET_Z = 0.0", "CARRIER_OFFSET_Z = -0.5"),
}


def prepare(args):
    source, directory = model_path(args.step), model_path(args.directory)
    template = Path(args.template).resolve() if args.template else (
        REPO / "models/examples/performance/planetary_imported" / MODEL
    )
    payloads = {directory / MODEL: template.read_bytes(),
                directory / "input/planetary.step": source.read_bytes()}
    for path, payload in payloads.items():
        if path.exists() and path.read_bytes() != payload:
            raise FileExistsError(f"Refusing to replace a different prepared input: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    write_json(directory / "preparation.json", {
        "inputSource": str(source), "template": str(template),
        "files": {str(path.relative_to(directory)): {"sha256": sha256(payload), "bytes": len(payload)}
                  for path, payload in payloads.items()},
    })
    print(directory / MODEL)


def describe(root):
    def color(value):
        return list(value) if value is not None else None

    parts = {}
    for part in root.children:
        if part.label in parts:
            raise AssertionError(f"Duplicate part label: {part.label}")
        bounds = part.bounding_box()
        parts[part.label] = {
            "volume": part.volume, "area": part.area,
            "bounds": [list(bounds.min), list(bounds.max)],
            "color": color(part.color), "solids": len(part.solids()),
            "faces": len(part.faces()), "edges": len(part.edges()),
            "vertices": len(part.vertices()), "valid": part.is_valid,
        }
    if len(parts) != 9 or "carrier_plate" not in parts:
        raise AssertionError("Expected nine named parts, including carrier_plate")
    if not all(part["solids"] == 1 and part["valid"] for part in parts.values()):
        raise AssertionError("Every occurrence must contain one valid solid")
    return {"label": root.label, "color": color(root.color), "parts": parts}


def same_values(actual, expected, context="geometry"):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys(), context
        for key, value in expected.items():
            same_values(actual[key], value, f"{context}.{key}")
    elif isinstance(expected, list):
        assert len(actual) == len(expected), context
        for index, value in enumerate(expected):
            same_values(actual[index], value, f"{context}[{index}]")
    elif isinstance(expected, float):
        assert math.isclose(actual, expected, rel_tol=1e-8, abs_tol=2e-6), (context, actual, expected)
    else:
        assert actual == expected, (context, actual, expected)


def validate(args):
    directory = model_path(args.directory)
    model, source = directory / MODEL, directory / "input/planetary.step"
    original, original_stat = model.read_bytes(), model.stat()
    input_bytes = source.read_bytes()
    store = directory / "validation-store"
    os.environ.update(CADGEN_CACHE_DIR=str(store / "build"), CADGEN_DAEMON="0", PYTHONDONTWRITEBYTECODE="1")
    from cadgen.cli._run_model import run_model_argv
    from cadgen.step_scene import read_step
    import cadgen

    report = {"metadata": metadata(), "cadgenModule": str(Path(cadgen.__file__).resolve()),
              "helperSha256": sha256(Path(__file__).read_bytes()),
              "model": str(model), "sourceSha256": sha256(original),
              "inputSha256": sha256(input_bytes), "inputBytes": len(input_bytes), "variants": {}}
    baseline = describe(read_step(source))
    report["input"] = baseline
    try:
        for name, substitution in VARIANTS.items():
            text = original.decode()
            if substitution:
                before, after = substitution
                assert text.count(before) == 1
                text = text.replace(before, after)
            model.write_text(text)
            spec = importlib.util.spec_from_file_location("imported_planetary_validation", model)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            captured = {}

            def capture_input(path):
                shape = read_step(path)
                captured.update({part.label: part.wrapped for part in shape.children})
                return shape

            # Observe the public input without replacing its behavior. This
            # separate untimed body check proves native retention before save.
            module.read_step = capture_input
            authored = module.planetary_gear_assembly.__wrapped__()
            source_description = describe(authored)
            retained = [part.label for part in authored.children if part.label != "carrier_plate"
                        and part.wrapped.IsSame(captured[part.label])]
            assert len(retained) == 8, retained
            expected = copy.deepcopy(baseline)
            carrier = expected["parts"]["carrier_plate"]
            if name == "geometry":
                carrier["volume"] = math.pi * ((106 / 2) ** 2 - 3 * 3.2 ** 2) * 4
                carrier["bounds"] = [[-53.0, -53.0, -5.0], [53.0, 53.0, -1.0]]
                # Analytic exposed area of both annular faces and four walls.
                carrier["area"] = 2 * math.pi * ((106 / 2) ** 2 - 3 * 3.2 ** 2) + 2 * math.pi * (106 / 2 + 3 * 3.2) * 4
            elif name == "placement":
                for corner in carrier["bounds"]:
                    corner[2] -= 0.5
            same_values(source_description, expected, f"{name}.source")
            log = directory / f"validation-{name}.log"
            with log.open("w") as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                code = run_model_argv([str(model), "--verbose"])
            assert code == 0, f"Build failed; see {log}"
            output = directory / "STEP/planetary.step"
            # A fresh store for each variant forces a read of the saved STEP's
            # bytes, rather than validating its already-cached source tree.
            with tempfile.TemporaryDirectory(prefix=f"readback-{name}-", dir=store) as readback_store:
                os.environ["CADGEN_CACHE_DIR"] = readback_store
                try:
                    saved = describe(read_step(output))
                finally:
                    os.environ["CADGEN_CACHE_DIR"] = str(store / "build")
            same_values(saved, expected, f"{name}.saved")
            report["variants"][name] = {
                "sourceSha256": sha256(text.encode()), "retainedNativeParts": sorted(retained),
                "source": source_description, "saved": saved,
                "savedReadbackFreshStore": True,
                "stepSha256": sha256(output.read_bytes()), "stepBytes": output.stat().st_size,
            }
    finally:
        model.write_bytes(original)
        os.utime(model, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        report["sourceRestored"] = model.read_bytes() == original
        report["inputUnchanged"] = source.read_bytes() == input_bytes
        report["runtimeUnchangedDuringValidation"] = metadata()["sourceFingerprint"] == report["metadata"]["sourceFingerprint"]
        write_json(args.report, report)
    assert report["sourceRestored"] and report["inputUnchanged"]
    print(f"Validated all three variants: {args.report}")


def verify_report(args):
    import json
    report = json.loads(args.report.read_text())
    baseline = set(report["runs"][0]["components"])
    checks = []
    for row in report["runs"]:
        components = set(row["components"])
        assert row["exit"] == 0 and row["occurrences"] == 9 and len(components) == len(baseline), row["run"]
        removed, added = baseline - components, components - baseline
        expected = 1 if row.get("variantKind", row["variant"]) == "geometry" else 0
        assert len(removed) == len(added) == expected, (row["run"], removed, added)
        checks.append({"run": row["run"], "retainedComponents": len(baseline & components),
                       "removed": sorted(removed), "added": sorted(added)})
    for field in ("sourceRestored", "inputClosureUnchangedAfterRestoration", "runtimeUnchangedDuringStudy"):
        assert report[field], field
    write_json(args.output, {"report": str(args.report), "reportSha256": sha256(args.report.read_bytes()),
                             "sourceSha256": report["sourceSha256"], "checks": checks})
    print(f"Verified every measured and priming build: {args.output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--step", required=True)
    prepare_parser.add_argument("--directory", required=True)
    prepare_parser.add_argument("--template", help="Model source override for an archived runtime study")
    prepare_parser.set_defaults(run=prepare)
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("--directory", required=True)
    validate_parser.add_argument("--report", required=True, type=Path)
    validate_parser.set_defaults(run=validate)
    verify_parser = commands.add_parser("verify-report")
    verify_parser.add_argument("--report", required=True, type=Path)
    verify_parser.add_argument("--output", required=True, type=Path)
    verify_parser.set_defaults(run=verify_report)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
