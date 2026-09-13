"""Closed render operations shared by hosts, without daemon or source execution."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from math import isfinite
from pathlib import Path
import time

from .assets import runtime_root
from .results import SnapshotFile, SnapshotResult, SnapshotTimings
from .snapshot_core import DEFAULT_TIMEOUT_SECONDS, SnapshotError, _capture_snapshot_job

MAX_PACKET_BYTES = 64 * 1024 * 1024
MAX_FRAME_BYTES = MAX_PACKET_BYTES + 64 * 1024
CLEANUP_SECONDS = 30.0
MAX_OPERATION_SECONDS = 24 * 60 * 60


def packet_size_bound(packet):
    """Conservative JSON byte charge without allocating an encoded packet."""
    pending, size = [packet], 0
    while pending:
        value = pending.pop()
        kind = type(value)
        if kind is dict:
            size += 2 + len(value) * 2
            pending.extend(value)
            pending.extend(value.values())
        elif kind is list:
            size += 2 + len(value)
            pending.extend(value)
        elif kind is str:
            size += 2 + len(value) * 12
        elif kind is int:
            size += 2 + value.bit_length()
        else:
            size += 32
        if size > MAX_PACKET_BYTES:
            raise SnapshotError("snapshot service packet exceeds its byte capacity")
    return size


def resolved_packet(value):
    packet = _capture_snapshot_job(value)
    packet_size_bound(packet)
    if set(packet) != {"single", "jobs"} or type(packet["single"]) is not bool:
        raise SnapshotError("snapshot service requires a resolved job packet")
    if type(packet["jobs"]) is not list or not packet["jobs"]:
        raise SnapshotError("snapshot service requires a nonempty resolved job packet")
    for job in packet["jobs"]:
        if type(job) is not dict or type(job.get("resolved")) is not dict:
            raise SnapshotError("snapshot service accepts fully resolved jobs only")
        root = job["resolved"].get("rootPath")
        if root is not None:
            absolute_path(root, "render root")
        if type(job.get("outputs")) is not list:
            raise SnapshotError("snapshot service jobs require resolved outputs")
        for output in job["outputs"]:
            if type(output) is not dict:
                raise SnapshotError("snapshot outputs must be objects")
            absolute_path(output.get("path"), "output path")
        seconds = job.get("timeoutSeconds") or DEFAULT_TIMEOUT_SECONDS
        if type(seconds) not in (int, float) or not 0 < seconds <= MAX_OPERATION_SECONDS or not isfinite(seconds):
            raise SnapshotError("snapshot timeout must be a finite positive duration")
    return packet


def absolute_path(value, label):
    if type(value) is not str or not value or len(value) > 8192 or not Path(value).is_absolute():
        raise SnapshotError(f"snapshot {label} must be an absolute path")
    return value


def capture_operation(packet, *, runtime_dir, cache_root, encoder=None):
    packet = resolved_packet(packet)
    budget = sum(job.get("timeoutSeconds") or DEFAULT_TIMEOUT_SECONDS for job in packet["jobs"])
    return normalize_operation({
        "packet": packet, "runtimeRoot": str(Path(runtime_dir).resolve()),
        "storeRoot": str(Path(cache_root).resolve()), "encoder": encoder,
        # One deadline includes admission, transfer, startup, rendering and cleanup.
        "deadline": time.monotonic() + min(budget + CLEANUP_SECONDS, MAX_OPERATION_SECONDS),
    })


def normalize_operation(value):
    value = _capture_snapshot_job(value)
    if set(value) != {"packet", "runtimeRoot", "storeRoot", "encoder", "deadline"}:
        raise SnapshotError("invalid snapshot render operation fields")
    value["packet"] = resolved_packet(value["packet"])
    trusted = str((runtime_root() / "browser").resolve())
    if absolute_path(value["runtimeRoot"], "runtime root") != trusted:
        raise SnapshotError("the warm snapshot worker accepts only this installation's browser bundle")
    absolute_path(value["storeRoot"], "store root")
    if value["encoder"] is not None:
        absolute_path(value["encoder"], "encoder")
    if any(job.get("video") is not None for job in value["packet"]["jobs"]) and value["encoder"] is None:
        raise SnapshotError("video operations require the caller's resolved encoder")
    deadline = value["deadline"]
    if type(deadline) not in (int, float) or not 0 < deadline <= time.monotonic() + MAX_OPERATION_SECONDS or not isfinite(deadline):
        raise SnapshotError("invalid snapshot operation deadline")
    packet_size_bound(value)
    return value


def operation_key(operation):
    return hashlib.sha256(json.dumps(operation, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def result_value(result):
    if type(result) is not SnapshotResult:
        raise SnapshotError("snapshot worker must return a SnapshotResult")
    value = asdict(result)
    for entry in value["files"]:
        entry["path"] = str(entry["path"])
    value = _capture_snapshot_job(value)
    packet_size_bound(value)
    return value


def read_result(value):
    value = _capture_snapshot_job(value)
    if set(value) != {"ok", "files", "parts", "warnings", "timings", "debug"} or type(value["ok"]) is not bool:
        raise SnapshotError("invalid snapshot result fields")
    if any(type(value[key]) is not list for key in ("files", "parts", "warnings", "debug")):
        raise SnapshotError("invalid snapshot result collections")
    files = []
    for entry in value["files"]:
        if type(entry) is not dict or set(entry) != {"path", "kind", "view", "input", "tree", "frames", "fps", "seconds"}:
            raise SnapshotError("invalid snapshot result file")
        if any(type(entry[key]) is not str for key in ("path", "kind", "view", "input", "tree")):
            raise SnapshotError("invalid snapshot result file strings")
        if any(type(entry[key]) is not int or entry[key] < 0 for key in ("frames", "fps")):
            raise SnapshotError("invalid snapshot result frame count")
        if type(entry["seconds"]) not in (int, float) or entry["seconds"] < 0:
            raise SnapshotError("invalid snapshot result duration")
        files.append(SnapshotFile(**{**entry, "path": Path(absolute_path(entry["path"], "result path"))}))
    timing = value["timings"]
    if type(timing) is not dict or set(timing) != {"job_count", "total_ms"}:
        raise SnapshotError("invalid snapshot result timings")
    if type(timing["job_count"]) is not int or timing["job_count"] < 0 or type(timing["total_ms"]) not in (int, float) or timing["total_ms"] < 0:
        raise SnapshotError("invalid snapshot result timing values")
    if any(type(row) is not dict for row in value["parts"] + value["debug"]) or any(type(row) is not str for row in value["warnings"]):
        raise SnapshotError("invalid snapshot result details")
    return SnapshotResult(value["ok"], tuple(files), tuple(value["parts"]), tuple(value["warnings"]), SnapshotTimings(**timing), tuple(value["debug"]))


def progress_value(method, args, kwargs):
    if method not in {"phase", "detail", "advance", "narrate"}:
        raise SnapshotError("invalid snapshot progress method")
    value = _capture_snapshot_job({"method": method, "args": args, "kwargs": kwargs})
    if type(value["args"]) is not list or type(value["kwargs"]) is not dict:
        raise SnapshotError("invalid snapshot progress arguments")
    if packet_size_bound(value) > 64 * 1024:
        raise SnapshotError("snapshot progress frame exceeds its size limit")
    return value
