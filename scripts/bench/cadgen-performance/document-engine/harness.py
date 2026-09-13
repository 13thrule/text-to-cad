#!/usr/bin/env python3
"""Bounded, serial P0 benchmark for the proposed retained CAD document engine.

The controller is stdlib-only. Frozen cadgen source is extracted to /private/tmp;
all fixture copies, stores, and CAD outputs stay below models/. Timing never
includes oracle readback, report writing, or daemon cleanup.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import statistics
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from typing import Any


REPO = Path(__file__).resolve().parents[4]
FIXTURES = REPO / "models/performance_document"
DEFAULT_PYTHON = REPO / ".venv/bin/python" if (REPO / ".venv/bin/python").is_file() else Path(sys.executable)
CHECKPOINT = "5c4a212cae32e834fa4d805ae778ab5ee6cd71a2"
OPTIMIZED_CODE = "18cc312ce"
MAIN = "3e4dfdeef2cbd5804c369592b59620132188a150"
OUTPUTS = {"plate": "plate.step", "assembly24": "assembly24.step"}
EXPECTED_OCCURRENCES = {"plate": 1, "assembly24": 24}
GEOMETRY_LINE = "HOLE_RADIUS = 3.0  # BENCH_GEOMETRY"
PLACEMENT_LINE = "PLACEMENT_Z = 0.0  # BENCH_PLACEMENT"
TRACE_SCHEMA = 1
INPROCESS_BOUNDARY_WITH_SETUP = "in-process-run-model-argv-with-first-call-engine-setup-v2"
FULL_REQUEST_BOUNDARY = "captured-entry-to-attested-step-full-request-v1"
FULL_OUTPUT_CONTRACT = "one-required-step-actual-byte-receipt-v1"
FULL_ADAPTER = Path(__file__).resolve().with_name("full_request_adapter.py")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def append_jsonl(path: Path, value: Any) -> None:
    """Durably preserve each completed sample before any later oracle/work."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO, text=True, capture_output=True, check=check)


def resolve_revision(value: str) -> str:
    result = git("rev-parse", f"{value}^{{commit}}")
    return result.stdout.strip()


def require_under(path: Path, parent: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(parent.resolve()):
        raise ValueError(f"{label} must be below {parent.resolve()}: {resolved}")
    return resolved


def line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open(encoding="utf-8") as stream:
        return sum(1 for _ in stream)


def read_trace(path: Path, start: int) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if number <= start:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"malformed document trace {path}:{number}: {exc}") from exc
        if not isinstance(row, dict):
            raise RuntimeError(f"document trace {path}:{number} is not an object")
        schema = row.get("schema")
        if schema is not None and schema != TRACE_SCHEMA:
            raise RuntimeError(f"unsupported document trace schema {schema!r}")
        rows.append(row)
    return rows


def process_rows() -> dict[int, tuple[int, int, str]]:
    completed = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,rss=,command="], text=True,
        capture_output=True, timeout=2, check=False,
    )
    rows: dict[int, tuple[int, int, str]] = {}
    for line in completed.stdout.splitlines():
        fields = line.strip().split(None, 3)
        if len(fields) != 4:
            continue
        try:
            pid, ppid, rss_kib = map(int, fields[:3])
        except ValueError:
            continue
        rows[pid] = (ppid, rss_kib * 1024, fields[3])
    return rows


def descendants(rows: dict[int, tuple[int, int, str]], roots: set[int]) -> set[int]:
    found = set(roots)
    changed = True
    while changed:
        changed = False
        for pid, (parent, _rss, _command) in rows.items():
            if parent in found and pid not in found:
                found.add(pid)
                changed = True
    return found


class RssSampler:
    def __init__(self, root_pid: int):
        self.known = {root_pid}
        self.peak_bytes = 0
        self.peak_processes = 0
        self.samples = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(0.05):
            rows = process_rows()
            self.known |= descendants(rows, self.known)
            live = self.known & rows.keys()
            self.peak_bytes = max(self.peak_bytes, sum(rows[pid][1] for pid in live))
            self.peak_processes = max(self.peak_processes, len(live))
            self.samples += 1

    def start(self) -> None:
        self._thread.start()

    def finish(self) -> dict[str, Any]:
        self._stop.set()
        self._thread.join(timeout=3)
        return {
            "sampledTreePeakRssBytes": self.peak_bytes or None,
            "sampledTreePeakProcesses": self.peak_processes or None,
            "rssSamples": self.samples,
            "qualification": (
                "50 ms ps samples of the command tree, including descendants observed before "
                "daemon detachment; a sampled RSS peak is not an allocator high-water mark"
            ),
        }


def archive_runtime(revision: str, destination: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=False)
    archive = destination.parent / f"{destination.name}.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", "-o", str(archive), revision, "packages/cadgen/src"],
        cwd=REPO, check=True,
    )
    with tarfile.open(archive) as stream:
        root = destination.resolve()
        for member in stream.getmembers():
            target = (destination / member.name).resolve()
            if not target.is_relative_to(root):
                raise RuntimeError(f"unsafe git archive member: {member.name}")
        stream.extractall(destination, filter="data")
    archive.unlink()
    source = destination / "packages/cadgen/src"
    files = [path for path in sorted(source.rglob("*")) if path.is_file()]
    digest = hashlib.sha256()
    for path in files:
        relative = str(path.relative_to(source)).replace(os.sep, "/")
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return {"source": source, "files": len(files), "treeSha256": digest.hexdigest()}


def runtime_metadata(python: Path, package: Path) -> dict[str, Any]:
    code = r'''
import importlib.metadata, json, platform, sys
import cadgen
values = {"python": sys.version, "platform": platform.platform(),
          "cadgen": getattr(cadgen, "__version__", "unknown"),
          "cadgenModule": cadgen.__file__}
for name in ("build123d", "cadquery-ocp", "numpy", "scipy"):
    try: values[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError: values[name] = None
try:
    import OCP
    values["occt"] = getattr(OCP, "OCP_VERSION", None) or getattr(OCP, "__version__", "unknown")
except Exception as exc:
    values["occt"] = "unavailable:" + type(exc).__name__
print("__DOCUMENT_METADATA__" + json.dumps(values, sort_keys=True))
'''
    env = os.environ.copy()
    env.update(PYTHONPATH=str(package), PYTHONDONTWRITEBYTECODE="1", CADGEN_DAEMON="0")
    completed = subprocess.run([str(python), "-c", code], cwd=REPO, env=env,
                               text=True, capture_output=True, timeout=30, check=True)
    line = next(value for value in completed.stdout.splitlines()
                if value.startswith("__DOCUMENT_METADATA__"))
    return json.loads(line.removeprefix("__DOCUMENT_METADATA__"))


def source_variant(original: str, *, geometry: float = 3.0, placement: float = 0.0) -> str:
    if original.count(GEOMETRY_LINE) != 1 or original.count(PLACEMENT_LINE) != 1:
        raise RuntimeError("fixture edit markers changed")
    return original.replace(
        GEOMETRY_LINE, f"HOLE_RADIUS = {geometry:.6f}  # BENCH_GEOMETRY",
    ).replace(
        PLACEMENT_LINE, f"PLACEMENT_Z = {placement:.6f}  # BENCH_PLACEMENT",
    )


def json_events(stdout: str) -> list[dict[str, Any]]:
    rows = []
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def stage_counts(stderr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in json_events(stderr):
        phase = str(row.get("phase") or row.get("state") or "unclassified")
        counts[phase] = counts.get(phase, 0) + 1
    return counts


def daemon_status(python: Path, env: dict[str, str]) -> dict[str, Any]:
    code = "import json; from cadgen.daemon.client import status; print(json.dumps(status() or {}))"
    completed = subprocess.run([str(python), "-c", code], cwd=REPO, env=env,
                               text=True, capture_output=True, timeout=5, check=False)
    try:
        return json.loads(completed.stdout.splitlines()[-1]) if completed.stdout.strip() else {}
    except (json.JSONDecodeError, IndexError):
        return {"statusProbeError": completed.stderr[-1000:]}


def rss_for_pids(pids: list[int]) -> dict[str, Any]:
    rows = process_rows()
    live = [pid for pid in pids if pid in rows]
    return {
        "rssBytes": sum(rows[pid][1] for pid in live),
        "livePids": live,
        "processes": len(live),
    }


def owned_pids(status: dict[str, Any]) -> list[int]:
    values = [status.get("pid")]
    values += [worker.get("pid") for worker in status.get("workers", []) if isinstance(worker, dict)]
    return sorted({int(value) for value in values if isinstance(value, int) and value > 1})


def stop_owned_daemon(python: Path, env: dict[str, str]) -> dict[str, Any]:
    status = daemon_status(python, env)
    pids = owned_pids(status)
    for pid in reversed(pids):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 5.0
    live = pids
    while live and time.monotonic() < deadline:
        time.sleep(0.05)
        rows = process_rows()
        live = [pid for pid in pids if pid in rows]
    killed = []
    for pid in live:
        try:
            os.kill(pid, signal.SIGKILL)
            killed.append(pid)
        except ProcessLookupError:
            pass
    return {
        "privateSocket": env["CADGEN_DAEMON_SOCKET"],
        "ownedPids": pids,
        "sigkillAfterDeadline": killed,
        "cleanedWithinSeconds": not live,
        "deadlineSeconds": 5.0,
    }


def oracle_batch(python: Path, package: Path,
                 requests: list[tuple[Path, Path]]) -> list[dict[str, Any]]:
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(package), "PYTHONDONTWRITEBYTECODE": "1", "CADGEN_DAEMON": "0",
    })
    plan = json.dumps([{"step": str(step), "store": str(store)} for step, store in requests])
    completed = subprocess.run(
        [str(python), str(Path(__file__).resolve()), "_oracle", "--plan", plan],
        cwd=REPO, env=env, text=True, capture_output=True,
        timeout=min(120, 20 * len(requests) + 10), check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"STEP oracle failed: {completed.stderr[-2000:]}")
    line = next((line for line in completed.stdout.splitlines()
                 if line.startswith("__DOCUMENT_ORACLES__")), None)
    if line is None:
        raise RuntimeError(f"STEP oracle emitted no result: {completed.stdout[-1000:]}")
    values = json.loads(line.removeprefix("__DOCUMENT_ORACLES__"))
    if not isinstance(values, list) or len(values) != len(requests):
        raise RuntimeError("STEP oracle result count differs from request count")
    return values


def run_command(*, python: Path, package: Path, model: Path, output: Path,
                env: dict[str, str], trace: Path, source_trace: Path,
                archived_step: Path, timeout: float, label: str,
                sample_rss: bool) -> dict[str, Any]:
    trace_start, source_start = line_count(trace), line_count(source_trace)
    started = time.perf_counter()
    argv = [str(python), str(model), "--json"]
    if os.environ.get("CADGEN_DOCUMENT_BENCH_DEBUG") == "1":
        argv.append("--verbose")
    process = subprocess.Popen(argv, cwd=model.parent, env=env,
                               text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    sampler = RssSampler(process.pid) if sample_rss else None
    if sampler:
        sampler.start()
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        raise RuntimeError(f"{label}: exceeded {timeout:.0f}s command cap")
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    memory = sampler.finish() if sampler else {
        "sampledTreePeakRssBytes": None,
        "sampledTreePeakProcesses": None,
        "rssSamples": 0,
        "qualification": "peak RSS sampling disabled so timing has no ps sampler; use --sample-rss for a separate diagnostic run",
    }
    if process.returncode:
        raise RuntimeError(f"{label}: exit {process.returncode}\n{stdout[-1000:]}\n{stderr[-2000:]}")
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"{label}: declared STEP output was not completed")
    events = json_events(stdout)
    completion_count = sum(row.get("ok") is True for row in events)
    if not completion_count:
        raise RuntimeError(f"{label}: no successful JSON completion event")
    archived_step.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output, archived_step)
    status = daemon_status(python, env)
    pids = owned_pids(status)
    runtime_rows = read_trace(trace, trace_start)
    return {
        "label": label,
        "processExitMs": elapsed_ms,
        "exitCode": process.returncode,
        "stdoutJsonEvents": events,
        "completionEventCount": completion_count,
        "progressStageCounts": stage_counts(stderr),
        "stderrTail": stderr[-2000:],
        "stepBytes": output.stat().st_size,
        "stepSha256": sha256(output),
        "oracleStep": str(archived_step),
        "sourceSideEffectExecutions": line_count(source_trace) - source_start,
        "documentTrace": runtime_rows,
        "documentTraceAvailability": "available" if runtime_rows else "unavailable",
        "memory": {
            **memory,
            "daemonStatus": status,
            "immediateAfterCommand": rss_for_pids(pids),
        },
    }


def assert_close(actual: float, expected: float, context: str) -> None:
    if not math.isclose(actual, expected, rel_tol=1e-8, abs_tol=2e-6):
        raise AssertionError(f"{context}: {actual} != {expected}")


def parts_by_label(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {part["label"]: part for part in value["parts"]}


def validate_oracle(model: str, scenario: str, prime: dict[str, Any], row: dict[str, Any]) -> None:
    expected_count = EXPECTED_OCCURRENCES[model]
    current = row["oracle"]
    if current["occurrences"] != expected_count or not current["valid"]:
        raise AssertionError(f"{model}/{scenario}: invalid occurrence contract")
    before, after = parts_by_label(prime), parts_by_label(current)
    if before.keys() != after.keys():
        raise AssertionError(f"{model}/{scenario}: labels changed")
    if scenario == "unchanged":
        if current != prime or row["stepSha256"] != row["primeStepSha256"]:
            raise AssertionError(f"{model}/unchanged: geometry or STEP bytes changed")
    elif scenario == "local_geometry":
        for label in before:
            if not after[label]["volume"] < before[label]["volume"]:
                raise AssertionError(f"{model}/local_geometry: {label} volume did not decrease")
            if after[label]["bounds"] != before[label]["bounds"]:
                raise AssertionError(f"{model}/local_geometry: {label} bounds changed")
            if after[label]["counts"] != before[label]["counts"]:
                raise AssertionError(f"{model}/local_geometry: {label} topology counts changed")
    elif scenario == "placement":
        target = next(iter(before)) if model == "plate" else "plate_01"
        for label in before:
            assert_close(after[label]["volume"], before[label]["volume"], f"{label}.volume")
            assert_close(after[label]["area"], before[label]["area"], f"{label}.area")
            if after[label]["counts"] != before[label]["counts"]:
                raise AssertionError(f"{model}/placement: {label} topology counts changed")
            if label == target:
                delta = [after[label]["bounds"][corner][2] - before[label]["bounds"][corner][2]
                         for corner in (0, 1)]
                if not all(value > 0 for value in delta):
                    raise AssertionError(f"{model}/placement: target Z bounds did not move")
            elif after[label]["bounds"] != before[label]["bounds"]:
                raise AssertionError(f"{model}/placement: non-target {label} moved")


def session_env(package: Path, root: Path) -> dict[str, str]:
    socket_id = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(package),
        "PYTHONDONTWRITEBYTECODE": "1",
        "CADGEN_CACHE_DIR": str(root / "store"),
        "CADGEN_DAEMON_STATE_DIR": str(root / "daemon-state"),
        # AF_UNIX is capped at roughly 104 bytes on macOS. State and all CAD
        # data remain in the fixture root; only the transport endpoint is short.
        "CADGEN_DAEMON_SOCKET": f"/private/tmp/cadgen-doc-{socket_id}.sock",
        "CADGEN_DAEMON": "1",
        "CADGEN_JOBS": "1",
        "CADGEN_COMPONENT_WORKERS": "1",
        "CADGEN_DAEMON_SPARES": "0",
        "CADGEN_DAEMON_RECYCLE": "1000",
        "CADGEN_DOCUMENT_BENCH_TRACE": str(root / "document-trace.jsonl"),
        "CADGEN_DOCUMENT_BENCH_SOURCE_TRACE": str(root / "source-trace.jsonl"),
    })
    return env


def prepare_model(model: str, root: Path) -> tuple[Path, str, Path]:
    root.mkdir(parents=True, exist_ok=False)
    source = FIXTURES / f"{model}.py"
    original = source.read_text(encoding="utf-8")
    if "@memo" in original or original.count("@step") != 1:
        raise AssertionError(f"{source} must contain exactly one @step and no @memo")
    destination = root / source.name
    destination.write_text(original, encoding="utf-8")
    return destination, original, root / OUTPUTS[model]


def run_session(*, python: Path, package: Path, model: str, scenario: str,
                samples: int, root: Path, timeout: float, measured_cold: bool = False,
                sample_rss: bool = False, journal: Path, cold_index: int = 0) -> dict[str, Any]:
    model_path, original, output = prepare_model(model, root)
    env = session_env(package, root)
    trace, source_trace = Path(env["CADGEN_DOCUMENT_BENCH_TRACE"]), Path(env["CADGEN_DOCUMENT_BENCH_SOURCE_TRACE"])
    rows = []
    prime_row: dict[str, Any] | None = None
    plateau: dict[str, Any] | None = None
    try:
        if measured_cold:
            model_path.write_text(source_variant(original), encoding="utf-8")
            row = run_command(
                python=python, package=package, model=model_path, output=output, env=env,
                trace=trace, source_trace=source_trace,
                archived_step=root / f"oracles/cold-{cold_index}.step",
                timeout=timeout, label=f"{model}/cold/{cold_index}", sample_rss=sample_rss,
            )
            row.update(sample=cold_index, measured=True, sourceSha256=sha256(model_path))
            rows.append(row)
            append_jsonl(journal, {"kind": "sample", "model": model, "scenario": scenario, **row})
        else:
            model_path.write_text(source_variant(original), encoding="utf-8")
            prime_row = run_command(
                python=python, package=package, model=model_path, output=output, env=env,
                trace=trace, source_trace=source_trace, archived_step=root / "oracles/prime.step",
                timeout=timeout, label=f"{model}/{scenario}/prime", sample_rss=sample_rss,
            )
            prime_row.update(sample=None, measured=False, sourceSha256=sha256(model_path))
            append_jsonl(journal, {"kind": "prime", "model": model, "scenario": scenario, **prime_row})
            prime_sha = prime_row["stepSha256"]
            for sample in range(samples):
                geometry = 3.0 + 0.05 * (sample + 1) if scenario == "local_geometry" else 3.0
                placement = 0.5 + 0.25 * sample if scenario == "placement" else 0.0
                model_path.write_text(source_variant(original, geometry=geometry, placement=placement),
                                      encoding="utf-8")
                row = run_command(
                    python=python, package=package, model=model_path, output=output, env=env,
                    trace=trace, source_trace=source_trace,
                    archived_step=root / f"oracles/sample-{sample}.step", timeout=timeout,
                    label=f"{model}/{scenario}/{sample}", sample_rss=sample_rss,
                )
                row.update(sample=sample, measured=True, geometryValue=geometry,
                           placementValue=placement, sourceSha256=sha256(model_path),
                           primeStepSha256=prime_sha)
                rows.append(row)
                append_jsonl(journal, {"kind": "sample", "model": model, "scenario": scenario, **row})
        status = daemon_status(python, env)
        pids = owned_pids(status)
        settled_first = rss_for_pids(pids)
        time.sleep(2.0)
        plateau = {"first": settled_first, "afterTwoSeconds": rss_for_pids(pids),
                   "idleSeconds": 2.0, "daemonStatus": status}
    finally:
        cleanup = stop_owned_daemon(python, env)
        write_json(root / "cleanup.json", cleanup)
    oracle_inputs = ([] if prime_row is None else [
        (Path(prime_row["oracleStep"]), root / "readback-prime"),
    ]) + [(Path(row["oracleStep"]), root / f"readback-{index}") for index, row in enumerate(rows)]
    hidden_source = model_path.with_suffix(".source-hidden")
    os.replace(model_path, hidden_source)
    try:
        descriptions = oracle_batch(python, package, oracle_inputs)
    finally:
        os.replace(hidden_source, model_path)
    if prime_row is None:
        prime = descriptions[0]
        if prime["occurrences"] != EXPECTED_OCCURRENCES[model] or not prime["valid"]:
            raise AssertionError(f"{model}/cold: invalid occurrence contract")
        rows[0]["oracle"] = prime
    else:
        prime = descriptions[0]
        prime_row["oracle"] = prime
        for row, description in zip(rows, descriptions[1:]):
            row["oracle"] = description
            validate_oracle(model, scenario, prime, row)
    for row in rows:
        append_jsonl(journal, {"kind": "oracle", "model": model, "scenario": scenario,
                               "label": row["label"], "stepSha256": row["stepSha256"],
                               "oracle": row["oracle"]})
    return {"model": model, "scenario": scenario, "rows": rows, "primeOracle": prime,
            "prime": prime_row, "settledPlateau": plateau, "cleanup": cleanup,
            "savedDocumentReadbackWithSourceHidden": True}


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row["processExitMs"] for row in rows]
    return {
        "samples": len(values),
        "medianMs": statistics.median(values),
        "observedMinMs": min(values),
        "observedMaxMs": max(values),
        "p95": None,
        "qualification": "median and observed range only; this sample count does not establish p95",
    }


def command_preflight(_args: argparse.Namespace) -> None:
    fixtures = {}
    for name in OUTPUTS:
        path = FIXTURES / f"{name}.py"
        text = path.read_text(encoding="utf-8")
        fixtures[name] = {"path": str(path.relative_to(REPO)), "sha256": sha256(path),
                          "stepDecorators": text.count("@step"), "memoDecorators": text.count("@memo")}
        if fixtures[name]["stepDecorators"] != 1 or fixtures[name]["memoDecorators"]:
            raise AssertionError(f"invalid fixture decorator contract: {path}")
    checkpoint = resolve_revision(CHECKPOINT)
    optimized = resolve_revision(OPTIMIZED_CODE)
    main = resolve_revision(MAIN)
    changed = git("diff", "--name-only", f"{optimized}..{checkpoint}").stdout.splitlines()
    production_roots = ("packages/cadgen/", "packages/cadgen-js/", "apps/viewer/")
    production_changes = [path for path in changed if path.startswith(production_roots)]
    result = {
        "ok": not production_changes,
        "revisions": {"checkpoint": checkpoint, "optimizedCode": optimized, "main": main},
        "checkpointChangesSinceOptimizedCode": changed,
        "productionChangesSinceOptimizedCode": production_changes,
        "fixtures": fixtures,
        "controller": {"python": sys.version, "platform": platform.platform()},
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if production_changes:
        raise SystemExit("checkpoint is not production-code identical to optimized revision")


def candidate_worker(args: argparse.Namespace) -> None:
    """Own one in-process runner; retained and legacy stacks never mix."""
    import contextlib as worker_contextlib
    import dataclasses
    import io
    import resource

    from cadgen.cli._run_model import run_model_argv

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    engine = plan["engine"]
    model, scenario = plan["model"], plan["scenario"]
    source, output = Path(plan["source"]), Path(plan["output"])
    original = source.read_text(encoding="utf-8")
    source_trace, journal = Path(plan["sourceTrace"]), Path(plan["journal"])
    if engine not in {"retained", "legacy"}:
        raise ValueError(f"unknown in-process engine {engine!r}")
    service = None
    engine_ready = False

    def prepare_engine() -> float:
        """Time engine-specific imports/setup once; warm primes pay it unmeasured."""
        nonlocal engine_ready, service
        if engine_ready:
            return 0.0
        started = time.perf_counter()
        if engine == "retained":
            from cadgen._document.service import DocumentService

            service = DocumentService(max_documents=1)
        else:
            # This distinct control process installs only the legacy witness.
            # A retained worker never imports or installs that interception stack.
            from cadgen import memoization

            memoization.install(trusted_worker=True)
        engine_ready = True
        return (time.perf_counter() - started) * 1000.0

    def current_rss() -> int | None:
        row = process_rows().get(os.getpid())
        return row[1] if row else None

    def execute(*, label: str, sample: int | None, measured: bool,
                geometry: float, placement: float, archive: Path) -> dict[str, Any]:
        source.write_text(source_variant(original, geometry=geometry, placement=placement),
                          encoding="utf-8")
        source_start = line_count(source_trace)
        stdout, stderr = io.StringIO(), io.StringIO()
        started = time.perf_counter()
        setup_ms = prepare_engine()
        call_started = time.perf_counter()
        with worker_contextlib.redirect_stdout(stdout), worker_contextlib.redirect_stderr(stderr):
            if engine == "legacy":
                code = run_model_argv([str(source), "--json"])
            else:
                with service.activate():
                    code = run_model_argv([str(source), "--json"])
        call_ms = (time.perf_counter() - call_started) * 1000.0
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        attempt = service.last_attempt if engine == "retained" else None
        if code or (engine == "retained" and (attempt is None or attempt.state != "exports_complete")):
            raise RuntimeError(
                f"{label}: retained run failed code={code}, "
                f"state={getattr(attempt, 'state', None)}\n{stdout.getvalue()[-1000:]}\n"
                f"{stderr.getvalue()[-2000:]}"
            )
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError(f"{label}: explicit STEP completion produced no file")
        events = json_events(stdout.getvalue())
        completion_count = sum(row.get("ok") is True for row in events)
        if completion_count != 1:
            raise RuntimeError(f"{label}: expected one successful completion event, got {completion_count}")
        side_effects = line_count(source_trace) - source_start
        if engine == "retained" and side_effects != 1:
            raise RuntimeError(f"{label}: ordinary Python executed {side_effects} times, expected one")
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output, archive)
        stats = dataclasses.asdict(attempt.stats) if attempt is not None else None
        row = {
            "label": label, "sample": sample, "measured": measured,
            "geometryValue": geometry, "placementValue": placement,
            "processExitMs": elapsed_ms,
            "engineSetupMs": setup_ms,
            "runModelArgvMs": call_ms,
            "sourceGeometryMs": attempt.source_seconds * 1000.0 if attempt is not None else None,
            "geometryCounters": stats,
            "revisionId": attempt.revision.revision_id if attempt is not None else None,
            "explicitExportState": attempt.state if attempt is not None else "completed-file-and-event",
            "requiredExports": list(attempt.required_exports) if attempt is not None else [str(output)],
            "completionEventCount": completion_count,
            "stdoutJsonEvents": events,
            "progressStageCounts": stage_counts(stderr.getvalue()),
            "stderrTail": stderr.getvalue()[-2000:],
            "stepBytes": output.stat().st_size, "stepSha256": sha256(output),
            "oracleStep": str(archive), "sourceSha256": sha256(source),
            "sourceSideEffectExecutions": side_effects,
            "processPeakRssBytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            * (1 if sys.platform == "darwin" else 1024),
        }
        append_jsonl(journal, {"kind": f"{engine}-sample" if measured else f"{engine}-prime",
                               "model": model, "scenario": scenario, **row})
        return row

    rows = []
    prime = None
    if plan["cold"]:
        rows.append(execute(label=f"{model}/cold/{plan['coldIndex']}",
                            sample=plan["coldIndex"], measured=True,
                            geometry=3.0, placement=0.0,
                            archive=Path(plan["root"]) / f"oracles/cold-{plan['coldIndex']}.step"))
    else:
        prime = execute(label=f"{model}/{scenario}/prime", sample=None, measured=False,
                        geometry=3.0, placement=0.0,
                        archive=Path(plan["root"]) / "oracles/prime.step")
        for sample in range(plan["samples"]):
            geometry = 3.0 + 0.05 * (sample + 1) if scenario == "local_geometry" else 3.0
            placement = 0.5 + 0.25 * sample if scenario == "placement" else 0.0
            row = execute(
                label=f"{model}/{scenario}/{sample}", sample=sample, measured=True,
                geometry=geometry, placement=placement,
                archive=Path(plan["root"]) / f"oracles/sample-{sample}.step",
            )
            row["primeStepSha256"] = prime["stepSha256"]
            rows.append(row)
    first = current_rss()
    time.sleep(2.0)
    plateau = {"firstRssBytes": first, "afterTwoSecondsRssBytes": current_rss(),
               "idleSeconds": 2.0}
    write_json(Path(plan["workerReport"]), {
        "rows": rows, "prime": prime, "settledPlateau": plateau,
        "managedService": engine == "retained",
        "legacyRunnerOrOperationMemoInvokedBeforeManagedAttempt": False if engine == "retained" else None,
        "effectiveControls": {
            name: os.environ.get(name) for name in (
                "CADGEN_DAEMON", "CADGEN_OP_MEMO", "CADGEN_OP_MEMO_DISK",
                "CADGEN_MEMO_CACHE", "CADGEN_DETERMINISM",
            )
        },
        "resolvedLegacyCacheDefaults": {
            "operationMemoEnabled": os.environ.get("CADGEN_OP_MEMO", "1") != "0",
            "operationMemoDiskEnabled": os.environ.get("CADGEN_OP_MEMO_DISK", "1") != "0",
            "wholeCallMemoEnabled": os.environ.get("CADGEN_MEMO_CACHE", "1") != "0",
        } if engine == "legacy" else None,
    })


def candidate_session(*, python: Path, package: Path, model: str, scenario: str,
                      samples: int, root: Path, timeout: float, journal: Path,
                      engine: str = "retained", cold: bool = False,
                      cold_index: int = 0) -> dict[str, Any]:
    source, _original, output = prepare_model(model, root)
    worker_report = root / "candidate-worker.json"
    source_trace = root / "source-trace.jsonl"
    plan = {
        "engine": engine, "model": model, "scenario": scenario, "samples": samples, "cold": cold,
        "coldIndex": cold_index, "root": str(root), "source": str(source),
        "output": str(output), "sourceTrace": str(source_trace),
        "journal": str(journal), "workerReport": str(worker_report),
    }
    plan_path = root / "candidate-plan.json"
    write_json(plan_path, plan)
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(package), "PYTHONDONTWRITEBYTECODE": "1",
        "CADGEN_DAEMON": "0", "CADGEN_CACHE_DIR": str(root / "store"),
        "CADGEN_DOCUMENT_BENCH_SOURCE_TRACE": str(source_trace),
    })
    controls = ("CADGEN_OP_MEMO", "CADGEN_OP_MEMO_DISK", "CADGEN_MEMO_CACHE", "CADGEN_DETERMINISM")
    if engine == "retained":
        env.update({name: "0" for name in controls})
    else:
        for name in controls:
            env.pop(name, None)
    completed = subprocess.run(
        [str(python), str(Path(__file__).resolve()), "_candidate_worker", "--plan", str(plan_path)],
        cwd=REPO, env=env, text=True, capture_output=True, timeout=timeout, check=False,
    )
    if completed.returncode or not worker_report.is_file():
        raise RuntimeError(
            f"candidate worker failed ({completed.returncode}):\n"
            f"{completed.stdout[-1000:]}\n{completed.stderr[-3000:]}"
        )
    result = json.loads(worker_report.read_text(encoding="utf-8"))
    rows, prime_row = result["rows"], result["prime"]
    oracle_inputs = ([] if prime_row is None else [
        (Path(prime_row["oracleStep"]), root / "readback-prime"),
    ]) + [(Path(row["oracleStep"]), root / f"readback-{index}") for index, row in enumerate(rows)]
    hidden_source = source.with_suffix(".source-hidden")
    os.replace(source, hidden_source)
    try:
        descriptions = oracle_batch(python, package, oracle_inputs)
    finally:
        os.replace(hidden_source, source)
    if prime_row is None:
        prime = descriptions[0]
        if prime["occurrences"] != EXPECTED_OCCURRENCES[model] or not prime["valid"]:
            raise AssertionError(f"candidate {model}/cold: invalid occurrence contract")
        rows[0]["oracle"] = prime
    else:
        prime = descriptions[0]
        prime_row["oracle"] = prime
        for row, description in zip(rows, descriptions[1:]):
            row["oracle"] = description
            validate_oracle(model, scenario, prime, row)
    for row in rows:
        append_jsonl(journal, {"kind": f"{engine}-oracle", "model": model,
                               "scenario": scenario, "label": row["label"],
                               "stepSha256": row["stepSha256"], "oracle": row["oracle"]})
    return {
        "model": model, "scenario": scenario, "rows": rows, "prime": prime_row,
        "primeOracle": prime, "settledPlateau": result["settledPlateau"],
        "managedService": result["managedService"],
        "legacyRunnerOrOperationMemoInvokedBeforeManagedAttempt": result[
            "legacyRunnerOrOperationMemoInvokedBeforeManagedAttempt"
        ],
        "effectiveControls": result["effectiveControls"],
        "resolvedLegacyCacheDefaults": result["resolvedLegacyCacheDefaults"],
        "workerProcessExited": True, "savedDocumentReadbackWithSourceHidden": True,
    }


def source_tree_record(source: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    files = [path for path in sorted(source.rglob("*"))
             if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"]
    for path in files:
        digest.update(str(path.relative_to(source)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return {"path": str(source), "files": len(files), "treeSha256": digest.hexdigest()}


def candidate_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = summarize(rows)
    source_values = [row["sourceGeometryMs"] for row in rows if row["sourceGeometryMs"] is not None]
    result["sourceGeometryMedianMs"] = statistics.median(source_values) if source_values else None
    result["geometryCounters"] = [row["geometryCounters"] for row in rows]
    return result


def inprocess_report(*, engine: str, python: Path, package: Path,
                     started_revision: str, runtime_archive: dict[str, Any] | None,
                     runtime_before: dict[str, Any], runtime_after: dict[str, Any],
                     models: list[str], scenarios: list[str], sessions: list[dict[str, Any]],
                     cold_samples: int, warm_samples: int, environment_note: str,
                     sample_plan_extra: dict[str, Any] | None = None,
                     execution_order: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build the common retained/legacy report for the matched worker boundary."""
    if runtime_before["treeSha256"] != runtime_after["treeSha256"]:
        raise RuntimeError(f"{engine} runtime source tree changed during in-process benchmark")
    summaries = {
        model: {
            scenario: candidate_summary([
                row for session in sessions if session["model"] == model
                and session["scenario"] == scenario for row in session["rows"]
            ])
            for scenario in ("cold", "unchanged", "local_geometry", "placement")
            if any(session["model"] == model and session["scenario"] == scenario
                   for session in sessions)
        } for model in models
    }
    retained = engine == "retained"
    sample_plan = {
        "coldPerFixture": cold_samples, "warmPerFixtureScenario": warm_samples,
        "models": models, "scenarios": scenarios, "serial": True,
        "coldEngineSetupInsideBoundary": True,
        "commonWorkerBootstrapExcluded": "harness and run_model_argv module imports",
    }
    sample_plan.update(sample_plan_extra or {})
    result = {
        "schema": 1, "outcome": "passed",
        "qualification": (f"{engine}-functional-smoke"
                          if cold_samples < 5 or warm_samples < 10
                          else f"{engine}-bounded-exploratory-series"),
        "percentileEvidence": False,
        "engine": "internal-retained-document-service" if retained else "frozen-legacy-in-process",
        "timingBoundaryKind": INPROCESS_BOUNDARY_WITH_SETUP,
        "environmentNote": environment_note,
        "startedFromRevision": started_revision,
        "runtime": runtime_metadata(python, package),
        "runtimeSourceBefore": runtime_before, "runtimeSourceAfter": runtime_after,
        "runtimeSourceStable": True, "runtimeArchive": runtime_archive,
        "samplePlan": sample_plan,
        "fixtureSources": {name: {"sha256": sha256(FIXTURES / f"{name}.py"),
                                  "path": str((FIXTURES / f"{name}.py").relative_to(REPO))}
                           for name in OUTPUTS},
        "timingBoundary": (
            "cold processExitMs begins before engine-specific import/setup and includes the first full "
            "in-process run_model_argv call through explicit STEP completion; warm processExitMs is the "
            "full run_model_argv call after an unmeasured prime. retained calls run inside "
            "DocumentService.activate; process launch, controller IPC are excluded. engineSetupMs and "
            "runModelArgvMs expose the cold split and sum to processExitMs apart from timer overhead"
        ),
        "counterQualification": (
            "geometryCounters are literal transaction EvaluationStats. computed includes every core "
            "operator evaluation, including rigid transforms and opaque captures, rather than only surface "
            "or boolean modeling. derived_computed/reused cover only document-core derivations and do not "
            "instrument downstream export/viewer mesh work; zero cannot establish end-to-end zero remesh."
        ),
        "coldQualification": (
            "new Python process; timed first call includes DocumentService import/construction and later "
            "native/frontend imports; filesystem cache not flushed" if retained else
            "new Python process; timed first call includes legacy memoization import/witness installation "
            "and its build123d/native imports; filesystem cache not flushed"
        ),
        "warmQualification": (
            "one persistent Python process and DocumentService per scenario; engine setup occurs in the "
            "unmeasured prime and ordinary Python executes once per measured call" if retained else
            "one persistent Python process and operation witness per scenario; engine setup occurs in the "
            "unmeasured prime and legacy freshness behavior is preserved"
        ),
        "sessions": sessions, "summary": summaries,
    }
    if execution_order is not None:
        result["actualChronologicalOrder"] = execution_order
    return result


def _command_inprocess(args: argparse.Namespace, *, engine: str, package: Path,
                       started_revision: str, runtime_archive: dict[str, Any] | None = None) -> None:
    python = Path(os.path.abspath(args.python))
    if not python.is_file():
        raise FileNotFoundError(f"CAD Python not found: {python}")
    scratch = require_under(Path(args.scratch), REPO / "models", "scratch")
    report = Path(args.report).resolve()
    journal = report.with_suffix(report.suffix + ".samples.jsonl")
    args._journal_started = False
    if scratch.exists() or report.exists() or journal.exists():
        raise FileExistsError("in-process scratch, report, and journal must be new paths")
    scratch.mkdir(parents=True)
    append_jsonl(journal, {
        "kind": f"{engine}-run-start", "schema": 1,
        "coldSamples": args.cold_samples, "warmSamples": args.warm_samples,
        "environmentNote": args.environment_note, "qualification": "incomplete-until-final-report",
    })
    args._journal_started = True
    runtime_before = source_tree_record(package)
    models = args.models.split(",") if args.models else list(OUTPUTS)
    scenarios = args.scenarios.split(",") if args.scenarios else [
        "cold", "unchanged", "local_geometry", "placement",
    ]
    if set(models) - OUTPUTS.keys() or set(scenarios) - {"cold", "unchanged", "local_geometry", "placement"}:
        raise ValueError("unknown in-process model or scenario")
    sessions = []
    for model in models:
        for sample in range(args.cold_samples if "cold" in scenarios else 0):
            sessions.append(candidate_session(
                python=python, package=package, model=model, scenario="cold", samples=1,
                root=scratch / model / f"cold-{sample}", timeout=args.timeout,
                journal=journal, engine=engine, cold=True, cold_index=sample,
            ))
        for scenario in ("unchanged", "local_geometry", "placement"):
            if scenario in scenarios:
                sessions.append(candidate_session(
                    python=python, package=package, model=model, scenario=scenario,
                    samples=args.warm_samples, root=scratch / model / scenario,
                    timeout=args.timeout, journal=journal, engine=engine,
                ))
    runtime_after = source_tree_record(package)
    result = inprocess_report(
        engine=engine, python=python, package=package,
        started_revision=started_revision, runtime_archive=runtime_archive,
        runtime_before=runtime_before, runtime_after=runtime_after,
        models=models, scenarios=scenarios, sessions=sessions,
        cold_samples=args.cold_samples, warm_samples=args.warm_samples,
        environment_note=args.environment_note,
        sample_plan_extra={"workerSessionTimeoutSeconds": args.timeout},
    )
    result["rawSampleJournal"] = str(journal)
    write_json(report, result)
    append_jsonl(journal, {"kind": f"{engine}-run-complete", "outcome": "passed",
                           "report": str(report), "finishedAt": time.time()})
    args._journal_started = False
    print(json.dumps({"outcome": "passed", "qualification": result["qualification"],
                      "report": str(report), "summary": result["summary"]}, indent=2))


def command_candidate(args: argparse.Namespace) -> None:
    package = REPO / "packages/cadgen/src"
    _command_inprocess(args, engine="retained", package=package,
                       started_revision=resolve_revision("HEAD"))


def command_legacy_inprocess(args: argparse.Namespace) -> None:
    revision = resolve_revision(args.revision)
    with tempfile.TemporaryDirectory(prefix=f"cadgen-document-inprocess-{revision[:10]}-",
                                     dir="/private/tmp") as temporary:
        archive = Path(temporary) / "runtime"
        archive_record = archive_runtime(revision, archive)
        package = archive_record.pop("source")
        _command_inprocess(args, engine="legacy", package=package,
                           started_revision=revision, runtime_archive=archive_record)


def paired_plan(models: list[str], scenarios: list[str], cold_samples: int
                ) -> list[dict[str, Any]]:
    """Alternate first engine for each cold sample or complete warm session."""
    units = []
    pair_ordinal = 0
    for model in models:
        if "cold" in scenarios:
            for sample in range(cold_samples):
                order = (("legacy", "retained") if pair_ordinal % 2 == 0
                         else ("retained", "legacy"))
                units.append({"pairOrdinal": pair_ordinal, "model": model,
                              "scenario": "cold", "coldIndex": sample,
                              "engineOrder": order})
                pair_ordinal += 1
        for scenario in ("unchanged", "local_geometry", "placement"):
            if scenario not in scenarios:
                continue
            order = (("legacy", "retained") if pair_ordinal % 2 == 0
                     else ("retained", "legacy"))
            units.append({"pairOrdinal": pair_ordinal, "model": model,
                          "scenario": scenario, "coldIndex": None,
                          "engineOrder": order})
            pair_ordinal += 1
    return units


def full_request_session(*, python: Path, engine_package: Path, readback_package: Path,
                         engine: str, model: str, scenario: str, samples: int,
                         root: Path, timeout: float, journal: Path, cold: bool = False,
                         cold_index: int = 0) -> dict[str, Any]:
    """Run one full captured-entry session through an attested STEP response."""
    root.mkdir(parents=True, exist_ok=False)
    original_path = FIXTURES / f"{model}.py"
    original = original_path.read_text(encoding="utf-8")
    if "@memo" in original or original.count("@step") != 1:
        raise AssertionError(f"invalid full-request fixture: {original_path}")
    source = root / original_path.name
    output = root / OUTPUTS[model]
    source_trace = root / "source-trace.jsonl"
    accepted = root / "accepted-inputs"
    accepted.mkdir()
    requests: list[dict[str, Any]] = []

    def add_request(*, label: str, sample: int | None, measured: bool,
                    geometry: float, placement: float, name: str) -> None:
        payload = source_variant(original, geometry=geometry, placement=placement).encode("utf-8")
        # A transport buffer is not an importable source path. The logical
        # model path is absent (current) or hidden (legacy) during readback.
        capture = accepted / f"{name}.buffer"
        capture.write_bytes(payload)
        requests.append({
            "label": label, "sample": sample, "measured": measured,
            "geometryValue": geometry, "placementValue": placement,
            "input": str(capture), "digest": sha256_bytes(payload), "bytes": len(payload),
            "archive": str(root / "oracles" / f"{name}.step"),
        })

    if cold:
        add_request(label=f"{model}/cold/{cold_index}", sample=cold_index, measured=True,
                    geometry=3.0, placement=0.0, name=f"cold-{cold_index}")
    else:
        add_request(label=f"{model}/{scenario}/prime", sample=None, measured=False,
                    geometry=3.0, placement=0.0, name="prime")
        for sample in range(samples):
            geometry = 3.0 + 0.05 * (sample + 1) if scenario == "local_geometry" else 3.0
            placement = 0.5 + 0.25 * sample if scenario == "placement" else 0.0
            add_request(label=f"{model}/{scenario}/{sample}", sample=sample, measured=True,
                        geometry=geometry, placement=placement, name=f"sample-{sample}")

    worker_report = root / "full-adapter-report.json"
    plan = {
        "engine": engine, "model": model, "scenario": scenario, "cold": cold,
        "source": str(source), "output": str(output), "sourceTrace": str(source_trace),
        "ownerRoot": str(root / "document-owner"), "workerReport": str(worker_report),
        "journal": str(journal), "requests": requests,
        "startupTimeout": min(60.0, timeout), "requestTimeout": min(60.0, timeout),
        "cancellationGrace": 2.0,
    }
    plan_path = root / "full-request-plan.json"
    write_json(plan_path, plan)
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(engine_package), "PYTHONDONTWRITEBYTECODE": "1",
        "CADGEN_DAEMON": "0", "CADGEN_CACHE_DIR": str(root / "legacy-store"),
        "CADGEN_DOCUMENT_BENCH_SOURCE_TRACE": str(source_trace),
    })
    # Frozen legacy receives its production defaults. The direct document
    # worker has no dependency on these removed controls; clearing inherited
    # values keeps author-visible input equal across both adapters.
    for name in ("CADGEN_OP_MEMO", "CADGEN_OP_MEMO_DISK", "CADGEN_MEMO_CACHE",
                 "CADGEN_DETERMINISM"):
        env.pop(name, None)
    env["CADGEN_FULL_REQUEST_STARTED_NS"] = str(time.perf_counter_ns())
    completed = subprocess.run(
        [str(python), str(FULL_ADAPTER), "--plan", str(plan_path)],
        cwd=REPO, env=env, text=True, capture_output=True, timeout=timeout, check=False,
    )
    if completed.returncode or not worker_report.is_file():
        raise RuntimeError(
            f"full-request {engine} adapter failed ({completed.returncode}):\n"
            f"{completed.stdout[-1000:]}\n{completed.stderr[-3000:]}"
        )
    adapter = json.loads(worker_report.read_text(encoding="utf-8"))
    rows = [row for row in adapter["rows"] if row["measured"]]
    prime_row = next((row for row in adapter["rows"] if not row["measured"]), None)
    expected_rows = 1 if cold else samples
    if len(rows) != expected_rows:
        raise RuntimeError("full-request adapter returned the wrong measured sample count")

    oracle_rows = ([] if prime_row is None else [prime_row]) + rows
    oracle_inputs = [
        (Path(row["oracleStep"]), root / "independent-readback" / f"item-{index}")
        for index, row in enumerate(oracle_rows)
    ]
    hidden = None
    if source.exists():
        hidden = source.with_suffix(".source-hidden")
        os.replace(source, hidden)
    readback_started = time.perf_counter()
    try:
        descriptions = oracle_batch(python, readback_package, oracle_inputs)
    finally:
        saved_readback_ms = (time.perf_counter() - readback_started) * 1000.0
        if hidden is not None:
            os.replace(hidden, source)
    if prime_row is None:
        prime = descriptions[0]
        if prime["occurrences"] != EXPECTED_OCCURRENCES[model] or not prime["valid"]:
            raise AssertionError(f"full-request {engine} {model}/cold failed saved-byte oracle")
        rows[0]["oracle"] = prime
    else:
        prime = descriptions[0]
        prime_row["oracle"] = prime
        for row, description in zip(rows, descriptions[1:]):
            row["oracle"] = description
            validate_oracle(model, scenario, prime, row)
    for row in rows:
        append_jsonl(journal, {
            "kind": f"full-{engine}-oracle", "model": model, "scenario": scenario,
            "label": row["label"], "stepSha256": row["stepSha256"],
            "oracle": row["oracle"],
        })
    return {
        "model": model, "scenario": scenario, "rows": rows, "prime": prime_row,
        "primeOracle": prime, "residentDisplay": adapter["residentDisplay"],
        "cleanup": adapter["cleanup"], "effectiveControls": adapter["effectiveControls"],
        "resolvedLegacyCacheDefaults": adapter["resolvedLegacyCacheDefaults"],
        "inputCapture": {
            "scope": "exact-entry-buffer-only",
            "qualification": (
                "the entry was captured before adapter dispatch; any helper or managed-data inputs "
                "would be captured only when consumed and this single-file fixture consumed none"
            ),
            "requests": [{"path": value["input"], "digest": value["digest"],
                          "bytes": value["bytes"]} for value in requests],
        },
        "independentSavedByteReadback": {
            "outsideFullRequestTiming": True, "sourceHidden": True,
            "commonRuntime": str(readback_package), "items": len(oracle_inputs),
            "batchMs": saved_readback_ms,
            "qualification": (
                "one common actual-saved-byte parser validates geometry after the request; batch time "
                "includes its subprocess setup and is reported separately, never subtracted or ratioed"
            ),
        },
        "workerProcessExited": adapter["cleanup"]["ownerExitedAfterSession"],
    }


def full_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row["fullRequestMs"] for row in rows]
    result = {
        "samples": len(values), "medianMs": statistics.median(values),
        "observedMinMs": min(values), "observedMaxMs": max(values),
        "p95": None,
        "qualification": "median and observed range only; this sample count does not establish p95",
    }
    stages = {}
    for field in ("acceptedBufferReadHashMs", "engineSetupMs", "adapterWriteMs", "engineRequestMs",
                  "actualByteVerificationMs", "ownerRequestMs", "sourceGeometryMs"):
        values = [row[field] for row in rows if row.get(field) is not None]
        stages[field.removesuffix("Ms") + "MedianMs"] = (
            statistics.median(values) if values else None
        )
    result["stages"] = stages
    result["geometryCounters"] = [row.get("geometryCounters") for row in rows]
    result["productCounters"] = [row.get("productCounters") for row in rows]
    return result


def full_request_report(*, engine: str, python: Path, package: Path,
                        started_revision: str, runtime_archive: dict[str, Any] | None,
                        runtime_before: dict[str, Any], runtime_after: dict[str, Any],
                        models: list[str], scenarios: list[str], sessions: list[dict[str, Any]],
                        cold_samples: int, warm_samples: int, environment_note: str,
                        chronology: list[dict[str, Any]], cold_timeout: float,
                        warm_timeout: float) -> dict[str, Any]:
    if runtime_before["treeSha256"] != runtime_after["treeSha256"]:
        raise RuntimeError(f"{engine} runtime source tree changed during full-request benchmark")
    summaries = {
        model: {
            scenario: full_summary([
                row for session in sessions if session["model"] == model
                and session["scenario"] == scenario for row in session["rows"]
            ])
            for scenario in ("cold", "unchanged", "local_geometry", "placement")
            if any(session["model"] == model and session["scenario"] == scenario
                   for session in sessions)
        } for model in models
    }
    retained = engine == "retained"
    complete = cold_samples == 5 and warm_samples == 10
    return {
        "schema": 1, "outcome": "passed",
        "qualification": (f"{engine}-full-request-bounded-series" if complete
                          else f"{engine}-full-request-functional-smoke"),
        "percentileEvidence": False,
        "engine": ("current-direct-document-worker" if retained
                   else "frozen-legacy-benchmark-materialization-adapter"),
        "timingBoundaryKind": FULL_REQUEST_BOUNDARY,
        "fullRequestOutputContract": FULL_OUTPUT_CONTRACT,
        "environmentNote": environment_note,
        "startedFromRevision": started_revision,
        "runtime": runtime_metadata(python, package),
        "runtimeSourceBefore": runtime_before, "runtimeSourceAfter": runtime_after,
        "runtimeSourceStable": True, "runtimeArchive": runtime_archive,
        "benchmarkAdapter": {"path": str(FULL_ADAPTER.relative_to(REPO)),
                             "sha256": sha256(FULL_ADAPTER)},
        "inputDelivery": ({
            "kind": "captured-entry-worker-payload",
            "qualification": "current worker executes the exact entry bytes accepted before dispatch",
        } if retained else {
            "kind": "benchmark-adapter-materialized-entry",
            "qualification": (
                "the adapter writes the exact accepted entry bytes immediately before the frozen old "
                "runner; this changes the old path-only door semantics and is not a compatibility API"
            ),
        }),
        "samplePlan": {
            "coldPerFixture": cold_samples, "warmPerFixtureScenario": warm_samples,
            "models": models, "scenarios": scenarios, "serial": True, "paired": True,
            "pairingUnit": "one cold sample or one complete warm scenario adapter",
            "alternatingFirstEngine": True,
            "coldAdapterTimeoutSeconds": cold_timeout,
            "warmAdapterTimeoutSeconds": warm_timeout,
            "coldProcessAndEngineSetupInsideBoundary": True,
            "warmPrimeUnmeasured": True,
            "singleFileExactEntryCapture": True,
        },
        "fixtureSources": {name: {
            "sha256": sha256(FIXTURES / f"{name}.py"),
            "path": str((FIXTURES / f"{name}.py").relative_to(REPO)),
        } for name in OUTPUTS},
        "timingBoundary": (
            "fullRequestMs begins before a cold adapter process launch or, for warm rows, immediately "
            "before input delivery inside a primed persistent adapter. It ends only after source and "
            "native work, the one required STEP publication, and an actual destination byte/hash check. "
            "Cold includes adapter bootstrap and engine setup. Frozen legacy's adapter materialization "
            "is included and also exposed as adapterWriteMs; candidate includes DocumentWorker IPC. "
            "Archive copying, resident display, lease release/shutdown, independent saved-byte readback, "
            "geometry oracle, report writing and controller chronology are excluded."
        ),
        "stageQualification": (
            "acceptedBufferReadHashMs is inside cold fullRequestMs because cold starts before adapter "
            "launch, and outside warm fullRequestMs because warm starts after that exact buffer is read. "
            "adapterWriteMs is separately reported and remains inside fullRequestMs. engineRequestMs is "
            "an engine-door interval, not a kernel-only measurement. No stage is subtracted to create a "
            "synthetic headline, and no resident-display/saved-reopen ratio is produced."
        ),
        "inputQualification": (
            "only the exact single-file entry buffer is captured before dispatch. SourceSession records "
            "helpers or managed data when actually consumed; this fixture has none and the report makes "
            "no atomic whole-project snapshot claim."
        ),
        "savedByteQualification": (
            "requestVerification checks the actual destination bytes before fullRequestMs ends. A second, "
            "common current-runtime parser reads archived actual bytes with source hidden after timing; "
            "that independent geometry oracle and its batch time are separate from request verification."
        ),
        "counterQualification": (
            "candidate evaluation/product counters are literal internal observations. Frozen legacy has "
            "no equivalent counters. Aggregates do not establish zero modeling or end-to-end zero remesh."
        ),
        "legacyCacheQualification": (
            "frozen legacy installs its trusted operation witness and runs with production-default "
            "operation, disk, and whole-call caches enabled; every session reports resolved defaults"
            if not retained else
            "the direct document worker does not invoke the removed legacy memo/store pipeline"
        ),
        "historicalBoundaryRelationship": (
            "the prior in-process paired series remains valid evidence for its own obsolete development "
            "bridge boundary; its distinct versioned identifier makes it timing-incomparable here"
        ),
        "actualChronologicalOrder": chronology,
        "executionOrderQualification": (
            "controller timestamps establish order only; elapsedControllerMs includes excluded oracle and "
            "session cleanup work and is not timing evidence"
        ),
        "sessions": sessions, "summary": summaries,
    }


def full_request_dispatch(*, series_id: str, dispatch_ordinal: int,
                          unit: dict[str, Any], position: int, engine: str,
                          python: Path, engine_package: Path, readback_package: Path,
                          root: Path, journal: Path, samples: int,
                          timeout: float) -> tuple[dict[str, Any], dict[str, Any]]:
    cold = unit["scenario"] == "cold"
    dispatch = {
        "seriesId": series_id, "dispatchOrdinal": dispatch_ordinal,
        "pairOrdinal": unit["pairOrdinal"], "positionInPair": position,
        "firstEngine": unit["engineOrder"][0], "engine": engine,
        "model": unit["model"], "scenario": unit["scenario"],
        "coldIndex": unit["coldIndex"], "startedAt": time.time(),
    }
    append_jsonl(journal, {"kind": "full-paired-dispatch-start", **dispatch})
    started = time.perf_counter()
    try:
        session = full_request_session(
            python=python, engine_package=engine_package,
            readback_package=readback_package, engine=engine,
            model=unit["model"], scenario=unit["scenario"],
            samples=1 if cold else samples, root=root, timeout=timeout,
            journal=journal, cold=cold, cold_index=unit["coldIndex"] or 0,
        )
    except BaseException as error:
        append_jsonl(journal, {"kind": "full-paired-dispatch-failed", **dispatch,
                               "error": str(error), "finishedAt": time.time()})
        raise
    labels = ([] if session["prime"] is None else [session["prime"]["label"]])
    labels.extend(row["label"] for row in session["rows"])
    entry = {
        **dispatch, "finishedAt": time.time(),
        "elapsedControllerMs": (time.perf_counter() - started) * 1000.0,
        "adapterExecutionOrder": labels,
        "workerProcessExited": session["workerProcessExited"],
    }
    session["pairedDispatchOrdinal"] = dispatch_ordinal
    session["pairedPairOrdinal"] = unit["pairOrdinal"]
    append_jsonl(journal, {"kind": "full-paired-dispatch-complete", **entry})
    return session, entry


def command_full_paired(args: argparse.Namespace) -> None:
    """Compare frozen and current full requests at one captured-entry boundary."""
    python = Path(os.path.abspath(args.python))
    if not python.is_file():
        raise FileNotFoundError(f"CAD Python not found: {python}")
    if not FULL_ADAPTER.is_file():
        raise FileNotFoundError(f"full-request adapter not found: {FULL_ADAPTER}")
    scratch = require_under(Path(args.scratch), REPO / "models", "scratch")
    reports = {
        "legacy": Path(args.baseline_report).resolve(),
        "retained": Path(args.candidate_report).resolve(),
    }
    comparison = Path(args.comparison_report).resolve()
    journals = {engine: report.with_suffix(report.suffix + ".samples.jsonl")
                for engine, report in reports.items()}
    if any(path.exists() for path in (scratch, comparison, *reports.values(), *journals.values())):
        raise FileExistsError("full-paired scratch, reports, comparison, and journals must be new paths")
    models = args.models.split(",") if args.models else list(OUTPUTS)
    scenarios = args.scenarios.split(",") if args.scenarios else [
        "cold", "unchanged", "local_geometry", "placement",
    ]
    if (set(models) - OUTPUTS.keys()
            or set(scenarios) - {"cold", "unchanged", "local_geometry", "placement"}):
        raise ValueError("unknown full-paired model or scenario")
    scratch.mkdir(parents=True)
    baseline_revision = resolve_revision(args.baseline_revision)
    candidate_revision = resolve_revision("HEAD")
    series_id = f"full-paired-{time.time_ns()}"
    for engine, journal in journals.items():
        append_jsonl(journal, {
            "kind": f"full-{engine}-paired-run-start", "schema": 1,
            "seriesId": series_id, "timingBoundaryKind": FULL_REQUEST_BOUNDARY,
            "coldSamples": args.cold_samples, "warmSamples": args.warm_samples,
            "environmentNote": args.environment_note,
            "qualification": "incomplete-until-final-report", "startedAt": time.time(),
        })
    chronology: list[dict[str, Any]] = []
    sessions: dict[str, list[dict[str, Any]]] = {"legacy": [], "retained": []}
    adapter_digest = sha256(FULL_ADAPTER)
    try:
        with tempfile.TemporaryDirectory(
                prefix=f"cadgen-document-full-paired-{baseline_revision[:10]}-",
                dir="/private/tmp") as temporary:
            baseline_archive = Path(temporary) / "baseline-runtime"
            baseline_archive_record = archive_runtime(baseline_revision, baseline_archive)
            baseline_package = baseline_archive_record.pop("source")
            candidate_archive = Path(temporary) / "candidate-runtime"
            candidate_archive_record = archive_runtime(candidate_revision, candidate_archive)
            candidate_package = candidate_archive_record.pop("source")
            packages = {"legacy": baseline_package, "retained": candidate_package}
            runtime_before = {engine: source_tree_record(package)
                              for engine, package in packages.items()}
            for unit in paired_plan(models, scenarios, args.cold_samples):
                cold = unit["scenario"] == "cold"
                for position, engine in enumerate(unit["engineOrder"]):
                    leaf = f"cold-{unit['coldIndex']}" if cold else unit["scenario"]
                    session, entry = full_request_dispatch(
                        series_id=series_id, dispatch_ordinal=len(chronology), unit=unit,
                        position=position, engine=engine, python=python,
                        engine_package=packages[engine], readback_package=candidate_package,
                        root=scratch / engine / unit["model"] / leaf,
                        journal=journals[engine], samples=args.warm_samples,
                        timeout=args.cold_timeout if cold else args.warm_timeout,
                    )
                    sessions[engine].append(session)
                    chronology.append(entry)
            runtime_after = {engine: source_tree_record(package)
                             for engine, package in packages.items()}
            candidate_head_after = resolve_revision("HEAD")
            if sha256(FULL_ADAPTER) != adapter_digest:
                raise RuntimeError("full-request benchmark adapter changed during the series")
            built = {
                engine: full_request_report(
                    engine=engine, python=python, package=packages[engine],
                    started_revision=(baseline_revision if engine == "legacy"
                                      else candidate_revision),
                    runtime_archive=(baseline_archive_record if engine == "legacy"
                                     else candidate_archive_record),
                    runtime_before=runtime_before[engine], runtime_after=runtime_after[engine],
                    models=models, scenarios=scenarios, sessions=sessions[engine],
                    cold_samples=args.cold_samples, warm_samples=args.warm_samples,
                    environment_note=args.environment_note, chronology=chronology,
                    cold_timeout=args.cold_timeout, warm_timeout=args.warm_timeout,
                ) for engine in ("legacy", "retained")
            }
            for engine, report_value in built.items():
                report_value["pairedSeriesId"] = series_id
                report_value["rawSampleJournal"] = str(journals[engine])
                report_value["candidateHeadAtArchive"] = candidate_revision
                report_value["candidateHeadAfterSeries"] = candidate_head_after
                report_value["candidateHeadMovedAfterArchive"] = (
                    candidate_head_after != candidate_revision
                )
                report_value["controllerArgv"] = [sys.executable, str(Path(__file__).resolve()),
                                                  *sys.argv[1:]]
                write_json(reports[engine], report_value)
                append_jsonl(journals[engine], {
                    "kind": f"full-{engine}-paired-run-complete", "outcome": "passed",
                    "seriesId": series_id, "report": str(reports[engine]),
                    "finishedAt": time.time(),
                })
        command_compare(argparse.Namespace(
            baseline=str(reports["legacy"]), candidate=str(reports["retained"]),
            report=str(comparison),
        ))
        compared = json.loads(comparison.read_text(encoding="utf-8"))
        compared["pairedSeriesId"] = series_id
        compared["actualChronologicalOrder"] = chronology
        compared["displayTimingComparable"] = False
        compared["displayTimingQualification"] = (
            "candidate pinned-resident display and common saved-byte readback are separate diagnostics; "
            "no resident-scene/saved-reopen ratio is defined"
        )
        write_json(comparison, compared)
    except BaseException as error:
        for engine, journal in journals.items():
            append_jsonl(journal, {
                "kind": f"full-{engine}-paired-run-incomplete", "outcome": "incomplete",
                "seriesId": series_id, "error": str(error), "finishedAt": time.time(),
            })
        raise
    print(json.dumps({
        "outcome": "passed", "seriesId": series_id,
        "baselineReport": str(reports["legacy"]),
        "candidateReport": str(reports["retained"]),
        "comparisonReport": str(comparison),
    }, indent=2))


def paired_dispatch(*, series_id: str, dispatch_ordinal: int, unit: dict[str, Any],
                    position: int, engine: str, python: Path, package: Path,
                    root: Path, journal: Path, samples: int, timeout: float
                    ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one existing worker session and record its actual controller order."""
    cold = unit["scenario"] == "cold"
    dispatch = {
        "seriesId": series_id, "dispatchOrdinal": dispatch_ordinal,
        "pairOrdinal": unit["pairOrdinal"], "positionInPair": position,
        "firstEngine": unit["engineOrder"][0], "engine": engine,
        "model": unit["model"], "scenario": unit["scenario"],
        "coldIndex": unit["coldIndex"], "startedAt": time.time(),
    }
    append_jsonl(journal, {"kind": "paired-dispatch-start", **dispatch})
    started = time.perf_counter()
    try:
        session = candidate_session(
            python=python, package=package, model=unit["model"],
            scenario=unit["scenario"], samples=samples, root=root,
            timeout=timeout, journal=journal, engine=engine, cold=cold,
            cold_index=unit["coldIndex"] or 0,
        )
    except BaseException as exc:
        append_jsonl(journal, {"kind": "paired-dispatch-failed", **dispatch,
                               "error": str(exc), "finishedAt": time.time()})
        raise
    labels = ([] if session["prime"] is None else [session["prime"]["label"]])
    labels.extend(row["label"] for row in session["rows"])
    entry = {
        **dispatch, "finishedAt": time.time(),
        "elapsedControllerMs": (time.perf_counter() - started) * 1000.0,
        "workerExecutionOrder": labels,
        "workerProcessExited": session["workerProcessExited"],
    }
    session["pairedDispatchOrdinal"] = dispatch_ordinal
    session["pairedPairOrdinal"] = unit["pairOrdinal"]
    append_jsonl(journal, {"kind": "paired-dispatch-complete", **entry})
    return session, entry


def command_paired(args: argparse.Namespace) -> None:
    """Run matched legacy/retained sessions in an alternating paired schedule."""
    python = Path(os.path.abspath(args.python))
    if not python.is_file():
        raise FileNotFoundError(f"CAD Python not found: {python}")
    scratch = require_under(Path(args.scratch), REPO / "models", "scratch")
    reports = {
        "legacy": Path(args.baseline_report).resolve(),
        "retained": Path(args.candidate_report).resolve(),
    }
    comparison = Path(args.comparison_report).resolve()
    journals = {engine: report.with_suffix(report.suffix + ".samples.jsonl")
                for engine, report in reports.items()}
    if any(path.exists() for path in (scratch, comparison, *reports.values(), *journals.values())):
        raise FileExistsError("paired scratch, reports, comparison, and journals must be new paths")
    models = args.models.split(",") if args.models else list(OUTPUTS)
    scenarios = args.scenarios.split(",") if args.scenarios else [
        "cold", "unchanged", "local_geometry", "placement",
    ]
    if (set(models) - OUTPUTS.keys()
            or set(scenarios) - {"cold", "unchanged", "local_geometry", "placement"}):
        raise ValueError("unknown paired model or scenario")
    scratch.mkdir(parents=True)
    baseline_revision = resolve_revision(args.baseline_revision)
    candidate_revision = resolve_revision("HEAD")
    series_id = f"paired-{time.time_ns()}"
    for engine, journal in journals.items():
        append_jsonl(journal, {
            "kind": f"{engine}-paired-run-start", "schema": 1,
            "seriesId": series_id, "coldSamples": args.cold_samples,
            "warmSamples": args.warm_samples, "environmentNote": args.environment_note,
            "qualification": "incomplete-until-final-report", "startedAt": time.time(),
        })
    chronology = []
    sessions = {"legacy": [], "retained": []}
    try:
        with tempfile.TemporaryDirectory(
                prefix=f"cadgen-document-paired-{baseline_revision[:10]}-",
                dir="/private/tmp") as temporary:
            archive = Path(temporary) / "runtime"
            archive_record = archive_runtime(baseline_revision, archive)
            baseline_package = archive_record.pop("source")
            packages = {"legacy": baseline_package,
                        "retained": REPO / "packages/cadgen/src"}
            runtime_before = {engine: source_tree_record(package)
                              for engine, package in packages.items()}
            schedule = paired_plan(models, scenarios, args.cold_samples)
            for unit in schedule:
                cold = unit["scenario"] == "cold"
                for position, engine in enumerate(unit["engineOrder"]):
                    leaf = (f"cold-{unit['coldIndex']}" if cold else unit["scenario"])
                    session, entry = paired_dispatch(
                        series_id=series_id, dispatch_ordinal=len(chronology),
                        unit=unit, position=position, engine=engine,
                        python=python, package=packages[engine],
                        root=scratch / engine / unit["model"] / leaf,
                        journal=journals[engine], samples=1 if cold else args.warm_samples,
                        timeout=args.cold_timeout if cold else args.warm_timeout,
                    )
                    sessions[engine].append(session)
                    chronology.append(entry)
            runtime_after = {engine: source_tree_record(package)
                             for engine, package in packages.items()}
            plan_extra = {
                "paired": True,
                "pairingUnit": "one cold sample or one complete warm scenario worker",
                "alternatingFirstEngine": True,
                "coldWorkerTimeoutSeconds": args.cold_timeout,
                "warmWorkerTimeoutSeconds": args.warm_timeout,
                "publicCliProcessLaunchExcluded": True,
                "controllerElapsedIsTimingEvidence": False,
            }
            built = {
                "legacy": inprocess_report(
                    engine="legacy", python=python, package=packages["legacy"],
                    started_revision=baseline_revision, runtime_archive=archive_record,
                    runtime_before=runtime_before["legacy"],
                    runtime_after=runtime_after["legacy"],
                    models=models, scenarios=scenarios, sessions=sessions["legacy"],
                    cold_samples=args.cold_samples, warm_samples=args.warm_samples,
                    environment_note=args.environment_note,
                    sample_plan_extra=plan_extra, execution_order=chronology,
                ),
                "retained": inprocess_report(
                    engine="retained", python=python, package=packages["retained"],
                    started_revision=candidate_revision, runtime_archive=None,
                    runtime_before=runtime_before["retained"],
                    runtime_after=runtime_after["retained"],
                    models=models, scenarios=scenarios, sessions=sessions["retained"],
                    cold_samples=args.cold_samples, warm_samples=args.warm_samples,
                    environment_note=args.environment_note,
                    sample_plan_extra=plan_extra, execution_order=chronology,
                ),
            }
            for engine, result in built.items():
                result["pairedSeriesId"] = series_id
                result["rawSampleJournal"] = str(journals[engine])
                result["executionOrderQualification"] = (
                    "controller timestamps and workerExecutionOrder establish chronology only; "
                    "elapsedControllerMs includes launch, all session samples, oracle and settled-RSS work"
                )
                write_json(reports[engine], result)
                append_jsonl(journals[engine], {
                    "kind": f"{engine}-paired-run-complete", "outcome": "passed",
                    "seriesId": series_id, "report": str(reports[engine]),
                    "finishedAt": time.time(),
                })
        command_compare(argparse.Namespace(
            baseline=str(reports["legacy"]), candidate=str(reports["retained"]),
            report=str(comparison),
        ))
        compared = json.loads(comparison.read_text(encoding="utf-8"))
        compared["pairedSeriesId"] = series_id
        compared["actualChronologicalOrder"] = chronology
        compared["executionOrderQualification"] = built["retained"]["executionOrderQualification"]
        write_json(comparison, compared)
    except BaseException as exc:
        for engine, journal in journals.items():
            append_jsonl(journal, {
                "kind": f"{engine}-paired-run-incomplete", "outcome": "incomplete",
                "seriesId": series_id, "error": str(exc), "finishedAt": time.time(),
            })
        raise
    print(json.dumps({"outcome": "passed", "seriesId": series_id,
                      "baselineReport": str(reports["legacy"]),
                      "candidateReport": str(reports["retained"]),
                      "comparisonReport": str(comparison)}, indent=2))


def command_run(args: argparse.Namespace) -> None:
    # Do not resolve the venv launcher symlink: executing the base interpreter
    # path bypasses pyvenv.cfg and silently drops the CAD environment's OCP.
    python = Path(os.path.abspath(args.python))
    if not python.is_file():
        raise FileNotFoundError(f"CAD Python not found: {python}")
    revision = resolve_revision(args.revision)
    scratch = require_under(Path(args.scratch), REPO / "models", "scratch")
    report = Path(args.report).resolve()
    journal = report.with_suffix(report.suffix + ".samples.jsonl")
    args._journal_started = False
    if scratch.exists():
        raise FileExistsError(f"refusing to overwrite scratch directory: {scratch}")
    if report.exists():
        raise FileExistsError(f"refusing to overwrite report: {report}")
    if journal.exists():
        raise FileExistsError(f"refusing to overwrite raw sample journal: {journal}")
    scratch.mkdir(parents=True)
    append_jsonl(journal, {
        "kind": "run-start", "schema": 1, "requestedRevision": args.revision,
        "coldSamples": args.cold_samples, "warmSamples": args.warm_samples,
        "startedAt": time.time(), "qualification": "incomplete-until-final-report",
        "environmentNote": args.environment_note,
    })
    args._journal_started = True
    runtime_context = (
        contextlib.nullcontext(str(require_under(Path(args.runtime_directory), Path("/private/tmp"),
                                                 "runtime directory").parent))
        if args.runtime_directory else
        tempfile.TemporaryDirectory(prefix=f"cadgen-document-{revision[:10]}-", dir="/private/tmp")
    )
    with runtime_context as temp:
        archive = Path(args.runtime_directory).resolve() if args.runtime_directory else Path(temp) / "runtime"
        archive_record = archive_runtime(revision, archive)
        package = archive_record.pop("source")
        metadata = runtime_metadata(python, package)
        selected_models = args.models.split(",") if args.models else list(OUTPUTS)
        selected_scenarios = args.scenarios.split(",") if args.scenarios else [
            "cold", "unchanged", "local_geometry", "placement",
        ]
        unknown_models = set(selected_models) - OUTPUTS.keys()
        unknown_scenarios = set(selected_scenarios) - {"cold", "unchanged", "local_geometry", "placement"}
        if unknown_models or unknown_scenarios:
            raise ValueError(f"unknown model/scenario: {sorted(unknown_models)}, {sorted(unknown_scenarios)}")
        sessions = []
        for model in selected_models:
            for sample in range(args.cold_samples if "cold" in selected_scenarios else 0):
                session = run_session(
                    python=python, package=package, model=model, scenario="cold", samples=1,
                    root=scratch / model / f"cold-{sample}", timeout=args.timeout,
                    measured_cold=True, sample_rss=args.sample_rss, journal=journal,
                    cold_index=sample,
                )
                sessions.append(session)
            for scenario in ("unchanged", "local_geometry", "placement"):
                if scenario not in selected_scenarios:
                    continue
                sessions.append(run_session(
                    python=python, package=package, model=model, scenario=scenario,
                    samples=args.warm_samples, root=scratch / model / scenario,
                    timeout=args.timeout, sample_rss=args.sample_rss, journal=journal,
                ))
        summaries = {}
        for model in selected_models:
            summaries[model] = {}
            for scenario in ("cold", "unchanged", "local_geometry", "placement"):
                rows = [row for session in sessions if session["model"] == model
                        and session["scenario"] == scenario for row in session["rows"]]
                if rows:
                    summaries[model][scenario] = summarize(rows)
        smoke = args.cold_samples < 5 or args.warm_samples < 10
        result = {
            "schema": 1,
            "outcome": "passed",
            "qualification": "functional-smoke" if smoke else "bounded-exploratory-series",
            "percentileEvidence": False,
            "environmentNote": args.environment_note,
            "timingBoundaryKind": "source-cli-process",
            "startedFromRevision": revision,
            "requestedRevision": args.revision,
            "frozenReferences": {"checkpoint": CHECKPOINT, "optimizedCode": OPTIMIZED_CODE, "main": MAIN},
            "samplePlan": {"coldPerFixture": args.cold_samples,
                           "warmPerFixtureScenario": args.warm_samples,
                           "models": selected_models, "scenarios": selected_scenarios,
                           "serial": True, "commandTimeoutSeconds": args.timeout,
                           "peakRssSampling": args.sample_rss},
            "runtime": metadata,
            "runtimeArchive": archive_record,
            "fixtureSources": {name: {"sha256": sha256(FIXTURES / f"{name}.py"),
                                      "path": str((FIXTURES / f"{name}.py").relative_to(REPO))}
                               for name in OUTPUTS},
            "timingBoundary": (
                "wall clock immediately before spawning python MODEL --json through actual process exit; "
                "includes dispatch, geometry, declared STEP save and required verification; independent "
                "oracle, 2 s settled-RSS observation, report write and owned-daemon cleanup excluded"
            ),
            "coldQualification": (
                "new private daemon, worker, store and model copy; filesystem cache not flushed"
            ),
            "sessions": sessions,
            "summary": summaries,
            "rawSampleJournal": str(journal),
        }
        write_json(report, result)
        append_jsonl(journal, {"kind": "run-complete", "outcome": "passed",
                               "report": str(report), "finishedAt": time.time()})
        args._journal_started = False
    print(json.dumps({"outcome": "passed", "qualification": result["qualification"],
                      "report": str(report), "summary": result["summary"]}, indent=2))


def measured_rows(report: dict[str, Any]) -> dict[tuple[str, str, int], dict[str, Any]]:
    rows: dict[tuple[str, str, int], dict[str, Any]] = {}
    for session in report["sessions"]:
        for row in session["rows"]:
            key = (session["model"], session["scenario"], int(row["sample"]))
            if key in rows:
                raise AssertionError(f"duplicate measured row {key}")
            rows[key] = row
    return rows


def assert_oracle_parity(left: dict[str, Any], right: dict[str, Any], context: str) -> None:
    if left["occurrences"] != right["occurrences"] or left["valid"] != right["valid"]:
        raise AssertionError(f"{context}: occurrence/validity mismatch")
    left_parts, right_parts = parts_by_label(left), parts_by_label(right)
    if left_parts.keys() != right_parts.keys():
        raise AssertionError(f"{context}: label mismatch")
    for label in left_parts:
        before, after = left_parts[label], right_parts[label]
        if before["counts"] != after["counts"] or before["valid"] != after["valid"]:
            raise AssertionError(f"{context}/{label}: topology mismatch")
        assert_close(after["volume"], before["volume"], f"{context}/{label}.volume")
        assert_close(after["area"], before["area"], f"{context}/{label}.area")
        for corner in (0, 1):
            for axis in range(3):
                assert_close(after["bounds"][corner][axis], before["bounds"][corner][axis],
                             f"{context}/{label}.bounds[{corner}][{axis}]")


def command_compare(args: argparse.Namespace) -> None:
    baseline_path, candidate_path = Path(args.baseline).resolve(), Path(args.candidate).resolve()
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if baseline.get("outcome") != "passed" or candidate.get("outcome") != "passed":
        raise AssertionError("comparison requires two complete passing reports")
    for field in ("coldPerFixture", "warmPerFixtureScenario"):
        if baseline["samplePlan"].get(field) != candidate["samplePlan"].get(field):
            raise AssertionError("comparison sample counts differ")
    selected_models = candidate["samplePlan"]["models"]
    selected_scenarios = candidate["samplePlan"]["scenarios"]
    if not set(selected_models).issubset(baseline["samplePlan"]["models"]):
        raise AssertionError("candidate models are absent from baseline")
    if not set(selected_scenarios).issubset(baseline["samplePlan"]["scenarios"]):
        raise AssertionError("candidate scenarios are absent from baseline")
    for model in selected_models:
        if baseline["fixtureSources"][model]["sha256"] != candidate["fixtureSources"][model]["sha256"]:
            raise AssertionError(f"fixture source differs for {model}")
    baseline_rows, candidate_rows = measured_rows(baseline), measured_rows(candidate)
    baseline_rows = {
        key: row for key, row in baseline_rows.items()
        if key[0] in selected_models and key[1] in selected_scenarios
    }
    if baseline_rows.keys() != candidate_rows.keys():
        raise AssertionError("comparison measured rows differ")
    row_parity = []
    for key in sorted(baseline_rows):
        before, after = baseline_rows[key], candidate_rows[key]
        if (baseline.get("timingBoundaryKind") == FULL_REQUEST_BOUNDARY
                and candidate.get("timingBoundaryKind") == FULL_REQUEST_BOUNDARY):
            if before.get("acceptedEntry", {}).get("digest") != after.get("acceptedEntry", {}).get("digest"):
                raise AssertionError(f"{'/'.join(map(str, key))}: accepted entry bytes differ")
            for engine, row in (("baseline", before), ("candidate", after)):
                verification = row.get("requestVerification", {})
                if (verification.get("requiredStepPresent") is not True
                        or verification.get("actualDestinationSha256") != row.get("stepSha256")
                        or verification.get("actualDestinationBytes") != row.get("stepBytes")):
                    raise AssertionError(f"{'/'.join(map(str, key))}: {engine} request is not byte-attested")
        assert_oracle_parity(before["oracle"], after["oracle"], "/".join(map(str, key)))
        row_parity.append({
            "model": key[0], "scenario": key[1], "sample": key[2],
            "geometryParity": True,
            "stepBytesIdentical": before["stepSha256"] == after["stepSha256"],
        })
    full_contract_comparable = True
    if (baseline.get("timingBoundaryKind") == FULL_REQUEST_BOUNDARY
            or candidate.get("timingBoundaryKind") == FULL_REQUEST_BOUNDARY):
        full_contract_comparable = (
            baseline.get("fullRequestOutputContract") == FULL_OUTPUT_CONTRACT
            and candidate.get("fullRequestOutputContract") == FULL_OUTPUT_CONTRACT
            and all(report.get("runtimeSourceStable") is True
                    for report in (baseline, candidate))
            and all(session.get("independentSavedByteReadback", {}).get(
                        "outsideFullRequestTiming") is True
                    and session.get("independentSavedByteReadback", {}).get("sourceHidden") is True
                    for report in (baseline, candidate) for session in report.get("sessions", ()))
        )
    timing_comparable = (
        baseline.get("timingBoundaryKind") == candidate.get("timingBoundaryKind")
        and baseline.get("timingBoundaryKind") is not None
        and full_contract_comparable
        and all("noncomparable" not in value.get("environmentNote", "").lower()
                for value in (baseline, candidate))
    )
    ratios = None
    if timing_comparable:
        ratios = {}
        for model in selected_models:
            scenarios = baseline["summary"][model]
            ratios[model] = {}
            for scenario, summary in scenarios.items():
                if scenario not in selected_scenarios:
                    continue
                candidate_median = candidate["summary"][model][scenario]["medianMs"]
                ratios[model][scenario] = {
                    "baselineMedianMs": summary["medianMs"],
                    "candidateMedianMs": candidate_median,
                    "candidateOverBaseline": candidate_median / summary["medianMs"],
                }
    result = {
        "schema": 1, "outcome": "passed", "qualification": "cross-revision-oracle-parity",
        "percentileEvidence": False,
        "baseline": {"path": str(baseline_path), "revision": baseline["startedFromRevision"]},
        "candidate": {"path": str(candidate_path), "revision": candidate["startedFromRevision"]},
        "timingComparable": timing_comparable,
        "fullRequestContractComparable": (full_contract_comparable
                                           if FULL_REQUEST_BOUNDARY in {
                                               baseline.get("timingBoundaryKind"),
                                               candidate.get("timingBoundaryKind")}
                                           else None),
        "timingBoundaryKind": baseline.get("timingBoundaryKind") if timing_comparable else None,
        "timingQualification": (
            ("matching full-request boundaries, exact accepted entry bytes, required STEP actual-byte "
             "receipts, and timing-qualified environments; frozen adapter materialization remains "
             "inside its headline and is reported separately"
             if baseline.get("timingBoundaryKind") == FULL_REQUEST_BOUNDARY else
             f"matching {baseline.get('timingBoundaryKind')} boundaries and timing-qualified environments")
            if timing_comparable else
            "timing ratios withheld: boundary kinds differ or a source report marks timings noncomparable"
        ),
        "rows": row_parity, "medianRatios": ratios,
    }
    report = Path(args.report).resolve()
    if report.exists():
        raise FileExistsError(f"refusing to overwrite comparison: {report}")
    write_json(report, result)
    print(json.dumps({"outcome": "passed", "report": str(report),
                      "medianRatios": ratios}, indent=2))


def describe_step_root(root: Any) -> dict[str, Any]:
    """Normalize exact imported geometry without relying on store identities."""
    children = list(root.children)
    parts = children if children else [root]
    descriptions = []
    for index, part in enumerate(parts):
        bounds = part.bounding_box()
        label = str(part.label or ("drilled_plate" if len(parts) == 1 else f"part_{index + 1}"))
        values = {
            "label": label,
            "volume": float(part.volume),
            "area": float(part.area),
            "bounds": [list(map(float, bounds.min)), list(map(float, bounds.max))],
            "counts": {"solids": len(part.solids()), "faces": len(part.faces()),
                       "edges": len(part.edges()), "vertices": len(part.vertices())},
            "valid": bool(part.is_valid),
        }
        finite = [values["volume"], values["area"],
                  *values["bounds"][0], *values["bounds"][1]]
        if not all(math.isfinite(value) for value in finite):
            raise AssertionError(f"non-finite geometry oracle for {label}")
        if values["counts"]["solids"] != 1 or not values["valid"]:
            raise AssertionError(f"invalid/non-solid occurrence {label}")
        descriptions.append(values)
    return {"rootLabel": str(root.label or ""), "occurrences": len(parts),
            "valid": all(part["valid"] for part in descriptions), "parts": descriptions}


def command_oracle(args: argparse.Namespace) -> None:
    from cadgen.step_scene import read_step

    plan = json.loads(args.plan)
    values = []
    for request in plan:
        os.environ["CADGEN_CACHE_DIR"] = str(Path(request["store"]).resolve())
        root = read_step(str(Path(request["step"]).resolve()))
        values.append(describe_step_root(root))
    print("__DOCUMENT_ORACLES__" + json.dumps(values, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight", help="verify frozen revisions and fixture invariants")
    preflight.set_defaults(function=command_preflight)
    run = commands.add_parser("run", help="run one frozen revision serially")
    run.add_argument("--revision", required=True)
    run.add_argument("--python", default=str(DEFAULT_PYTHON))
    run.add_argument("--cold-samples", type=int, default=1)
    run.add_argument("--warm-samples", type=int, default=2)
    run.add_argument("--timeout", type=float, default=60.0)
    run.add_argument("--models", help="comma-separated subset: plate,assembly24")
    run.add_argument("--scenarios", help="comma-separated subset: cold,unchanged,local_geometry,placement")
    run.add_argument("--sample-rss", action="store_true",
                     help="poll ps during commands; use in a separate memory diagnostic, not timing series")
    run.add_argument("--environment-note", default="reserved serial native-compute window",
                     help="host-activity qualification stored verbatim in the report")
    run.add_argument("--scratch", required=True)
    run.add_argument("--report", required=True)
    run.add_argument("--runtime-directory",
                     help="optional new code-only archive directory below /private/tmp; retained for debugging")
    run.set_defaults(function=command_run)
    candidate = commands.add_parser(
        "candidate", help="benchmark the internal retained DocumentService in worker processes",
    )
    candidate.add_argument("--python", default=str(DEFAULT_PYTHON))
    candidate.add_argument("--cold-samples", type=int, default=1)
    candidate.add_argument("--warm-samples", type=int, default=2)
    candidate.add_argument("--timeout", type=float, default=120.0,
                           help="cap for one cold command or one persistent warm scenario worker")
    candidate.add_argument("--models", help="comma-separated subset: plate,assembly24")
    candidate.add_argument("--scenarios", help="comma-separated subset: cold,unchanged,local_geometry,placement")
    candidate.add_argument("--environment-note", default="reserved serial native-compute window")
    candidate.add_argument("--scratch", required=True)
    candidate.add_argument("--report", required=True)
    candidate.set_defaults(function=command_candidate)
    legacy = commands.add_parser(
        "legacy-inprocess", help="run frozen legacy code on the matched in-process boundary",
    )
    legacy.add_argument("--revision", required=True)
    legacy.add_argument("--python", default=str(DEFAULT_PYTHON))
    legacy.add_argument("--cold-samples", type=int, default=1)
    legacy.add_argument("--warm-samples", type=int, default=2)
    legacy.add_argument("--timeout", type=float, default=120.0)
    legacy.add_argument("--models", help="comma-separated subset: plate,assembly24")
    legacy.add_argument("--scenarios", help="comma-separated subset: cold,unchanged,local_geometry,placement")
    legacy.add_argument("--environment-note", default="reserved serial native-compute window")
    legacy.add_argument("--scratch", required=True)
    legacy.add_argument("--report", required=True)
    legacy.set_defaults(function=command_legacy_inprocess)
    paired = commands.add_parser(
        "paired", help="run alternating matched legacy and retained in-process sessions",
    )
    paired.add_argument("--baseline-revision", default=CHECKPOINT)
    paired.add_argument("--python", default=str(DEFAULT_PYTHON))
    paired.add_argument("--cold-samples", type=int, default=5)
    paired.add_argument("--warm-samples", type=int, default=10)
    paired.add_argument("--cold-timeout", type=float, default=60.0)
    paired.add_argument("--warm-timeout", type=float, default=120.0)
    paired.add_argument("--models", help="comma-separated subset: plate,assembly24")
    paired.add_argument(
        "--scenarios",
        help="comma-separated subset: cold,unchanged,local_geometry,placement",
    )
    paired.add_argument(
        "--environment-note", default="reserved serial paired native-compute window",
    )
    paired.add_argument("--scratch", required=True)
    paired.add_argument("--baseline-report", required=True)
    paired.add_argument("--candidate-report", required=True)
    paired.add_argument("--comparison-report", required=True)
    paired.set_defaults(function=command_paired)
    full_paired = commands.add_parser(
        "full-paired",
        help="run frozen and current complete captured-entry requests in alternating order",
    )
    full_paired.add_argument("--baseline-revision", default=CHECKPOINT)
    full_paired.add_argument("--python", default=str(DEFAULT_PYTHON))
    full_paired.add_argument("--cold-samples", type=int, default=5)
    full_paired.add_argument("--warm-samples", type=int, default=10)
    full_paired.add_argument("--cold-timeout", type=float, default=60.0)
    full_paired.add_argument("--warm-timeout", type=float, default=120.0)
    full_paired.add_argument("--models", help="comma-separated subset: plate,assembly24")
    full_paired.add_argument(
        "--scenarios",
        help="comma-separated subset: cold,unchanged,local_geometry,placement",
    )
    full_paired.add_argument(
        "--environment-note", default="reserved serial full-request native-compute window",
    )
    full_paired.add_argument("--scratch", required=True)
    full_paired.add_argument("--baseline-report", required=True)
    full_paired.add_argument("--candidate-report", required=True)
    full_paired.add_argument("--comparison-report", required=True)
    full_paired.set_defaults(function=command_full_paired)
    compare = commands.add_parser("compare", help="check complete reports for geometry parity")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--report", required=True)
    compare.set_defaults(function=command_compare)
    hidden = commands.add_parser("_oracle")
    hidden.add_argument("--plan", required=True)
    hidden.set_defaults(function=command_oracle)
    candidate_worker_parser = commands.add_parser("_candidate_worker")
    candidate_worker_parser.add_argument("--plan", required=True)
    candidate_worker_parser.set_defaults(function=candidate_worker)
    return result


def main() -> None:
    args = parser().parse_args()
    if hasattr(args, "cold_samples"):
        if not 1 <= args.cold_samples <= 5:
            raise SystemExit("--cold-samples must be 1..5")
        if not 1 <= args.warm_samples <= 10:
            raise SystemExit("--warm-samples must be 1..10")
        if args.command in {"paired", "full-paired"}:
            if not 1 <= args.cold_timeout <= 60:
                raise SystemExit("--cold-timeout must be 1..60 seconds")
            if not 1 <= args.warm_timeout <= 120:
                raise SystemExit("--warm-timeout must be 1..120 seconds")
        else:
            timeout_limit = 60 if args.command == "run" else 300
            if not 1 <= args.timeout <= timeout_limit:
                raise SystemExit(f"--timeout must be 1..{timeout_limit} seconds")
    try:
        args.function(args)
    except BaseException as exc:
        # A final aggregate is deliberately all-or-nothing, but completed
        # sample records must survive a timeout, failed oracle, or interrupt.
        if (args.command in {"run", "candidate", "legacy-inprocess"}
                and getattr(args, "report", None)
                and getattr(args, "_journal_started", False)):
            journal = Path(args.report).resolve().with_suffix(Path(args.report).suffix + ".samples.jsonl")
            if journal.is_file():
                append_jsonl(journal, {
                    "kind": "run-incomplete", "outcome": "incomplete",
                    "errorType": type(exc).__name__, "error": str(exc),
                    "finishedAt": time.time(),
                })
        raise


if __name__ == "__main__":
    main()
