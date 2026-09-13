"""The document process bridge retains exact inputs and fails owners honestly."""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import signal
import time
import unittest
from unittest.mock import patch

from cadgen._document import wire
from cadgen._document.sources import CapturedInput
from cadgen._document.worker import DocumentWorker, WorkerError, WorkerTimeout
from tests.python.support.paths import REPO_ROOT
from tests.python.support.tmp_root import generated_cad_directory


BAD_SOURCE = b"""from cadgen import step
@step(out='bad.step')
def bad():
    raise RuntimeError('expected authored failure')
"""

MULTIPROCESS_SOURCE = b"""import multiprocessing
import time
from cadgen import build123d as bd, step
@step(out='multiprocess.step')
def model():
    child = multiprocessing.get_context('spawn').Process(
        target=time.sleep, args=(0.01,))
    child.start()
    child.join(10)
    if child.exitcode != 0:
        raise RuntimeError(f'authored child failed: {child.exitcode}')
    return bd.Box(2, 3, 4)
"""

HANG_SOURCE = b"""from pathlib import Path
import time
marker = Path(__file__).with_suffix('.started')
marker.write_text((marker.read_text() if marker.exists() else '') + 'run\\n')
time.sleep(30)
raise RuntimeError('unreachable')
"""


def _abandon_owner(root, sender):
    """Exit a client abruptly so only the child's parent-death watch can act."""
    try:
        worker = DocumentWorker(Path(root), startup_timeout=60)
        sender.send(worker.pid)
        sender.close()
        os._exit(0)
    except BaseException:
        try:
            sender.send(-1)
        finally:
            sender.close()


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class WorkerTests(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="document-worker-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.catalog = self.directory / "catalog"
        fixture = REPO_ROOT / "models" / "performance_document" / "assembly24.py"
        self.source_path = self.directory / "assembly24.py"
        self.source_path.write_bytes(fixture.read_bytes())
        self.source = CapturedInput.read(self.source_path)
        self.target = self.directory / "assembly24.step"

    @staticmethod
    def _result(call):
        response, payloads = call
        return response["result"], payloads

    def test_exact_source_warm_display_assets_failure_reuse_and_authored_process(self):
        # The entry path can change after capture; the transmitted bytes remain
        # the only executable input.
        self.source_path.write_bytes(BAD_SOURCE)
        with DocumentWorker(self.catalog, startup_timeout=60) as worker:
            self.assertGreaterEqual(worker.startup_seconds, 0)
            cold, _ = self._result(worker.generate(self.source, timeout=60))
            first_revision = cold["revision"]
            self.assertEqual(self.source.digest, cold["inputs"][0]["digest"])
            display, buffers = self._result(worker.display(
                first_revision,
                options={"relative_chord": .01, "angular": .5, "edges": True},
                timeout=60))
            manifest = json.loads(buffers[0])
            self.assertEqual(24, len(manifest["occurrences"]))
            self.assertEqual(1, len(manifest["prototypes"]))
            self.assertEqual(1 + len(display["assets"]), len(buffers))
            self.assertEqual(1, len(display["assets"]))

            occurrence = manifest["occurrences"][0]
            reference = {
                "version": 1,
                "owner": manifest["owner"],
                "revision": manifest["revision"],
                "path": occurrence["path"],
                "prototype": occurrence["prototype"],
                "kind": "component",
                "ordinal": None,
            }
            inspected, query_buffers = self._result(
                worker.inspect(first_revision, [reference], timeout=60))
            self.assertEqual((), query_buffers)
            self.assertEqual("world", inspected["facts"][0]["space"])
            self.assertGreater(inspected["facts"][0]["volume"], 0)

            warm, _ = self._result(worker.generate(self.source, timeout=60))
            self.assertEqual(first_revision["owner"], warm["revision"]["owner"])
            self.assertGreater(warm["evaluations"]["reused"], 0)
            known = [item["identity"] for item in display["assets"]]
            redisplay, warm_buffers = self._result(worker.display(
                warm["revision"], options={"relative_chord": .01, "angular": .5,
                                           "edges": True},
                known=known, timeout=60))
            self.assertEqual([], redisplay["assets"])
            self.assertEqual(1, len(warm_buffers), "the complete manifest is always sent")
            with self.assertRaises(WorkerError):
                worker.inspect(first_revision, [{**reference, "prototype": "forged"}])
            with self.assertRaises(WorkerError):
                worker.inspect(warm["revision"], [reference],
                               space="prototype")
            self.assertTrue(worker.process.is_alive())

            bad_path = self.directory / "bad.py"
            bad_path.write_bytes(BAD_SOURCE)
            with self.assertRaisesRegex(WorkerError, "expected authored failure"):
                worker.generate(CapturedInput.read(bad_path), timeout=60)
            self.assertTrue(worker.process.is_alive())

            with self.assertRaises(WorkerError):
                worker.request("display", lease=first_revision["lease"],
                               options={}, known=["not-a-sha256"])
            self.assertTrue(worker.process.is_alive())
            with self.assertRaises(wire.WireError):
                worker.request("display", lease=first_revision["lease"],
                               options={"angular": float("nan")}, known=[])
            self.assertTrue(worker.process.is_alive())

            multiprocess_path = self.directory / "multiprocess.py"
            multiprocess_path.write_bytes(MULTIPROCESS_SOURCE)
            child, _ = self._result(worker.generate(
                CapturedInput.read(multiprocess_path), timeout=60))
            self._result(worker.release(child["revision"]))
            self._result(worker.release(first_revision))
            self._result(worker.release(warm["revision"]))

    def test_source_and_saved_step_checkpoint_restart_use_exact_captured_bytes(self):
        trace = self.directory / "source-runs.jsonl"
        with patch.dict(os.environ, {"CADGEN_DOCUMENT_BENCH_SOURCE_TRACE": str(trace)}):
            with DocumentWorker(self.catalog, startup_timeout=60) as first:
                source_result, _ = self._result(first.generate(self.source, timeout=60))
                source_revision = source_result["revision"]
                checkpoint, _ = self._result(first.checkpoint(source_revision, timeout=60))
                self.assertTrue(checkpoint["published"])
                saved = CapturedInput.read(self.target)
                opened, _ = self._result(first.open_step(saved, timeout=60))
                saved_revision = opened["revision"]
                saved_checkpoint, _ = self._result(
                    first.checkpoint(saved_revision, timeout=60))
                self.assertTrue(saved_checkpoint["published"])
                source_owner = source_revision["owner"]
                saved_owner = saved_revision["owner"]
                self._result(first.release(source_revision))
                self._result(first.release(saved_revision))

            self.source_path.unlink()
            self.target.write_bytes(b"external replacement after capture")
            with DocumentWorker(self.catalog, startup_timeout=60) as restarted:
                recovered, _ = self._result(restarted.generate(self.source, timeout=60))
                self.assertNotEqual(source_owner, recovered["revision"]["owner"])
                self.assertEqual(0, recovered["evaluations"]["computed"])
                self.assertGreater(recovered["evaluations"]["reused"], 0)
                self.target.write_bytes(b"another replacement before saved import")
                reopened, _ = self._result(restarted.open_step(saved, timeout=60))
                self.assertTrue(reopened["reused"])
                self.assertNotEqual(saved_owner, reopened["revision"]["owner"])
                self.assertEqual(saved.digest, reopened["input"]["digest"])
                self._result(restarted.release(recovered["revision"]))
                self._result(restarted.release(reopened["revision"]))
        self.assertEqual(2, len(trace.read_text().splitlines()),
                         "source replays once per explicit request across recovery")

    def test_cooperative_cancellation_fails_once_and_owner_remains_reusable(self):
        with DocumentWorker(self.catalog, startup_timeout=60) as worker:
            wire.send(worker.control, {"cancel": 1})
            with self.assertRaises(WorkerError) as failure:
                worker.generate(self.source, timeout=60)
            self.assertEqual("Cancelled", failure.exception.details["error"]["type"])
            recovered, _ = self._result(worker.generate(self.source, timeout=60))
            self.assertTrue(worker.process.is_alive())
            self._result(worker.release(recovered["revision"]))

    def test_consumed_success_response_timeout_still_terminates_owner_without_retry(self):
        trace = self.directory / "timeout-runs.jsonl"
        with patch.dict(os.environ, {"CADGEN_DOCUMENT_BENCH_SOURCE_TRACE": str(trace)}):
            worker = DocumentWorker(self.catalog, startup_timeout=60)
            self.addCleanup(worker.close)
            initial, _ = self._result(worker.generate(self.source, timeout=60))
            self._result(worker.release(initial["revision"]))
            original_receive = wire.receive
            calls = 0

            def consume_then_timeout(*args, **kwargs):
                nonlocal calls
                calls += 1
                response = original_receive(*args, **kwargs)
                if calls == 1:
                    raise WorkerTimeout("forced timeout after complete response")
                return response

            with patch.object(wire, "receive", side_effect=consume_then_timeout):
                with self.assertRaises(WorkerTimeout):
                    worker.generate(self.source, timeout=60, cancellation_grace=.1)
            self.assertTrue(worker._closed)
            self.assertFalse(worker.process.is_alive())
        self.assertEqual(2, len(trace.read_text().splitlines()),
                         "timed-out authored work is never retried")

    def test_payload_frame_timeout_tears_down_stream_and_owner(self):
        worker = DocumentWorker(self.catalog, startup_timeout=60)
        self.addCleanup(worker.close)
        generated, _ = self._result(worker.generate(self.source, timeout=60))
        original_wait = worker._wait
        waits = 0

        def fail_payload_wait(deadline):
            nonlocal waits
            waits += 1
            if waits == 2:
                raise WorkerTimeout("forced payload frame timeout")
            return original_wait(deadline)

        with patch.object(worker, "_wait", side_effect=fail_payload_wait):
            with self.assertRaises(WorkerTimeout):
                worker.display(generated["revision"],
                               options={"relative_chord": .01, "angular": .5,
                                        "edges": True},
                               timeout=60)
        self.assertTrue(worker._closed)
        self.assertFalse(worker.process.is_alive())

    def test_parent_death_watch_stops_non_daemon_owner(self):
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        helper = context.Process(target=_abandon_owner,
                                 args=(str(self.catalog), sender))
        helper.start()
        sender.close()
        self.assertTrue(receiver.poll(60), "abandoning client did not report owner pid")
        owner_pid = receiver.recv()
        receiver.close()
        helper.join(10)
        self.assertEqual(0, helper.exitcode)
        self.assertGreater(owner_pid, 0)
        deadline = time.monotonic() + 8
        while _pid_alive(owner_pid) and time.monotonic() < deadline:
            time.sleep(.05)
        if _pid_alive(owner_pid):
            os.kill(owner_pid, signal.SIGTERM)
            self.fail("owner survived its parent-death shutdown deadline")

    def test_owner_loss_during_wait_closes_client_immediately(self):
        worker = DocumentWorker(self.catalog, startup_timeout=60)
        self.addCleanup(worker.close)
        with patch.object(worker, "_wait", side_effect=WorkerError("owner exited")):
            with self.assertRaisesRegex(WorkerError, "owner exited"):
                worker.generate(self.source, timeout=60)
        self.assertTrue(worker._closed)
        self.assertTrue(worker.connection.closed)
        self.assertTrue(worker.control.closed)
        self.assertFalse(worker.process.is_alive())

    def test_elapsed_deadline_cannot_consume_another_ready_frame(self):
        worker = DocumentWorker(self.catalog, startup_timeout=60)
        self.addCleanup(worker.close)
        with patch.object(worker.connection, "poll", return_value=True) as poll:
            with self.assertRaises(WorkerTimeout):
                worker._wait(time.monotonic() - 1)
        poll.assert_not_called()

    def test_client_limits_are_validated_before_process_start_or_request(self):
        for kwargs in ({"max_documents": 0}, {"max_documents": True},
                       {"max_documents": 65}, {"startup_timeout": 0},
                       {"startup_timeout": float("nan")},
                       {"startup_timeout": "soon"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                DocumentWorker(self.catalog, **kwargs)
        with DocumentWorker(self.catalog, startup_timeout=60) as worker:
            for kwargs in ({"timeout": 0}, {"timeout": True},
                           {"timeout": "later"},
                           {"cancellation_grace": -1},
                           {"cancellation_grace": 11}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    worker.request("release", lease="unused", **kwargs)
            with self.assertRaises(ValueError):
                worker.request("unknown")
            self.assertTrue(worker.process.is_alive())


if __name__ == "__main__":
    unittest.main()
