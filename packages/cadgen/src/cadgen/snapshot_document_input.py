"""Closed, value-only native snapshot asset capability. No source or kernel work."""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import re
import stat

DOCUMENT_ASSET_PREFIX = "/__document_asset/"
MAX_MANIFEST_BYTES = 16 * 1024**2
MAX_MESH_BYTES = 128 * 1024**2
MAX_ASSET_BYTES = 256 * 1024**2
MAX_ASSETS = 100_000
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_UNSUPPORTED = frozenset({"selection", "kinematics", "jointValues", "animation", "video",
                          "selectorRuntime", "displayEdgeRuntime", "stepParameterUrl",
                          "sourceSidecar", "meshData", "package", "url", "glbUrl", "pose"})


def native_mesh_options(job):
    """Same bounded snapshot quality rungs as the shared scene policy."""
    render = job.get("render")
    quality = job.get("quality", {}).get("tessellation", {}) or {}
    final = render is not None and render.get("quality", "final") == "final"
    return {"relative_chord": .00015 if final else quality.get("chordTolerance", .0015),
            "angular": .35 if render is not None else quality.get("angleTolerance", .35),
            "edges": render is None}


def native_job_options(job):
    if job.get("mode", "view") != "view":
        raise ValueError("native document snapshots currently support only still view mode")
    conflicts = _UNSUPPORTED.intersection(job)
    if conflicts:
        raise ValueError("unsupported native document snapshot fields: " + ", ".join(sorted(conflicts)))
    if job.get("kind", "step") not in {"step", "stp"}:
        raise ValueError("native document snapshots require STEP scene units")


def document_descriptor(value):
    """Validate and copy the complete descriptor before an asynchronous consumer."""
    if type(value) is not dict or set(value) != {"version", "owner", "revision", "manifest", "assets", "meshing"}:
        raise ValueError("invalid native snapshot descriptor fields")
    if (type(value["version"]) is not int or value["version"] != 1
            or type(value["owner"]) is not str or not 0 < len(value["owner"]) <= 4096
            or type(value["revision"]) is not int or value["revision"] < 1):
        raise ValueError("invalid native snapshot revision")
    manifest = value["manifest"]
    if (type(manifest) is not dict or set(manifest) != {"sha256", "bytes"}
            or type(manifest["sha256"]) is not str or not _HASH.fullmatch(manifest["sha256"])
            or type(manifest["bytes"]) is not int or not 1 <= manifest["bytes"] <= MAX_MANIFEST_BYTES):
        raise ValueError("invalid native snapshot manifest binding")
    if type(value["assets"]) is not dict or not 0 < len(value["assets"]) <= MAX_ASSETS:
        raise ValueError("invalid native snapshot asset inventory")
    assets, size = {}, 0
    for identity, row in value["assets"].items():
        if (type(identity) is not str or not _HASH.fullmatch(identity)
                or identity == manifest["sha256"] or type(row) is not dict or set(row) != {"bytes"}
                or type(row["bytes"]) is not int or not 12 <= row["bytes"] <= MAX_MESH_BYTES):
            raise ValueError("invalid native snapshot mesh binding")
        size += row["bytes"]
        if size > MAX_ASSET_BYTES:
            raise ValueError("native snapshot assets exceed the byte capacity")
        assets[identity] = dict(row)
    options = value["meshing"]
    if type(options) is not dict or set(options) != {"relative_chord", "angular", "edges"}:
        raise ValueError("invalid native snapshot mesh policy")
    for key, minimum, maximum in (("relative_chord", 1e-5, 1), ("angular", .005, math.pi)):
        if type(options[key]) not in (int, float) or not math.isfinite(options[key]) or not minimum <= options[key] <= maximum:
            raise ValueError("native snapshot mesh policy exceeds the supported range")
    if type(options["edges"]) is not bool:
        raise ValueError("native snapshot edges policy must be boolean")
    return {**value, "manifest": dict(manifest), "assets": assets, "meshing": dict(options)}


def native_job_descriptor(job):
    resolved = job.get("resolved", {})
    if "document" not in resolved:
        return None
    native_job_options(job)
    if set(resolved) - {"kind", "rootPath", "inputPath", "document", "inputHash"}:
        raise ValueError("native snapshot cannot be combined with another resolved source")
    if resolved.get("kind") not in {"step", "stp"}:
        raise ValueError("native snapshot requires a resolved STEP scene")
    root = resolved.get("rootPath")
    if type(root) is not str or not Path(root).is_absolute():
        raise ValueError("native snapshot requires an absolute asset capability root")
    if "inputHash" in resolved and (type(resolved["inputHash"]) is not str or not _HASH.fullmatch(resolved["inputHash"])):
        raise ValueError("invalid saved native snapshot input digest")
    descriptor = document_descriptor(resolved["document"])
    if descriptor["meshing"] != native_mesh_options(job):
        raise ValueError("native snapshot mesh policy does not match the requested snapshot quality")
    return descriptor


def asset_inventory(descriptor):
    return {descriptor["manifest"]["sha256"]: descriptor["manifest"]["bytes"],
            **{key: row["bytes"] for key, row in descriptor["assets"].items()}}


def read_regular(path, maximum, *, expected_bytes=None):
    """Bounded regular-file capture; opening a substituted FIFO cannot block."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum
                or (expected_bytes is not None and metadata.st_size != expected_bytes)):
            raise ValueError("native snapshot input size/type changed")
        data = stream.read(metadata.st_size + 1)
    if len(data) != metadata.st_size or (expected_bytes is not None and len(data) != expected_bytes):
        raise ValueError("native snapshot input exceeded its captured byte length")
    return data


def read_asset(root, inventory, identity):
    """Read one regular hash-named file, with a fixed bound and no symlink follow."""
    if identity not in inventory:
        raise FileNotFoundError("asset is outside the native snapshot capability")
    length = inventory[identity]
    data = read_regular(Path(root) / identity, length, expected_bytes=length)
    if len(data) != length or hashlib.sha256(data).hexdigest() != identity:
        raise ValueError("native snapshot asset does not match its captured hash")
    return data
