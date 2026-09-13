"""Bounded JSON/binary process framing rejects ambiguous or partial messages."""
from __future__ import annotations

import json
import multiprocessing
from types import MappingProxyType
import unittest
from unittest.mock import patch

from cadgen._document import wire


class WireTests(unittest.TestCase):
    def setUp(self):
        self.left, self.right = multiprocessing.Pipe(duplex=True)
        self.addCleanup(self.left.close)
        self.addCleanup(self.right.close)

    def test_round_trip_preserves_values_and_exact_binary_boundaries(self):
        value = MappingProxyType({"finite": 1.25, "nested": (True, None, "ok")})
        with patch.object(wire, "CHUNK_BYTES", 3):
            wire.send(self.left, value, (b"abcdefgh", b"", b"xyz"))
            decoded, payloads = wire.receive(self.right)
        self.assertEqual(decoded, {"finite": 1.25, "nested": [True, None, "ok"]})
        self.assertEqual(payloads, (b"abcdefgh", b"", b"xyz"))

    def test_sender_rejects_unbounded_or_non_value_messages_before_writing(self):
        recursive = []
        recursive.append(recursive)
        cases = (
            ({"bad": float("nan")}, ()),
            ({"bad": object()}, ()),
            (recursive, ()),
            ({}, (bytearray(b"mutable"),)),
        )
        for value, payloads in cases:
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(wire.WireError):
                    wire.send(self.left, value, payloads)
        with patch.object(wire, "MAX_PAYLOADS", 1):
            with self.assertRaisesRegex(wire.WireError, "count"):
                wire.send(self.left, {}, (b"a", b"b"))
        with patch.object(wire, "MAX_BYTES", 2):
            with self.assertRaisesRegex(wire.WireError, "bytes"):
                wire.send(self.left, {}, (b"abc",))
        with patch.object(wire, "MAX_HEADER", 20):
            with self.assertRaisesRegex(wire.WireError, "metadata"):
                wire.send(self.left, {"text": "x" * 40})

    def test_receiver_rejects_duplicate_unknown_nonfinite_and_oversized_metadata(self):
        headers = (
            b'{"version":1,"version":1,"value":{},"lengths":[]}',
            b'{"version":1,"value":{},"lengths":[],"extra":0}',
            b'{"version":1,"value":NaN,"lengths":[]}',
            b'{"version":true,"value":{},"lengths":[]}',
        )
        for header in headers:
            with self.subTest(header=header):
                self.left.send_bytes(header)
                with self.assertRaises(wire.WireError):
                    wire.receive(self.right)
        with patch.object(wire, "MAX_HEADER", 8):
            self.left.send_bytes(b"x" * 9)
            with self.assertRaises(wire.WireError):
                wire.receive(self.right)

    def test_receiver_checks_declared_totals_and_each_chunk(self):
        header = lambda lengths: json.dumps(
            {"version": wire.PROTOCOL, "value": {}, "lengths": lengths},
            separators=(",", ":")).encode()
        with patch.object(wire, "MAX_BYTES", 3):
            self.left.send_bytes(header([4]))
            with self.assertRaisesRegex(wire.WireError, "lengths"):
                wire.receive(self.right)

        self.left.send_bytes(header([4]))
        self.left.send_bytes(b"abc")
        with self.assertRaisesRegex(wire.WireStreamInterrupted, "frame"):
            wire.receive(self.right)

    def test_shared_dag_expansion_is_bounded_before_encoding_or_writing(self):
        value = [0]
        for _ in range(40):
            value = [value, value]
        with self.assertRaisesRegex(wire.WireError, "expansion"):
            wire.send(self.left, value)
        self.assertFalse(self.right.poll())

    def test_excessive_json_nesting_is_a_protocol_failure(self):
        self.left.send_bytes(b'{"version":1,"value":' + b'[' * 2000
                             + b'0' + b']' * 2000 + b',"lengths":[]}')
        with self.assertRaises(wire.WireError):
            wire.receive(self.right)

    def test_payload_wait_failure_marks_stream_unusable(self):
        header = json.dumps(
            {"version": wire.PROTOCOL, "value": {"ok": True}, "lengths": [4]},
            separators=(",", ":")).encode()
        self.left.send_bytes(header)
        calls = 0

        def wait():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise TimeoutError("payload timed out")

        with self.assertRaises(wire.WireStreamInterrupted) as failure:
            wire.receive(self.right, before_read=wait)
        self.assertIsInstance(failure.exception.__cause__, TimeoutError)

    def test_payload_list_is_captured_before_metadata_encoding(self):
        buffers = [b"original"]
        original_value = wire._value

        def mutate_and_encode(*args, **kwargs):
            buffers[:] = [b"replacement", b"extra"]
            return original_value(*args, **kwargs)

        with patch.object(wire, "_value", side_effect=mutate_and_encode):
            prepared = wire.prepare(None, buffers)
        wire.send_prepared(self.left, prepared)
        value, received = wire.receive(self.right)
        self.assertIsNone(value)
        self.assertEqual((b"original",), received)


if __name__ == "__main__":
    unittest.main()
