"""Bounded value and binary messages on a private process connection.

No pickle decoding, native objects, base64 mesh expansion or file paths for
temporary payloads. A connection has exactly one reader and one writer.
"""
from __future__ import annotations

import json
import math
from types import MappingProxyType


PROTOCOL = 1
MAX_HEADER = 1024 * 1024
MAX_BYTES = 272 * 1024 * 1024
CHUNK_BYTES = 4 * 1024 * 1024
MAX_PAYLOADS = 4096


class WireError(ValueError):
    pass


class WireStreamInterrupted(WireError):
    """A payload frame was only partly consumed; the connection cannot resume."""


def _value(value, depth=0, budget=None):
    # Count expanded visits, not unique Python objects. A tiny shared DAG can
    # otherwise expand exponentially before the encoded-header check runs.
    if budget is None:
        budget = [8 * MAX_HEADER]
    budget[0] -= 64
    if type(value) is str:
        budget[0] -= 4 * len(value)
    elif type(value) is int:
        budget[0] -= (value.bit_length() + 7) // 8
    if budget[0] < 0:
        raise WireError("document metadata expansion exceeds the protocol limit")
    if depth > 128:
        raise WireError("document message nesting exceeds the protocol limit")
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) in (list, tuple):
        return [_value(item, depth + 1, budget) for item in value]
    if type(value) in (dict, MappingProxyType) and all(type(key) is str for key in value):
        return {_value(key, depth + 1, budget): _value(item, depth + 1, budget)
                for key, item in value.items()}
    raise WireError("document messages contain only finite value data")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise WireError("document metadata contains a duplicate field")
        result[key] = value
    return result


def _constant(value):
    raise WireError(f"document metadata contains a non-finite constant: {value}")


def prepare(value, payloads=()):
    """Validate and freeze a message before any bytes reach its connection."""
    if type(payloads) not in (list, tuple):
        raise WireError("document payload count exceeds the protocol limit")
    payloads = tuple(payloads)
    if len(payloads) > MAX_PAYLOADS:
        raise WireError("document payload count exceeds the protocol limit")
    if any(type(payload) is not bytes for payload in payloads):
        raise WireError("document payloads require immutable bytes")
    lengths = [len(payload) for payload in payloads]
    if sum(lengths) > MAX_BYTES:
        raise WireError("document payload bytes exceed the protocol limit")
    try:
        header = json.dumps(
            {"version": PROTOCOL, "value": _value(value), "lengths": lengths},
            separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (OverflowError, UnicodeError, ValueError, RecursionError) as error:
        if isinstance(error, WireError):
            raise
        raise WireError("document metadata cannot be encoded") from error
    if len(header) > MAX_HEADER:
        raise WireError("document metadata exceeds the protocol limit")
    return header, payloads


def send_prepared(connection, message):
    """Send a private result of prepare; the caller owns the whole exchange."""
    header, payloads = message
    connection.send_bytes(header)
    for payload in payloads:
        view = memoryview(payload)
        for offset in range(0, len(view), CHUNK_BYTES):
            connection.send_bytes(view[offset:offset + CHUNK_BYTES])


def send(connection, value, payloads=()):
    send_prepared(connection, prepare(value, payloads))


def receive(connection, *, before_read=lambda: None):
    before_read()
    try:
        header = json.loads(connection.recv_bytes(MAX_HEADER),
                            object_pairs_hook=_object, parse_constant=_constant)
    except (ValueError, UnicodeDecodeError, OSError, RecursionError) as error:
        raise WireError("invalid document message header") from error
    if (type(header) is not dict or set(header) != {"version", "value", "lengths"}
            or type(header["version"]) is not int or header["version"] != PROTOCOL):
        raise WireError("invalid document protocol version or fields")
    lengths = header["lengths"]
    if (type(lengths) is not list or len(lengths) > MAX_PAYLOADS
            or any(type(size) is not int or size < 0 for size in lengths)
            or sum(lengths) > MAX_BYTES):
        raise WireError("invalid document payload lengths")
    value = _value(header["value"])
    payloads = []
    for size in lengths:
        # Allocate only after validating the whole declared message budget.
        payload = bytearray(size)
        for offset in range(0, size, CHUNK_BYTES):
            try:
                before_read()
                chunk = connection.recv_bytes(CHUNK_BYTES)
            except BaseException as error:
                raise WireStreamInterrupted("document payload stream was interrupted") from error
            if len(chunk) != min(CHUNK_BYTES, size - offset):
                raise WireStreamInterrupted("document payload frame has an invalid length")
            payload[offset:offset + len(chunk)] = chunk
        payloads.append(bytes(payload))
    return value, tuple(payloads)
