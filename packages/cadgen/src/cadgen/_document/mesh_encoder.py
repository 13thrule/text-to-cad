"""Owned, bounded value transport to the captured native-mesh JS codec.

The trusted service constructs MeshEncoder before authored execution. Its
captured bundled program, interpreter and environment then stay fixed. Native
handles never cross this boundary. Regular temporary descriptors avoid pipe
backpressure and are removed only after the child has exited and been reaped.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
import time
from types import MappingProxyType

from cadgen.assets import runtime_root
from cadgen._internal.node_runtime import cad_node_executable
from . import display as display_module
from .resources import Cancelled

MAX_HEADER_BYTES = 16 * 1024**2
MAX_EXPORT_BYTES = 128 * 1024**2
MAX_INPUT_BYTES = 12 + MAX_HEADER_BYTES + display_module.MAX_ASSET_BYTES
MAX_OUTPUT_BYTES = 12 + MAX_HEADER_BYTES + MAX_EXPORT_BYTES
MAX_ERROR_BYTES = 16 * 1024
MAX_PROGRAM_BYTES = 8 * 1024**2
CHUNK = 1024**2


class MeshEncodingError(RuntimeError):
    pass


class Budget:
    def __init__(self, deadline, cancellation=None):
        if type(deadline) not in (float, int) or not math.isfinite(deadline):
            raise ValueError("mesh work requires a finite absolute monotonic deadline")
        self.deadline, self.cancellation = deadline, cancellation

    def check(self):
        if self.cancellation is not None and self.cancellation.is_set():
            raise Cancelled("native mesh export was cancelled")
        if time.monotonic() >= self.deadline:
            raise TimeoutError("native mesh export deadline exceeded")

    def is_set(self):
        # Consumer checkpoints accept the Event protocol. Raising here preserves
        # the distinction between a deadline and explicit cancellation.
        self.check()
        return False


@dataclass(frozen=True)
class EncoderReceipt:
    pid: int | None
    returncode: int | None
    input_bytes: int
    output_bytes: int
    reaped: bool
    temporary_files_removed: bool


@dataclass(frozen=True)
class MeshExportProduct:
    identity: str
    format: str
    name: str
    payload: bytes
    sha256: str
    encoder_identity: tuple[str, str, str]
    facts: object


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _regular_size(stream, limit):
    value = os.fstat(stream.fileno())
    if not stat.S_ISREG(value.st_mode) or value.st_size > limit:
        raise MeshEncodingError("encoder descriptor is not a bounded regular file")
    return value.st_size


def _write(stream, payload, budget):
    view = memoryview(payload)
    for offset in range(0, len(view), CHUNK):
        budget.check()
        chunk = view[offset:offset + CHUNK]
        if stream.write(chunk) != len(chunk):
            raise MeshEncodingError("short encoder staging write")


def _freeze(value, *, depth=0, counter=None):
    counter = [0] if counter is None else counter
    counter[0] += 1
    if depth > 32 or counter[0] > 1_000_000:
        raise MeshEncodingError("encoder facts exceed expanded limits")
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is str and len(value) <= 4096:
        return value
    if type(value) is list:
        return tuple(_freeze(item, depth=depth + 1, counter=counter) for item in value)
    if type(value) is dict and all(type(key) is str and len(key) <= 4096 for key in value):
        return MappingProxyType({key: _freeze(item, depth=depth + 1, counter=counter) for key, item in value.items()})
    raise MeshEncodingError("encoder facts are not closed finite values")


def _validate_facts(value, format):
    counts = ("triangles", "prototypeVariants", "occurrences")
    if any(type(value[key]) is not int or not 0 <= value[key] < 2**53 for key in counts):
        raise MeshEncodingError("encoder fact counts")
    if value["prototypeVariants"] > 100_000 or value["occurrences"] > 100_000:
        raise MeshEncodingError("encoder fact count capacity")
    expected_pbr = (["roughness", "metalness", "clearcoat", "clearcoatRoughness", "opacity"] if format == "glb"
                    else ["roughness", "metalness"] if format == "3mf" else [])
    expected_capabilities = {"units": "meter" if format == "glb" else "millimeter", "instancing": format != "stl",
        "color": "linear-rgba" if format == "glb" else "srgb-rgb" if format == "3mf" else "none",
        "pbr": expected_pbr, "authoredMetadata": format != "stl"}
    capabilities = value["capabilities"]
    if (capabilities != expected_capabilities or type(capabilities.get("instancing")) is not bool
            or type(capabilities.get("authoredMetadata")) is not bool):
        raise MeshEncodingError("encoder capability facts")
    omissions = value["omissions"]
    if type(omissions) is not list or len(omissions) > 100_000:
        raise MeshEncodingError("encoder omission capacity")
    for row in omissions:
        if (type(row) is not dict or set(row) != {"path", "fields", "reason"}
                or type(row["path"]) is not list or not 1 <= len(row["path"]) <= 128
                or any(type(index) is not int or not 1 <= index <= 100_000 for index in row["path"])
                or type(row["fields"]) is not list or not 1 <= len(row["fields"]) <= 32
                or any(type(field) is not str or not 1 <= len(field) <= 128 for field in row["fields"])
                or type(row["reason"]) is not str or not 1 <= len(row["reason"]) <= 4096):
            raise MeshEncodingError("encoder omission schema")
    precision = value["precision"]
    error_key = "maxPositionRoundingMm" if format == "stl" else "maxLinearColorRounding" if format == "3mf" else None
    keys = {"positions", "color"} | ({error_key} if error_key else set())
    if (type(precision) is not dict or set(precision) != keys
            or precision["positions"] != ("world-float32" if format == "stl" else "native-local-float32-with-float64-transforms")
            or precision["color"] != ("linear-json-number" if format == "glb" else "srgb-8-bit" if format == "3mf" else "none")
            or error_key and (type(precision[error_key]) not in (int, float)
                             or not math.isfinite(precision[error_key]) or precision[error_key] < 0)):
        raise MeshEncodingError("encoder precision facts")


def _parse_output(payload, *, formats, name, program_sha256):
    if len(payload) < 12 or len(payload) > MAX_OUTPUT_BYTES or payload[:8] != b"CGEXOU01":
        raise MeshEncodingError("encoder output frame magic or capacity")
    size, = struct.unpack_from("<I", payload, 8)
    if size > MAX_HEADER_BYTES or size + 12 > len(payload):
        raise MeshEncodingError("encoder output metadata capacity")
    try:
        value = json.loads(payload[12:12 + size])
    except (ValueError, RecursionError) as error:
        raise MeshEncodingError("encoder output metadata is not JSON") from error
    if (type(value) is not dict or set(value) != {"version", "runtime", "products"}
            or type(value["version"]) is not int or value["version"] != 1
            or type(value["runtime"]) is not dict or set(value["runtime"]) != {"node", "v8"}
            or any(type(s) is not str or not s or len(s) > 128 for s in value["runtime"].values())
            or type(value["products"]) is not list or len(value["products"]) != len(formats)):
        raise MeshEncodingError("encoder output schema")
    runtime = (program_sha256, value["runtime"]["node"], value["runtime"]["v8"])
    offset, total, products = 12 + size, 0, []
    for row, expected in zip(value["products"], formats):
        if (type(row) is not dict or set(row) != {"format", "bytes", "sha256", "facts"}
                or row["format"] != expected or type(row["bytes"]) is not int or row["bytes"] <= 0
                or type(row["sha256"]) is not str or len(row["sha256"]) != 64
                or type(row["facts"]) is not dict
                or set(row["facts"]) != {"codec", "format", "triangles", "prototypeVariants", "occurrences",
                                         "capabilities", "omissions", "precision"}
                or type(row["facts"]["codec"]) is not int or row["facts"]["codec"] != 1
                or row["facts"]["format"] != expected):
            raise MeshEncodingError("encoder product schema")
        total += row["bytes"]
        if total > MAX_EXPORT_BYTES or offset + row["bytes"] > len(payload):
            raise MeshEncodingError("encoder product capacity")
        data = payload[offset:offset + row["bytes"]]
        offset += row["bytes"]
        if _digest(data) != row["sha256"]:
            raise MeshEncodingError("encoder output digest mismatch")
        _validate_facts(row["facts"], expected)
        facts = _freeze(row["facts"])
        identity = _digest(_json(("native-mesh-product-v1", runtime, expected, row["sha256"])))
        products.append(MeshExportProduct(identity, expected, name, data, row["sha256"], runtime, facts))
    if offset != len(payload):
        raise MeshEncodingError("encoder output has trailing bytes")
    return tuple(products)


def _content_recipe(manifest, formats, name):
    """Digest inputs only: source identities never become export identities."""
    paths, counts, rows = {}, {}, []
    leaves = {tuple(row["path"]): row for row in manifest["occurrences"]}
    for node in manifest["nodes"]:
        source = tuple(node["path"])
        counts[source[:-1]] = counts.get(source[:-1], 0) + 1
        path = paths.get(source[:-1], ()) + (counts[source[:-1]],)
        paths[source] = path
        leaf = leaves.get(source)
        mesh = None if leaf is None else manifest["prototypes"][leaf["prototype"]]["mesh"]
        rows.append((path, node["kind"], node["label"], node["transform"], node["appearance"], mesh))
    return _digest(_json(("native-mesh-input-v1", formats, name, rows)))


class MeshEncoder:
    """Explicit codec owner; construct before executing untrusted authored code.

    Uses the installed self-contained bundle in both wheels and checkouts.
    Source edits become active through the normal bundle freshness gate.
    Its bounded cache contains immutable values, never native owners or handles.
    """
    def __init__(self):
        self.executable = cad_node_executable()
        path = runtime_root() / "node" / "document-mesh-export.mjs"
        if path.is_symlink():
            raise MeshEncodingError("native mesh codec cannot be a symlink")
        with path.open("rb") as stream:
            _regular_size(stream, MAX_PROGRAM_BYTES)
            self._program = stream.read(MAX_PROGRAM_BYTES + 1)
        if not self._program or len(self._program) > MAX_PROGRAM_BYTES:
            raise MeshEncodingError("missing or oversized native mesh codec")
        self.program_sha256 = _digest(self._program)
        self._environment = {key: value for key, value in os.environ.items()
                             if key not in {"NODE_OPTIONS", "NODE_PATH"}}
        self._cache, self._cache_bytes = OrderedDict(), 0
        self.last_receipt = None

    def encode(self, product, formats, *, name, work_directory, deadline, cancellation=None):
        budget = Budget(deadline, cancellation)
        budget.check()
        if (type(product) is not display_module.DisplayProduct
                or display_module._products.get(id(product)) is not product):
            raise TypeError("native mesh export requires an attested DisplayProduct")
        formats = tuple(formats)
        if (not formats or len(formats) > 3 or len(set(formats)) != len(formats)
                or any(value not in {"stl", "glb", "3mf"} for value in formats)
                or type(name) is not str or not name or len(name) > 4096):
            raise ValueError("invalid native mesh format or name")
        manifest = json.loads(product.manifest)
        recipe = _content_recipe(manifest, formats, name)
        cached = self._cache.get(recipe)
        if cached is not None:
            self._cache.move_to_end(recipe)
            budget.check()
            return cached
        assets = tuple(product.assets.values())
        header = _json({"version": 1, "manifest": manifest, "assets": [
            {"sha256": asset.identity, "bytes": len(asset.payload)} for asset in assets], "formats": formats, "name": name})
        if len(header) > MAX_HEADER_BYTES:
            raise MeshEncodingError("encoder input metadata capacity")
        chunks = (b"CGEXIN01" + struct.pack("<I", len(header)), header) + tuple(asset.payload for asset in assets)
        output = self._run(chunks, work_directory=work_directory, budget=budget)
        products = _parse_output(output, formats=formats, name=name, program_sha256=self.program_sha256)
        budget.check()
        size = sum(len(row.payload) for row in products)
        while self._cache and (len(self._cache) >= 8 or self._cache_bytes + size > MAX_EXPORT_BYTES):
            _, old = self._cache.popitem(last=False)
            self._cache_bytes -= sum(len(row.payload) for row in old)
        self._cache[recipe] = products
        self._cache_bytes += size
        return products

    def _run(self, chunks, *, work_directory, budget):
        budget.check()
        total = sum(len(chunk) for chunk in chunks)
        if total > MAX_INPUT_BYTES:
            raise MeshEncodingError("encoder input frame capacity")
        directory = Path(work_directory)
        directory.mkdir(parents=True, exist_ok=True)
        child, output_size, path = None, 0, None
        try:
            with tempfile.TemporaryDirectory(prefix="native-mesh-", dir=directory) as temporary:
                path = Path(temporary)
                script = path / "codec.mjs"
                with script.open("xb") as stream:
                    _write(stream, self._program, budget)
                # All descriptors are freshly created below an owned directory.
                # No caller-supplied path is opened by the child.
                with (path / "input").open("x+b") as source, (path / "output").open("x+b") as result, \
                        (path / "error").open("x+b") as error:
                    for chunk in chunks:
                        _write(source, chunk, budget)
                    source.flush(); source.seek(0)
                    budget.check()
                    child = subprocess.Popen([self.executable, "--max-old-space-size=1024", str(script)],
                                             stdin=source, stdout=result, stderr=error, env=self._environment)
                    try:
                        while child.poll() is None:
                            budget.check()
                            output_size = _regular_size(result, MAX_OUTPUT_BYTES)
                            _regular_size(error, MAX_ERROR_BYTES)
                            time.sleep(min(.02, max(0, budget.deadline - time.monotonic())))
                        child.wait()
                        budget.check()
                        output_size = _regular_size(result, MAX_OUTPUT_BYTES)
                        error_size = _regular_size(error, MAX_ERROR_BYTES)
                        if child.returncode:
                            error.seek(0)
                            raise MeshEncodingError(error.read(error_size).decode("utf-8", errors="replace"))
                        # The size is checked before reading, and the sole writer
                        # is dead. No background sender or reader survives here.
                        result.seek(0)
                        payload = result.read(output_size + 1)
                        if len(payload) != output_size:
                            raise MeshEncodingError("encoder output changed after exit")
                        budget.check()
                        return payload
                    finally:
                        if child.poll() is None:
                            child.kill()
                        child.wait()
        finally:
            self.last_receipt = EncoderReceipt(None if child is None else child.pid,
                None if child is None else child.returncode, total, output_size,
                child is None or child.returncode is not None, path is None or not path.exists())
