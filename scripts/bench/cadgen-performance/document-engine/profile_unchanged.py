#!/usr/bin/env python3
"""Profile warmed unchanged direct document-program requests.

This diagnostic deliberately runs inside the native owner process so cProfile
can attribute source replay and publication work.  It excludes DocumentWorker
IPC and is therefore not a full-request benchmark or speedup measurement.
"""

from __future__ import annotations

import argparse
import cProfile
from dataclasses import asdict, is_dataclass
import hashlib
import json
import os
from pathlib import Path
import pstats
import sys
import time


MODELS = {"plate": "plate.step", "assembly24": "assembly24.step"}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("rb") as stream:
        return sum(1 for _line in stream)


def _closed(value):
    if is_dataclass(value):
        return {key: _closed(item) for key, item in asdict(value).items()}
    if type(value) in (str, int, float, bool) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_closed(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _closed(item) for key, item in value.items()}
    raise TypeError(f"profile report cannot encode {type(value).__name__}")


def _profile_rows(profile: cProfile.Profile, *, order: str, limit: int) -> list[dict]:
    stats = pstats.Stats(profile)
    index = 3 if order == "cumulative" else 2
    rows = []
    for (filename, line, function), values in sorted(
            stats.stats.items(), key=lambda item: item[1][index], reverse=True)[:limit]:
        primitive_calls, total_calls, total_seconds, cumulative_seconds, _callers = values
        rows.append({
            "file": filename,
            "line": line,
            "function": function,
            "primitiveCalls": primitive_calls,
            "totalCalls": total_calls,
            "totalSeconds": total_seconds,
            "cumulativeSeconds": cumulative_seconds,
        })
    return rows


def _receipt_facts(receipt) -> dict:
    value = _closed(receipt)
    destination = Path(value["destination"])
    payload = destination.read_bytes()
    if value["sha256"] != _sha256(payload) or value["size"] != len(payload):
        raise RuntimeError("publication receipt does not attest the actual STEP bytes")
    return {**value, "actualSha256": _sha256(payload), "actualBytes": len(payload)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=tuple(MODELS), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--candidate-revision", required=True)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--top", type=int, default=50)
    args = parser.parse_args()
    if args.iterations < 1 or args.iterations > 20:
        parser.error("--iterations must be between 1 and 20")
    if args.top < 1 or args.top > 200:
        parser.error("--top must be between 1 and 200")

    source = args.source.resolve()
    payload = source.read_bytes()
    digest = _sha256(payload)
    scratch = args.scratch.resolve()
    logical_source = scratch / "source" / source.name
    output = logical_source.parent / MODELS[args.model]
    trace = scratch / "source-trace.jsonl"
    profile_path = scratch / f"{args.model}-unchanged.prof"
    scratch.mkdir(parents=True, exist_ok=True)
    logical_source.parent.mkdir(parents=True, exist_ok=True)
    if logical_source.exists():
        raise RuntimeError("captured logical source must remain absent during execution")
    os.environ["CADGEN_DAEMON"] = "0"
    os.environ["CADGEN_DOCUMENT_BENCH_SOURCE_TRACE"] = str(trace)

    from cadgen._document.service import DocumentService
    from cadgen._document.sources import CapturedInput
    import cadgen

    captured = CapturedInput(logical_source, payload, digest)
    service = DocumentService(max_documents=1)
    prime = service.generate_captured(captured)
    prime_attempt = service.last_attempt
    if prime_attempt is None:
        raise RuntimeError("prime request did not expose a build attempt")
    prime_receipts = [_receipt_facts(receipt) for receipt in prime.outputs]
    if len(prime_receipts) != 1 or Path(prime_receipts[0]["destination"]).resolve() != output:
        raise RuntimeError("prime request did not produce exactly the required fixture STEP")
    trace_before = _line_count(trace)

    profiler = cProfile.Profile()
    attempts = []
    receipts = []
    started = time.perf_counter()
    profiler.enable()
    try:
        for _index in range(args.iterations):
            result = service.generate_captured(captured)
            attempt = service.last_attempt
            if attempt is None:
                raise RuntimeError("profiled request did not expose a build attempt")
            attempts.append({
                "revision": result.revision_id,
                "sourceSeconds": attempt.source_seconds,
                "evaluations": _closed(attempt.stats),
                "products": _closed(result.product_metrics),
            })
            current = [_receipt_facts(receipt) for receipt in result.outputs]
            if len(current) != 1:
                raise RuntimeError("profiled request did not produce exactly one required STEP")
            receipts.append(current[0])
    finally:
        profiler.disable()
    elapsed = time.perf_counter() - started
    profiler.dump_stats(profile_path)

    trace_after = _line_count(trace)
    if trace_after - trace_before != args.iterations:
        raise RuntimeError("ordinary source did not execute exactly once per profiled request")
    if logical_source.exists():
        raise RuntimeError("captured source was unexpectedly materialized")
    profile_payload = profile_path.read_bytes()
    report = {
        "schema": 1,
        "kind": "warmed-unchanged-program-cprofile-diagnostic",
        "qualification": (
            "cProfile attribution inside the native owner process; excludes DocumentWorker IPC; "
            "profiler overhead makes elapsed values unsuitable for benchmark ratios"
        ),
        "candidateRevision": args.candidate_revision,
        "model": args.model,
        "iterations": args.iterations,
        "entry": {"logicalPath": str(logical_source), "sourcePath": str(source),
                  "sha256": digest, "bytes": len(payload), "materialized": False},
        "runtime": {"python": sys.version, "executable": sys.executable,
                    "cadgen": getattr(cadgen, "__version__", None),
                    "cadgenModule": str(Path(cadgen.__file__).resolve())},
        "prime": {"revision": prime.revision_id,
                  "sourceSeconds": prime_attempt.source_seconds,
                  "evaluations": _closed(prime_attempt.stats),
                  "products": _closed(prime.product_metrics), "receipts": prime_receipts},
        "profiled": {"wallSeconds": elapsed, "wallSecondsPerRequest": elapsed / args.iterations,
                     "sourceTraceExecutions": trace_after - trace_before,
                     "attempts": attempts, "receipts": receipts},
        "profile": {"path": str(profile_path), "sha256": _sha256(profile_payload),
                    "bytes": len(profile_payload),
                    "topCumulative": _profile_rows(profiler, order="cumulative", limit=args.top),
                    "topTotal": _profile_rows(profiler, order="total", limit=args.top)},
    }
    _write_json(args.report.resolve(), report)
    print(json.dumps({"ok": True, "report": str(args.report.resolve()),
                      "profile": str(profile_path), "model": args.model,
                      "iterations": args.iterations, "wallSeconds": elapsed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
