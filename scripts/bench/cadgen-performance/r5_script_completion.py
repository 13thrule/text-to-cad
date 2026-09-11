#!/usr/bin/env python3
"""Bounded public-CLI check for discarded top-level model returns.

This compares one frozen candidate package with an otherwise identical private
package whose ``cadgen/authoring.py`` is taken from the pre-change revision.
It measures process start through exit for ordinary ``python model.py --json``
calls.  The model files and their STEP outputs live under ``models/``; package
copies, daemon state and logs belong under ``/private/tmp``.

Preparation is deliberately non-executing.  Use ``--prepare-only`` before a
source freeze; use ``--run`` only after a reviewer releases the native slot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO / "models/tmp/r5-script-completion"
RESULT = REPO / "scripts/bench/cadgen-performance/results/r5-script-completion-20260911.json"
BASELINE_REVISION = "4406d16148f617cbd1b5bf12a5c34f2da4e84add"
BASELINE_AUTHORING = Path("/private/tmp/cadgen-r5-authoring-4406d1614.py")
BASELINE_PACKAGE = Path("/private/tmp/cadgen-r5-baseline-package-4406d1614")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args: str) -> str:
    try:
        return subprocess.check_output(args, cwd=REPO, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def require_under_models(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to((REPO / "models").resolve()):
        raise ValueError("all CAD fixtures and outputs must live under models/")
    return resolved


def copy_baseline(candidate: Path, destination: Path, authoring: Path) -> Path:
    """Copy the frozen candidate source, replacing exactly authoring.py."""
    candidate, destination, authoring = candidate.resolve(), destination.resolve(), authoring.resolve()
    if not (candidate / "cadgen/authoring.py").is_file():
        raise ValueError(f"candidate must be a cadgen source root, got {candidate}")
    if not authoring.is_file():
        raise ValueError(f"missing baseline authoring file: {authoring}")
    if not destination.exists():
        shutil.copytree(candidate, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copyfile(authoring, destination / "cadgen/authoring.py")
    verify_baseline_copy(candidate, destination, authoring)
    return destination


def python_tree_identity(root: Path) -> tuple[str, dict[str, str]]:
    """Stable identity for the package's Python payload, excluding bytecode."""
    files = {str(path.relative_to(root)): sha256(path) for path in sorted(root.rglob("*.py"))
             if "__pycache__" not in path.parts}
    digest = hashlib.sha256()
    for relative, payload in sorted(files.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(payload.encode("ascii"))
    return digest.hexdigest(), files


def verify_baseline_copy(candidate: Path, baseline: Path, authoring: Path) -> dict[str, Any]:
    """The private baseline must differ from frozen candidate source only at authoring.py."""
    candidate_identity, candidate_files = python_tree_identity(candidate)
    baseline_identity, baseline_files = python_tree_identity(baseline)
    expected_difference = "cadgen/authoring.py"
    if set(candidate_files) != set(baseline_files):
        raise ValueError("baseline Python file set does not match candidate")
    changed = [relative for relative in candidate_files if candidate_files[relative] != baseline_files[relative]]
    if changed != [expected_difference]:
        raise ValueError(f"baseline must differ only at {expected_difference}, got {changed}")
    if baseline_files[expected_difference] != sha256(authoring):
        raise ValueError("baseline authoring.py does not match the requested revision")
    matching = {relative: payload for relative, payload in candidate_files.items() if relative != expected_difference}
    matching_digest = hashlib.sha256()
    for relative, payload in sorted(matching.items()):
        matching_digest.update(relative.encode("utf-8"))
        matching_digest.update(payload.encode("ascii"))
    return {
        "pythonFiles": len(candidate_files),
        "matchingFilesExceptAuthoring": len(matching),
        "matchingPythonSha256ExceptAuthoring": matching_digest.hexdigest(),
        "candidatePythonTreeSha256": candidate_identity,
        "baselinePythonTreeSha256": baseline_identity,
    }


def source_text(*, count: int, placement: int, nonce: str, used_return: bool) -> str:
    """A real-file model whose only source difference is an explicit nonce/placement."""
    invoke = """value = build_fixture()
if value is None:
    raise AssertionError("assigned model result was None")
volume = float(value.volume)
solids = len(value.solids())
if volume <= 0 or solids != COUNT:
    raise AssertionError(f"unexpected used result: volume={volume}, solids={solids}")
""" if used_return else "build_fixture()\nvolume = None\nsolids = None\n"
    return f'''# Generated by r5_script_completion.py; nonce makes model freshness explicit.
import json
import os
import sys
from cadgen import step

COUNT = {count}
REQUEST_NONCE = {nonce!r}

@step(out="fixture.step")
def build_fixture():
    from cadgen import build123d as bd
    return bd.Compound(children=[
        bd.Pos(index * 17 + {placement}, (index % 3) * 11, 0) * bd.Box(10, 8, 6)
        for index in range(COUNT)
    ])

if __name__ == "__main__":
    if os.environ.get("R5_GUARD_CALLER_KERNEL") == "1":
        class _BlockCallerKernel:
            def find_spec(self, fullname, _path=None, _target=None):
                if fullname == "build123d" or fullname == "OCP" or fullname.startswith("OCP."):
                    raise AssertionError("discarded bare return imported kernel in caller: " + fullname)
                return None

        for _loaded in list(sys.modules):
            if _loaded == "build123d" or _loaded == "OCP" or _loaded.startswith("OCP."):
                sys.modules.pop(_loaded, None)
        sys.meta_path.insert(0, _BlockCallerKernel())
    {invoke.rstrip().replace(chr(10), chr(10) + '    ')}
    caller_modules = sorted(name for name in sys.modules if name == "build123d" or name == "OCP" or name.startswith("OCP."))
    print("__R5_CALLER__" + json.dumps({{
        "nonce": REQUEST_NONCE,
        "usedReturn": {used_return!r},
        "volume": volume,
        "solids": solids,
        "callerKernelModules": caller_modules,
    }}, sort_keys=True))
'''


def write_model(directory: Path, *, count: int, placement: int, nonce: str, used_return: bool) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    model = directory / "model.py"
    model.write_text(source_text(count=count, placement=placement, nonce=nonce,
                                 used_return=used_return), encoding="utf-8")
    return model


def environment(*, package: Path, state: Path, store: Path, socket: Path,
                guard_kernel: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(package),
        "CADGEN_CACHE_DIR": str(store),
        "CADGEN_DAEMON_STATE_DIR": str(state),
        "CADGEN_DAEMON_SOCKET": str(socket),
        "CADGEN_DAEMON": "1",
        "CADGEN_JOBS": "1",
        "CADGEN_COMPONENT_WORKERS": "1",
        "CADGEN_DAEMON_SPARES": "0",
        "CADGEN_DAEMON_RECYCLE": "100",
    })
    if guard_kernel:
        env["R5_GUARD_CALLER_KERNEL"] = "1"
    else:
        env.pop("R5_GUARD_CALLER_KERNEL", None)
    return env


def marker_from(stdout: str) -> dict[str, Any]:
    lines = [line[len("__R5_CALLER__"):] for line in stdout.splitlines() if line.startswith("__R5_CALLER__")]
    if len(lines) != 1:
        raise RuntimeError(f"expected one caller marker, got {len(lines)}")
    return json.loads(lines[0])


def event_summary(stdout: str) -> dict[str, int]:
    events = []
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return {
        "jsonLines": len(events),
        "sourceResultEvents": sum(bool(value.get("sourceResult")) for value in events),
        "previewEvents": sum(bool(value.get("preview")) for value in events),
    }


def run_model(*, python: str, package: Path, state: Path, store: Path, fixture: Path,
              timeout: float, label: str, guard_kernel: bool) -> dict[str, Any]:
    env = environment(package=package, state=state, store=store, socket=state / "daemon.sock",
                      guard_kernel=guard_kernel)
    started = time.perf_counter()
    completed = subprocess.run([python, str(fixture), "--json"], cwd=fixture.parent, env=env,
                               text=True, capture_output=True, timeout=timeout)
    process_exit_ms = (time.perf_counter() - started) * 1000
    step = fixture.with_name("fixture.step")
    if completed.returncode != 0:
        raise RuntimeError(f"{label}: model failed ({completed.returncode}): {completed.stderr[-2000:]}")
    if not step.is_file() or step.stat().st_size == 0:
        raise RuntimeError(f"{label}: declared STEP output was not completed")
    return {
        "label": label,
        "processExitMs": process_exit_ms,
        "returncode": completed.returncode,
        "stepBytes": step.stat().st_size,
        "stepSha256": sha256(step),
        "caller": marker_from(completed.stdout),
        "events": event_summary(completed.stdout),
    }


def prime_document(*, python: str, package: Path, state: Path, store: Path, fixture: Path, timeout: float,
                   label: str, guard_kernel: bool) -> dict[str, Any]:
    """Warm the worker and create the exact source-revision document before timing."""
    run = run_model(python=python, package=package, state=state, store=store, fixture=fixture,
                    timeout=timeout, label=label + " model prime", guard_kernel=guard_kernel)
    # The source program's successful output receipt is the exact document
    # prime for this source revision. A later nonce-bearing revision is left
    # unprimed on purpose, so its normal freshness gate cannot skip the edit.
    return {"model": run, "documentSha256": run["stepSha256"], "documentBytes": run["stepBytes"]}


def no_kernel_in_caller(row: dict[str, Any]) -> None:
    if row["caller"]["callerKernelModules"]:
        raise RuntimeError(f"discarded bare call imported a caller kernel: {row['caller']['callerKernelModules']}")


def baseline_materializes(row: dict[str, Any]) -> None:
    if not row["caller"]["callerKernelModules"]:
        raise RuntimeError("baseline bare call did not materialize a caller kernel")


def used_return_imports_kernel(row: dict[str, Any], *, count: int) -> None:
    caller = row["caller"]
    if caller["solids"] != count or not caller["volume"] or not caller["callerKernelModules"]:
        raise RuntimeError(f"used-return control did not materialize real geometry: {caller}")


def stop_own_daemon(*, python: str, package: Path, state: Path, store: Path) -> None:
    """Ask only the state-specific private daemon to exit; ignore an already-gone daemon."""
    env = environment(package=package, state=state, store=store, socket=state / "daemon.sock")
    subprocess.run([python, "-m", "cadgen.cli", "daemon", "stop"], cwd=REPO, env=env,
                   text=True, capture_output=True, timeout=10, check=False)


def prepare_manifest(*, candidate: Path, baseline: Path, result: Path) -> dict[str, Any]:
    return {
        "status": "prepared-not-run",
        "baselineRevision": BASELINE_REVISION,
        "baselineAuthoring": str(BASELINE_AUTHORING),
        "baselineAuthoringSha256": sha256(BASELINE_AUTHORING),
        "candidatePackage": str(candidate),
        "candidateAuthoringSha256": sha256(candidate / "cadgen/authoring.py"),
        "baselinePackage": str(baseline),
        "baselineCopy": verify_baseline_copy(candidate, baseline, BASELINE_AUTHORING),
        "fixtureRoot": str(FIXTURE_ROOT),
        "plannedTimedPublicCalls": 8,
        "plannedControls": ["candidate bare call guarded against caller build123d/OCP imports",
                            "candidate assigned return checks real volume and solid count"],
        "boundary": "No model command has run. --run is required after frozen-source release.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--candidate-package", type=Path, default=REPO / "packages/cadgen/src")
    parser.add_argument("--baseline-package", type=Path, default=BASELINE_PACKAGE)
    parser.add_argument("--baseline-authoring", type=Path, default=BASELINE_AUTHORING)
    parser.add_argument("--fixture-root", type=Path, default=FIXTURE_ROOT)
    parser.add_argument("--result", type=Path, default=RESULT)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    if args.prepare_only == args.run:
        raise SystemExit("Choose exactly one of --prepare-only or --run.")
    if not 1 <= args.timeout <= 120:
        raise SystemExit("This bounded check permits a timeout from 1 to 120 seconds.")
    candidate = args.candidate_package.resolve()
    baseline = copy_baseline(candidate, args.baseline_package, args.baseline_authoring)
    baseline_copy = verify_baseline_copy(candidate, baseline, args.baseline_authoring)
    fixture_root = require_under_models(args.fixture_root)
    result = args.result.resolve()
    if args.prepare_only:
        manifest = prepare_manifest(candidate=candidate, baseline=baseline, result=result)
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2))
        return

    started = time.monotonic()
    state_root = Path(f"/private/tmp/cadgen-r5-script-completion-state-{time.time_ns()}")
    variants = {
        "baseline": {"package": baseline, "state": state_root / "baseline/state", "store": state_root / "baseline/store"},
        "candidate": {"package": candidate, "state": state_root / "candidate/state", "store": state_root / "candidate/store"},
    }
    rows: list[dict[str, Any]] = []
    controls: dict[str, Any] = {}
    def remaining() -> float:
        value = args.timeout - (time.monotonic() - started)
        if value <= 0:
            raise TimeoutError(f"R5 check exceeded its {args.timeout}-second wall-clock limit")
        return value

    try:
        # The assigned control uses fresh source/daemon state. It establishes that a
        # consumed result still materializes native geometry in the initiating process.
        control_dir = fixture_root / "used-return-control"
        control = write_model(control_dir, count=2, placement=0, nonce="used-return-control", used_return=True)
        control_state = state_root / "used-return/state"
        control_store = state_root / "used-return/store"
        controls["candidateUsedReturn"] = run_model(python=args.python, package=candidate,
            state=control_state, store=control_store, fixture=control,
            timeout=remaining(), label="candidate used-return",
            guard_kernel=False)
        used_return_imports_kernel(controls["candidateUsedReturn"], count=2)

        scenarios = [(2, "unchanged"), (2, "new-placement"), (24, "unchanged"), (24, "new-placement")]
        for index, (count, kind) in enumerate(scenarios):
            directory = fixture_root / f"{count}-{kind}"
            base_nonce = f"r5-{count}-{kind}-base"
            fixture = write_model(directory, count=count, placement=0, nonce=base_nonce,
                                  used_return=False)
            primes = {}
            for name, variant in variants.items():
                primes[name] = prime_document(python=args.python, package=variant["package"],
                    state=variant["state"], store=variant["store"], fixture=fixture,
                    timeout=remaining(), label=f"{count} {kind} {name}",
                    guard_kernel=name == "candidate")
                (no_kernel_in_caller if name == "candidate" else baseline_materializes)(primes[name]["model"])
            if primes["baseline"]["model"]["stepSha256"] != primes["candidate"]["model"]["stepSha256"]:
                raise RuntimeError(f"{count} {kind}: baseline/candidate prewarm STEP bytes differ")
            if kind == "new-placement":
                fixture = write_model(directory, count=count, placement=7, nonce=f"r5-{count}-{kind}-new",
                                      used_return=False)
            order = ("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")
            pair: dict[str, dict[str, Any]] = {}
            for position, name in enumerate(order, start=1):
                variant = variants[name]
                row = run_model(python=args.python, package=variant["package"], state=variant["state"],
                    store=variant["store"], fixture=fixture,
                    timeout=remaining(),
                    label=f"{count} {kind} {name} timed", guard_kernel=name == "candidate")
                (no_kernel_in_caller if name == "candidate" else baseline_materializes)(row)
                row.update(occurrences=count, scenario=kind, variant=name, orderInPair=position,
                           sourceSha256=sha256(fixture))
                pair[name] = row
                rows.append(row)
            if pair["baseline"]["stepSha256"] != pair["candidate"]["stepSha256"]:
                raise RuntimeError(f"{count} {kind}: matched public calls produced different STEP bytes")
        report = {
            "status": "passed",
            "baselineRevision": BASELINE_REVISION,
            "baselineAuthoringSha256": sha256(args.baseline_authoring),
            "candidateAuthoringSha256": sha256(candidate / "cadgen/authoring.py"),
            "gitHead": command("git", "rev-parse", "HEAD"),
            "python": args.python,
            "fixtureRoot": str(fixture_root),
            "timingBoundary": "Wall clock from public python model.py --json process start through process exit. Each package warms a private worker and successfully writes the base-source output before its pair. The unchanged timed call uses that exact source/output revision; the nonce-bearing placement revision is deliberately unprimed, so its normal source gate must execute. Not a native build-only timing or browser measurement.",
            "storeIsolation": "baseline and candidate use separate private stores, daemon state directories and sockets; CAD artifacts stay below models/.",
            "baselineCopy": baseline_copy,
            "timedPublicCalls": len(rows),
            "controls": controls,
            "runs": rows,
        }
        if len(rows) != 8:
            raise RuntimeError(f"expected exactly 8 timed public calls, got {len(rows)}")
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        for variant in variants.values():
            try:
                stop_own_daemon(python=args.python, package=variant["package"], state=variant["state"], store=variant["store"])
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            stop_own_daemon(python=args.python, package=candidate, state=state_root / "used-return/state",
                            store=state_root / "used-return/store")
        except (OSError, subprocess.SubprocessError):
            pass


if __name__ == "__main__":
    main()
