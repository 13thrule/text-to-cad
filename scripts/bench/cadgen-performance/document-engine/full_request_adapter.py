#!/usr/bin/env python3
"""Private process adapter for the document-engine full-request benchmark.

The controller supplies already captured entry buffers in a closed plan.  The
current engine sends those bytes through DocumentWorker.  Frozen legacy code
has no captured-input door, so this adapter materializes the accepted bytes
immediately before its old in-process runner call and reports that write as a
separate stage.  This is benchmark plumbing, not a product compatibility API.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import statistics
import sys
import time


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _append_jsonl(path: Path, value) -> None:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _events(text: str) -> list[dict]:
    values = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def _peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


class Adapter:
    def __init__(self, plan: dict):
        self.plan = plan
        self.engine = plan["engine"]
        if self.engine not in {"legacy", "retained"}:
            raise ValueError("full-request engine must be legacy or retained")
        self.source = Path(plan["source"])
        self.output = Path(plan["output"])
        self.journal = Path(plan["journal"])
        self.worker = None
        self.run_model_argv = None
        self.captured_type = None
        self.ready = False
        self.last_revision = None
        self.prime_sha256 = None

    def prepare(self) -> float:
        if self.ready:
            return 0.0
        started = time.perf_counter()
        if self.engine == "retained":
            from cadgen._document.sources import CapturedInput
            from cadgen._document.worker import DocumentWorker

            self.captured_type = CapturedInput
            self.worker = DocumentWorker(Path(self.plan["ownerRoot"]), max_documents=1,
                                         startup_timeout=self.plan["startupTimeout"])
        else:
            from cadgen import memoization
            from cadgen.cli._run_model import run_model_argv

            memoization.install(trusted_worker=True)
            self.run_model_argv = run_model_argv
        self.ready = True
        return (time.perf_counter() - started) * 1000.0

    def _accepted(self, request: dict) -> tuple[bytes, float]:
        started = time.perf_counter()
        payload = Path(request["input"]).read_bytes()
        if _sha256(payload) != request["digest"] or len(payload) != request["bytes"]:
            raise RuntimeError("captured benchmark entry changed before adapter acceptance")
        return payload, (time.perf_counter() - started) * 1000.0

    def execute(self, request: dict, *, cold: bool) -> dict:
        payload, accepted_ms = self._accepted(request)
        source_start = _line_count(Path(self.plan["sourceTrace"]))
        if cold:
            start_ns = int(os.environ["CADGEN_FULL_REQUEST_STARTED_NS"])
        else:
            start_ns = time.perf_counter_ns()
        setup_ms = self.prepare()
        adapter_write_ms = 0.0
        stdout = io.StringIO()
        stderr = io.StringIO()
        owner_seconds = None
        candidate = None
        input_records = []
        completion_events = []
        if self.engine == "legacy":
            write_started = time.perf_counter()
            self.source.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.source.with_suffix(self.source.suffix + ".accepted")
            temporary.write_bytes(payload)
            os.replace(temporary, self.source)
            adapter_write_ms = (time.perf_counter() - write_started) * 1000.0
            request_started = time.perf_counter()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = self.run_model_argv([str(self.source), "--json"])
            engine_request_ms = (time.perf_counter() - request_started) * 1000.0
            if code:
                raise RuntimeError(
                    f"{request['label']}: frozen runner failed with {code}\n"
                    f"{stdout.getvalue()[-1000:]}\n{stderr.getvalue()[-2000:]}"
                )
            completion_events = _events(stdout.getvalue())
            if sum(value.get("ok") is True for value in completion_events) != 1:
                raise RuntimeError(f"{request['label']}: frozen runner emitted no unique success event")
            materialized_after = _sha256(self.source.read_bytes())
            if materialized_after != request["digest"]:
                raise RuntimeError("legacy materialized entry changed during its source request")
            required = [{"destination": str(self.output), "kind": "step",
                         "attestation": "completed-file-and-json-event"},
                        {"destination": str(self.output) + ".json", "kind": "annotations",
                         "attestation": "actual-absence-check"}]
        else:
            captured = self.captured_type(self.source, payload, request["digest"])
            request_started = time.perf_counter()
            response, buffers = self.worker.generate(
                captured, timeout=self.plan["requestTimeout"],
                cancellation_grace=self.plan["cancellationGrace"])
            engine_request_ms = (time.perf_counter() - request_started) * 1000.0
            if buffers:
                raise RuntimeError("source generation unexpectedly returned binary response buffers")
            owner_seconds = float(response["seconds"])
            candidate = response["result"]
            input_records = candidate["inputs"]
            if not any(value.get("path") == str(self.source.resolve())
                       and value.get("digest") == request["digest"]
                       and value.get("bytes") == len(payload) for value in input_records):
                raise RuntimeError("current worker did not attest the exact accepted entry buffer")
            if len(input_records) != 1:
                raise RuntimeError("single-file fixture unexpectedly consumed helper or managed-data inputs")
            required = candidate["outputs"]
            if len(required) != 2:
                raise RuntimeError("fixture must complete its STEP and absent-companion obligations")

        if not self.output.is_file():
            raise RuntimeError(f"{request['label']}: required STEP output is absent")
        verify_started = time.perf_counter()
        output_payload = self.output.read_bytes()
        output_digest = _sha256(output_payload)
        if not output_payload:
            raise RuntimeError(f"{request['label']}: required STEP output is empty")
        companion = Path(str(self.output) + ".json")
        if os.path.lexists(companion):
            raise RuntimeError("these fixtures declare no annotations; the companion must be absent")
        if self.engine == "retained":
            by_destination = {Path(row["destination"]).resolve(): row for row in required}
            if set(by_destination) != {self.output.resolve(), companion.resolve()}:
                raise RuntimeError("current receipts do not name the required output pair")
            receipt = by_destination[self.output.resolve()]
            if (Path(receipt["destination"]).resolve() != self.output.resolve()
                    or receipt["sha256"] != output_digest
                    or receipt["size"] != len(output_payload)):
                raise RuntimeError("current STEP receipt does not attest the actual destination bytes")
            absent = by_destination[companion.resolve()]
            if absent["sha256"] is not None or absent["size"] != 0 or absent["action"] != "verified-absent":
                raise RuntimeError("current companion receipt does not attest its actual absence")
        verification_ms = (time.perf_counter() - verify_started) * 1000.0
        completed_ns = time.perf_counter_ns()

        archive = Path(request["archive"])
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(output_payload)
        if _sha256(archive.read_bytes()) != output_digest:
            raise RuntimeError("archived STEP sample differs from the verified request bytes")

        side_effects = _line_count(Path(self.plan["sourceTrace"])) - source_start
        if self.engine == "retained" and side_effects != 1:
            raise RuntimeError(
                f"{request['label']}: ordinary Python executed {side_effects} times, expected one"
            )
        row = {
            "label": request["label"], "sample": request["sample"],
            "measured": request["measured"],
            "geometryValue": request["geometryValue"],
            "placementValue": request["placementValue"],
            "fullRequestMs": (completed_ns - start_ns) / 1_000_000.0,
            "acceptedBufferReadHashMs": accepted_ms,
            "acceptedBufferReadHashInsideFullRequest": cold,
            "engineSetupMs": setup_ms,
            "adapterWriteMs": adapter_write_ms,
            "engineRequestMs": engine_request_ms,
            "actualByteVerificationMs": verification_ms,
            "ownerRequestMs": owner_seconds * 1000.0 if owner_seconds is not None else None,
            "sourceGeometryMs": (candidate["sourceSeconds"] * 1000.0
                                 if candidate is not None else None),
            "geometryCounters": candidate["evaluations"] if candidate is not None else None,
            "productCounters": candidate["products"] if candidate is not None else None,
            "requiredExports": required,
            "completionEventCount": (len([value for value in completion_events
                                           if value.get("ok") is True])
                                     if self.engine == "legacy" else None),
            "stdoutJsonEvents": completion_events,
            "stderrTail": stderr.getvalue()[-2000:],
            "acceptedEntry": {"path": str(self.source.resolve()),
                              "digest": request["digest"], "bytes": len(payload)},
            "consumedInputs": input_records if self.engine == "retained" else None,
            "inputDelivery": ("captured-entry-worker-payload"
                              if self.engine == "retained"
                              else "benchmark-adapter-materialized-entry"),
            "stepBytes": len(output_payload), "stepSha256": output_digest,
            "oracleStep": str(archive),
            "sourceSideEffectExecutions": side_effects,
            "requestVerification": {
                "requiredStepPresent": True,
                "actualDestinationSha256": output_digest,
                "actualDestinationBytes": len(output_payload),
                "requiredCompanionAbsent": True,
                "currentReceiptMatched": self.engine == "retained",
                "archiveCopyExcludedFromTiming": True,
            },
            "adapterProcessPeakRssBytes": _peak_rss_bytes(),
        }
        if request["measured"] and self.prime_sha256 is not None:
            row["primeStepSha256"] = self.prime_sha256
        if not request["measured"]:
            self.prime_sha256 = output_digest
        _append_jsonl(self.journal, {"kind": f"full-{self.engine}-sample"
                                    if request["measured"] else f"full-{self.engine}-prime",
                                    "model": self.plan["model"],
                                    "scenario": self.plan["scenario"], **row})
        if self.engine == "retained":
            if self.last_revision is not None:
                self.worker.release(self.last_revision, timeout=10)
            self.last_revision = candidate["revision"]
        return row

    def resident_display(self):
        if self.engine != "retained" or self.last_revision is None:
            return {"available": False,
                    "qualification": "frozen legacy adapter has no pinned resident scene"}
        started = time.perf_counter()
        response, buffers = self.worker.display(self.last_revision, timeout=60)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if not buffers:
            raise RuntimeError("resident display returned no manifest")
        result = response["result"]
        if len(buffers) != 1 + len(result["assets"]):
            raise RuntimeError("resident display asset metadata does not match its buffers")
        return {
            "available": True, "residentDisplayMs": elapsed_ms,
            "ownerRequestMs": response["seconds"] * 1000.0,
            "manifestBytes": len(buffers[0]), "manifestSha256": _sha256(buffers[0]),
            "assetCount": len(result["assets"]),
            "assetBytes": sum(len(payload) for payload in buffers[1:]),
            "qualification": (
                "candidate-only pinned-revision display after all source/STEP samples; "
                "excluded from fullRequestMs and never ratioed against saved STEP reopen"
            ),
        }

    def close(self) -> dict:
        pid = None
        startup_ms = None
        if self.worker is not None:
            pid = self.worker.pid
            startup_ms = self.worker.startup_seconds * 1000.0
            if self.last_revision is not None:
                self.worker.release(self.last_revision, timeout=10)
                self.last_revision = None
            self.worker.close()
            exited = not self.worker.process.is_alive()
        else:
            exited = True
        return {"ownerPid": pid, "ownerStartupMs": startup_ms,
                "ownerExitedAfterSession": exited}


def _line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open(encoding="utf-8") as stream:
        return sum(1 for _ in stream)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    requests = plan["requests"]
    if not requests or any(set(value) != {
            "label", "sample", "measured", "geometryValue", "placementValue",
            "input", "digest", "bytes", "archive"} for value in requests):
        raise ValueError("invalid full-request adapter plan")
    adapter = Adapter(plan)
    rows = []
    try:
        for index, request in enumerate(requests):
            rows.append(adapter.execute(request, cold=bool(plan["cold"] and index == 0)))
        display = adapter.resident_display()
    finally:
        cleanup = adapter.close()
    values = [row["fullRequestMs"] for row in rows if row["measured"]]
    report = {
        "rows": rows, "residentDisplay": display, "cleanup": cleanup,
        "medianFullRequestMs": statistics.median(values),
        "effectiveControls": {name: os.environ.get(name) for name in (
            "CADGEN_DAEMON", "CADGEN_OP_MEMO", "CADGEN_OP_MEMO_DISK",
            "CADGEN_MEMO_CACHE", "CADGEN_DETERMINISM")},
        "resolvedLegacyCacheDefaults": ({
            "operationMemoEnabled": os.environ.get("CADGEN_OP_MEMO", "1") != "0",
            "operationMemoDiskEnabled": os.environ.get("CADGEN_OP_MEMO_DISK", "1") != "0",
            "wholeCallMemoEnabled": os.environ.get("CADGEN_MEMO_CACHE", "1") != "0",
        } if plan["engine"] == "legacy" else None),
    }
    _write_json(Path(plan["workerReport"]), report)


if __name__ == "__main__":
    main()
