"""Daemon channels have one close owner even when cancellation races cleanup."""

from __future__ import annotations

import threading
import unittest

from cadgen.daemon.transport import Channel


class _BlockingCloseConnection:
    def __init__(self) -> None:
        self.close_entered = threading.Event()
        self.release_close = threading.Event()
        self.closed = threading.Event()
        self.close_calls = 0
        self._guard = threading.Lock()

    def close(self) -> None:
        with self._guard:
            self.close_calls += 1
        self.close_entered.set()
        self.release_close.wait(2)
        self.closed.set()


class _BlockingReceiveConnection:
    def __init__(self) -> None:
        self.receive_entered = threading.Event()
        self.closed = threading.Event()
        self.close_calls = 0

    def recv_bytes(self) -> bytes:
        self.receive_entered.set()
        if not self.closed.wait(2):
            raise TimeoutError("close did not unblock receive")
        raise OSError("connection closed")

    def close(self) -> None:
        self.close_calls += 1
        self.closed.set()


class ChannelCloseOwnershipTest(unittest.TestCase):
    def test_concurrent_close_has_one_underlying_owner_without_serializing_callers(self) -> None:
        connection = _BlockingCloseConnection()
        channel = Channel(connection)
        first = threading.Thread(target=channel.close)
        first.start()
        self.assertTrue(connection.close_entered.wait(1), "first close did not reach the connection")

        second_done = threading.Event()

        def close_again() -> None:
            channel.close()
            second_done.set()

        second = threading.Thread(target=close_again)
        second.start()
        try:
            self.assertTrue(second_done.wait(1), "duplicate close waited behind the blocking owner")
            self.assertEqual(connection.close_calls, 1)
        finally:
            connection.release_close.set()
            first.join(2)
            second.join(2)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())

    def test_close_unblocks_receive_and_repeated_close_is_idempotent(self) -> None:
        connection = _BlockingReceiveConnection()
        channel = Channel(connection)
        received: list[bytes | None] = []
        receiver = threading.Thread(target=lambda: received.append(channel.recv()))
        receiver.start()
        self.assertTrue(connection.receive_entered.wait(1), "receive did not begin")

        channel.close()
        channel.close()
        receiver.join(2)

        self.assertFalse(receiver.is_alive())
        self.assertEqual(received, [b""])
        self.assertEqual(connection.close_calls, 1)


if __name__ == "__main__":
    unittest.main()
