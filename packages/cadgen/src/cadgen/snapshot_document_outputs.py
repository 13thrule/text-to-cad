"""Bounded native still verification and publication after renderer cleanup."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import struct
import time
import zlib

from ._internal.atomic_replace import write_bytes_atomic
from .results import SnapshotFile, SnapshotResult
from .snapshot_document_input import read_regular

MAX_OUTPUT_BYTES = 128 * 1024**2
MAX_OUTPUTS = 256
MAX_OUTPUT_SIDE = 8192
_PNG = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class PublishedOutput:
    target: Path
    size: int
    sha256: str


def _matches(receipt):
    data = read_regular(receipt.target, receipt.size, expected_bytes=receipt.size)
    return hashlib.sha256(data).hexdigest() == receipt.sha256


def rollback_outputs(published):
    """Remove acknowledged writes only while their exact bytes still match.

    This is a bounded ownership check, not a cross-process path lock: another
    writer may still race the final check/unlink, as with the shared writer's
    atomic replacement. A different observed payload is never removed.
    """
    errors = []
    for receipt in reversed(published):
        try:
            if _matches(receipt):
                receipt.target.unlink(missing_ok=True)
        except (FileNotFoundError, ValueError):
            # Removed, replaced, nonregular or resized paths are no longer the
            # acknowledged effect represented by this receipt.
            continue
        except OSError as error:
            errors.append(error)
    if errors:
        for error in errors[1:]:
            errors[0].add_note(f"Additional native snapshot rollback failure: {error}")
        raise errors[0]


def output_inventory(job):
    rows, targets, total = [], set(), 0
    if not 0 < len(job["outputs"]) <= MAX_OUTPUTS:
        raise ValueError("native snapshot output count exceeds its capacity")
    for output in job["outputs"]:
        width, height = output["width"], output["height"]
        if any(type(value) is not int or not 0 < value <= MAX_OUTPUT_SIDE for value in (width, height)):
            raise ValueError("native snapshot dimensions must be within 1..8192 pixels")
        target = Path(output["path"])
        if target in targets:
            raise ValueError("native snapshot outputs require distinct final paths")
        targets.add(target)
        # RGBA/filter bytes plus conservative deflate/chunk overhead. This is
        # an admission bound, not an estimate based on typical image compression.
        raw = height * (width * 4 + 1)
        maximum = raw + (raw // 16383 + 1) * 5 + 65536
        total += maximum
        if total > MAX_OUTPUT_BYTES:
            raise ValueError("native snapshot outputs exceed their 128 MiB byte capacity")
        rows.append({"target": target, "width": width, "height": height, "bytes": maximum})
    return tuple(rows), total


def _check(deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError("native snapshot exhausted its original deadline during PNG publication")


def verify_png(data, width, height, deadline):
    """Validate exact static 8-bit RGB(A) browser PNGs with bounded decompression."""
    if not data.startswith(_PNG):
        raise ValueError("native snapshot output is not a PNG")
    offset, chunks, inflated = 8, 0, 0
    decoder = None
    row_size = None
    ended = False
    seen_idat = False
    idat_ended = False
    while offset < len(data):
        _check(deadline)
        chunks += 1
        if chunks > 100_000 or offset + 12 > len(data):
            raise ValueError("invalid native snapshot PNG framing")
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data):
            raise ValueError("truncated native snapshot PNG chunk")
        payload = memoryview(data)[offset + 8:offset + 8 + length]
        crc = zlib.crc32(payload, zlib.crc32(kind)) & 0xffffffff
        if struct.unpack_from(">I", data, end - 4)[0] != crc:
            raise ValueError("native snapshot PNG checksum mismatch")
        if chunks == 1:
            if kind != b"IHDR" or length != 13:
                raise ValueError("native snapshot PNG requires its exact header")
            w, h, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if ((w, h) != (width, height) or depth != 8 or color not in (2, 6)
                    or compression or filtering or interlace):
                raise ValueError("native snapshot PNG dimensions or pixel format differ from the request")
            row_size = width * (4 if color == 6 else 3) + 1
            decoder = zlib.decompressobj()
        elif kind == b"IDAT":
            if idat_ended:
                raise ValueError("native snapshot PNG has noncontiguous image data")
            seen_idat = True
            for start in range(0, len(payload), 65536):
                pending = payload[start:start + 65536]
                while pending:
                    _check(deadline)
                    block = decoder.decompress(pending, 65536)
                    pending = decoder.unconsumed_tail
                    if inflated + len(block) > height * row_size or decoder.unused_data:
                        raise ValueError("native snapshot PNG exceeds its decoded dimensions")
                    first = (-inflated) % row_size
                    if any(block[index] > 4 for index in range(first, len(block), row_size)):
                        raise ValueError("native snapshot PNG contains an invalid row filter")
                    inflated += len(block)
        elif kind == b"IEND":
            if length or not seen_idat or not decoder.eof or inflated != height * row_size or end != len(data):
                raise ValueError("native snapshot PNG has incomplete or trailing image data")
            ended = True
        else:
            if seen_idat:
                idat_ended = True
            # Browser screenshots may carry these bounded ancillary chunks.
            # APNG, palettes, private critical chunks and unknown image modes
            # are not a successful static browser still under this contract.
            if kind not in (b"sRGB", b"gAMA", b"cHRM", b"pHYs", b"iCCP", b"tEXt", b"zTXt", b"iTXt"):
                raise ValueError("unsupported native snapshot PNG chunk")
        offset = end
    if not ended:
        raise ValueError("native snapshot PNG has no complete image terminator")


def publish_outputs(result, inventory, private_paths, deadline, *, published):
    started = time.perf_counter()
    if type(result) is not SnapshotResult or result.ok is not True or len(result.files) != len(inventory):
        raise ValueError("native snapshot result has an incomplete output inventory")
    owned = []
    mapping = {}
    for output, row, private in zip(result.files, inventory, private_paths):
        _check(deadline)
        if (type(output) is not SnapshotFile or output.path != private or output.kind != "png"
                or output.frames or output.fps or output.seconds):
            raise ValueError("native snapshot result names an unexpected output")
        data = read_regular(private, row["bytes"])
        verify_png(data, row["width"], row["height"], deadline)
        owned.append(data)
        mapping[str(private)] = str(row["target"])
    # Every output is complete and verified before the first external rename.
    for row, data in zip(inventory, owned):
        _check(deadline)
        receipt = PublishedOutput(row["target"], len(data), hashlib.sha256(data).hexdigest())
        write_bytes_atomic(row["target"], data)
        published.append(receipt)
    # Read back every final path after all writes. A later camera's publication
    # can expose a concurrent replacement of an earlier camera's destination.
    for receipt in published:
        _check(deadline)
        if not _matches(receipt):
            raise ValueError("native snapshot published output differs from its verified bytes")
    _check(deadline)
    def remap(value):
        if type(value) is dict:
            return {key: mapping.get(item, item) if key == "path" and type(item) is str else remap(item)
                    for key, item in value.items()}
        if type(value) in (list, tuple):
            return [remap(item) for item in value]
        return value
    return replace(result, files=tuple(replace(output, path=row["target"]) for output, row in zip(result.files, inventory)),
                   debug=tuple(remap(row) for row in result.debug),
                   timings=replace(result.timings, total_ms=result.timings.total_ms + (time.perf_counter() - started) * 1000))
