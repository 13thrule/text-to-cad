"""A caller-owned, bounded RPC process; it never owns a renderer or executes source.

The existing cross-platform authenticated channel is intentionally unchanged.
Its blocking handshake is contained here so an unresponsive peer cannot strand
the calling process or its event loop past the operation's absolute deadline.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

from cadgen.snapshot_core import SnapshotError, _capture_snapshot_job, _finish_snapshot_cleanup
from cadgen.snapshot_operation import MAX_FRAME_BYTES, normalize_operation, operation_key, progress_value

TRANSPORT_REAP_SECONDS = 1.0


async def _drain_stderr(stream):
    tail = bytearray()
    while chunk := await stream.read(8192):
        tail.extend(chunk)
        if len(tail) > 8192:
            del tail[:-8192]
    return bytes(tail).decode(errors="replace")


async def _reap(proc, deadline):
    if proc.returncode is None:
        with suppress(ProcessLookupError):
            proc.kill()
    try:
        await asyncio.wait_for(proc.wait(), max(.001, deadline - time.monotonic()))
        return True
    except asyncio.TimeoutError:
        return False


async def transport_request(payload, cancel, relay):
    """Only a supervisor receipt proves render cleanup; transport reap is distinct."""
    from cadgen.daemon.snapshot import read_receipt

    operation = payload["snapshot"]
    deadline = operation["deadline"]
    transport_deadline = deadline - TRANSPORT_REAP_SECONDS
    env = dict(os.environ)
    # Import only this installation, regardless of the source caller's import
    # path. -P also excludes its current directory from runtime lookup.
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    proc = None
    stderr = control = None
    receipt = None
    failure = None
    reaped = False
    try:
        async with asyncio.timeout_at(transport_deadline):
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-P", "-m", "cadgen.daemon.snapshot_transport",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, limit=MAX_FRAME_BYTES,
                cwd=tempfile.gettempdir(), env=env,
            )
            stderr = asyncio.create_task(_drain_stderr(proc.stderr))
            proc.stdin.write(json.dumps(payload, separators=(",", ":"), allow_nan=False).encode() + b"\n")
            await proc.stdin.drain()

            async def cancel_request():
                await cancel.wait()
                proc.stdin.write(b'{"cancel":true}\n')
                await proc.stdin.drain()

            control = asyncio.create_task(cancel_request())
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    raise SnapshotError("snapshot transport exited without a supervisor cleanup receipt")
                if len(raw) > MAX_FRAME_BYTES:
                    raise SnapshotError("snapshot transport frame exceeds its byte limit")
                frame = _capture_snapshot_job(json.loads(raw))
                if set(frame) == {"receipt"}:
                    receipt = read_receipt(operation, frame["receipt"], as_value=True)
                    if await proc.stdout.read(1):
                        raise SnapshotError("snapshot transport emitted data after its completion receipt")
                    break
                if set(frame) == {"transportError"} and type(frame["transportError"]) is str:
                    raise SnapshotError(frame["transportError"])
                if set(frame) != {"progress"}:
                    raise SnapshotError("invalid snapshot transport output")
                event = frame["progress"]
                if type(event) is not dict or set(event) != {"method", "args", "kwargs"}:
                    raise SnapshotError("invalid snapshot transport progress")
                if event["method"] == "stream":
                    if type(event["args"]) is not list or len(event["args"]) != 2 or event["args"][0] not in {"stdout", "stderr"} or type(event["args"][1]) is not str or event["kwargs"] != {}:
                        raise SnapshotError("invalid snapshot transport stream")
                else:
                    event = progress_value(event["method"], event["args"], event["kwargs"])
                if not cancel.is_set():
                    relay.send(event["method"], *event["args"], **event["kwargs"])
            proc.stdin.close()
            await proc.wait()
            if proc.returncode != 0:
                raise SnapshotError("snapshot transport exited unsuccessfully after its receipt")
            reaped = True
    except BaseException as exc:
        failure = exc
    finally:
        if control is not None:
            control.cancel()
            with suppress(BaseException):
                await control
        if proc is not None and not reaped:
            cleanup = asyncio.create_task(_reap(proc, deadline))
            await _finish_snapshot_cleanup(cleanup)
            reaped = cleanup.result()
        if stderr is not None:
            if not stderr.done():
                stderr.cancel()
            with suppress(BaseException):
                await stderr
    if failure is not None:
        evidence = "transport process reaped" if reaped else "transport process cleanup was not acknowledged"
        render_evidence = "supervisor confirmed render cleanup" if receipt is not None else "worker/browser cleanup was not confirmed"
        raise SnapshotError(f"snapshot transport failed ({evidence}; {render_evidence}): {str(failure) or type(failure).__name__}") from failure
    return read_receipt(operation, receipt)


class _Lines:
    """Bounded stdin lines using raw I/O, safe with a daemon control reader."""
    def __init__(self):
        self.pending = bytearray()

    def read(self):
        while True:
            end = self.pending.find(b"\n")
            if end >= 0:
                value = bytes(self.pending[:end])
                del self.pending[:end + 1]
                return value
            if len(self.pending) > MAX_FRAME_BYTES:
                raise SnapshotError("snapshot transport input exceeds its byte limit")
            chunk = os.read(0, 65536)
            if not chunk:
                return b""
            self.pending.extend(chunk)


def _emit(value):
    sys.stdout.write(json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n")
    sys.stdout.flush()


def main():
    from cadgen.daemon.snapshot import _run_remote

    lines = _Lines()
    cancel = threading.Event()
    try:
        payload = _capture_snapshot_job(json.loads(lines.read()))
        if set(payload) != {"tool", "argv", "snapshot", "request", "token"} or payload["tool"] != "snapshot-render" or payload["argv"] != []:
            raise SnapshotError("invalid snapshot transport request")
        payload["snapshot"] = normalize_operation(payload["snapshot"])
        if operation_key(payload["snapshot"]) != payload["request"]:
            raise SnapshotError("snapshot transport request digest mismatch")

        def control():
            try:
                raw = lines.read()
                if not raw or json.loads(raw) == {"cancel": True}:
                    cancel.set()
                else:
                    cancel.set()
            except BaseException:
                cancel.set()

        threading.Thread(target=control, name="snapshot-transport-control", daemon=True).start()

        class Relay:
            def send(self, method, *args, **kwargs):
                _emit({"progress": {"method": method, "args": args, "kwargs": kwargs}})

        _emit({"receipt": _run_remote(payload, cancel, Relay())})
        return 0
    except BaseException as exc:
        _emit({"transportError": (str(exc) or type(exc).__name__)[:8192]})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
