"""Worker-owned snapshot loop with no Chromium, ffmpeg or CAD kernel work."""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
import io
from pathlib import Path
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

from cadgen.snapshot_core import SnapshotError
from cadgen.snapshot_service import SnapshotService, bind_snapshot_service, current_snapshot_service
from cadgen.store.paths import store_root

CALLER_CONTEXT = ContextVar("snapshot_test_caller", default="empty")


def packet(name="one"):
    return {"single": True, "jobs": [{"input": name, "resolved": {"rootPath": f"/tmp/{name}"}, "outputs": []}]}


class FakeOwner:
    instances = []
    fail_close = False

    def __init__(self, runtime_dir):
        self.runtime_dir = runtime_dir
        self._shutdown_error = None
        self.thread = threading.get_ident()
        self.closed = False
        self.instances.append(self)

    async def close(self):
        if self.fail_close:
            self._shutdown_error = RuntimeError("driver shutdown")
            raise self._shutdown_error
        self.closed = True
        self._shutdown_error = None


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        FakeOwner.instances = []
        FakeOwner.fail_close = False
        self.service = SnapshotService()
        self.addCleanup(self.service.close)
        owner = patch("cadgen.snapshot_service.BatchSnapshotRenderer", FakeOwner)
        owner.start()
        self.addCleanup(owner.stop)
        self.thread = threading.get_ident()

    async def test_explicit_binding_is_lazy_and_two_requests_share_only_the_remote_owner(self):
        self.assertIsNone(current_snapshot_service())
        with bind_snapshot_service(self.service):
            self.assertIs(self.service, current_snapshot_service())
            self.assertIsNone(self.service._thread)
        self.assertIsNone(current_snapshot_service())
        seen, callbacks = [], []
        token = CALLER_CONTEXT.set("caller")
        self.addCleanup(CALLER_CONTEXT.reset, token)
        async def render(value, *, renderer, progress, narrate, **kwargs):
            seen.append((threading.get_ident(), CALLER_CONTEXT.get(), store_root(), value))
            progress.phase("render", total=1)
            progress.detail(value["jobs"][0]["input"])
            progress.advance()
            narrate("progress")
            return value["jobs"][0]["input"]
        def record(*args, **kwargs):
            callbacks.append((threading.get_ident(), CALLER_CONTEXT.get(), args))
        progress = Mock(phase=record, detail=record, advance=record)
        with patch("cadgen.snapshot_service.render_snapshot", render):
            for name in ("one", "two"):
                with patch.dict("os.environ", {"CADGEN_CACHE_DIR": f"/tmp/store-{name}"}):
                    result = await self.service.render(packet(name), runtime_dir=Path("."), progress=progress, narrate=record)
                    self.assertEqual(name, result)
        self.assertEqual(1, len(FakeOwner.instances))
        self.assertTrue(all(row[0] != self.thread and row[1] == "empty" for row in seen))
        self.assertEqual([Path("/tmp/store-one").resolve(), Path("/tmp/store-two").resolve()], [row[2] for row in seen])
        self.assertEqual(8, len(callbacks))
        self.assertTrue(all(row[:2] == (self.thread, "caller") for row in callbacks))
        self.service.close()
        self.assertTrue(FakeOwner.instances[0].closed)
        self.assertFalse(self.service._thread.is_alive())

    async def test_active_cancellation_waits_for_cleanup_receipt_and_releases_reservation(self):
        from cadgen.assets import runtime_root
        from cadgen.snapshot_operation import capture_operation, RenderCleanup
        proof = RenderCleanup()
        operation = capture_operation(packet(), runtime_dir=runtime_root() / "browser", cache_root=store_root())
        started = threading.Event()
        cleanup_started = threading.Event()
        released = threading.Event()
        async def render(value, **kwargs):
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                cleanup_started.set()
                while not released.is_set():
                    await asyncio.sleep(.001)
        with patch("cadgen.snapshot_service.render_snapshot", render):
            task = asyncio.create_task(self.service.render_operation(operation, cleanup=proof))
            await asyncio.to_thread(started.wait, 2)
            task.cancel()
            await asyncio.to_thread(cleanup_started.wait, 2)
            self.assertFalse(task.done())
            self.assertFalse(proof.acknowledged)
            self.assertEqual(1, len(self.service._tickets))
            task.cancel()
            released.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(0, self.service._reserved_bytes)
        self.assertFalse(self.service._tickets)
        self.assertTrue(proof.acknowledged)

    async def test_queued_cancellation_and_capacity_are_bounded_without_starting_another_owner(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        async def render(value, **kwargs):
            calls.append(value)
            entered.set()
            while not release.is_set():
                await asyncio.sleep(.001)
            return True
        with patch("cadgen.snapshot_service.render_snapshot", render), patch("cadgen.snapshot_service.MAX_SERVICE_REQUESTS", 2):
            first = asyncio.create_task(self.service.render(packet(), runtime_dir=Path(".")))
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            original = packet("queued")
            second = asyncio.create_task(self.service.render(original, runtime_dir=Path(".")))
            await asyncio.sleep(.01)
            charged = self.service._reserved_bytes
            self.assertEqual(2, len(self.service._tickets))
            with self.assertRaisesRegex(SnapshotError, "capacity"):
                await self.service.render(packet("full"), runtime_dir=Path("."))
            second.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await second
            self.assertLess(self.service._reserved_bytes, charged)
            self.assertEqual(1, len(self.service._tickets))
            self.assertEqual(1, len(calls))
            release.set()
            await first
        self.assertEqual(0, self.service._reserved_bytes)
        self.assertEqual(1, len(FakeOwner.instances))

    async def test_queued_payload_runtime_store_and_encoder_are_captured_on_caller_thread(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        async def render(value, **kwargs):
            from cadgen.snapshot_video import ffmpeg_binary
            if value["jobs"][0]["input"] == "one":
                entered.set()
                while not release.is_set():
                    await asyncio.sleep(.001)
            calls.append((value, store_root(), kwargs["runtime_dir"], ffmpeg_binary()))
            return True
        with patch("cadgen.snapshot_service.render_snapshot", render), patch("cadgen.snapshot_video.shutil.which", return_value="/tmp/encoder"):
            first = asyncio.create_task(self.service.render(packet(), runtime_dir=Path(".")))
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            queued = packet("two")
            queued["jobs"][0]["video"] = {"fps": 1}
            with patch.dict("os.environ", {"CADGEN_CACHE_DIR": "/tmp/captured-store"}):
                second = asyncio.create_task(self.service.render(queued, runtime_dir=Path("/tmp/runtime")))
                await asyncio.sleep(.01)
            queued["jobs"][0]["resolved"]["rootPath"] = "/tmp/wrong"
            queued["jobs"][0]["video"]["fps"] = 999
            release.set()
            await asyncio.gather(first, second)
        second_call = calls[1]
        self.assertEqual("/tmp/two", second_call[0]["jobs"][0]["resolved"]["rootPath"])
        self.assertEqual(1, second_call[0]["jobs"][0]["video"]["fps"])
        self.assertEqual(Path("/tmp/captured-store").resolve(), second_call[1])
        self.assertEqual(Path("/tmp/runtime").resolve(), second_call[2])
        self.assertEqual("/private/tmp/encoder" if Path("/tmp").resolve() == Path("/private/tmp") else "/tmp/encoder", second_call[3])
        self.assertEqual(2, len(FakeOwner.instances))
        self.assertTrue(FakeOwner.instances[0].closed)

    async def test_callback_failure_cancels_work_then_allows_following_request(self):
        cleaned = threading.Event()
        async def render(value, *, progress, **kwargs):
            try:
                progress.detail("bad callback")
                await asyncio.Event().wait()
            finally:
                cleaned.set()
        progress = Mock(detail=Mock(side_effect=ValueError("callback")))
        with patch("cadgen.snapshot_service.render_snapshot", render):
            with self.assertRaisesRegex(ValueError, "callback"):
                await self.service.render(packet(), runtime_dir=Path("."), progress=progress)
        self.assertTrue(cleaned.is_set())
        with patch("cadgen.snapshot_service.render_snapshot", AsyncMock(return_value="next")):
            self.assertEqual("next", await self.service.render(packet(), runtime_dir=Path(".")))

    async def test_poisoned_owner_never_launches_replacement_and_shutdown_failure_is_loud(self):
        from cadgen.assets import runtime_root
        from cadgen.snapshot_operation import capture_operation, RenderCleanup
        proof = RenderCleanup()
        operation = capture_operation(packet(), runtime_dir=runtime_root() / "browser", cache_root=store_root())
        async def render(value, *, renderer, **kwargs):
            renderer._shutdown_error = RuntimeError("unacknowledged")
            raise SnapshotError("failed cleanup")
        with patch("cadgen.snapshot_service.render_snapshot", render):
            with self.assertRaisesRegex(SnapshotError, "failed cleanup"):
                await self.service.render_operation(operation, cleanup=proof)
        self.assertTrue(self.service.poisoned)
        self.assertFalse(proof.acknowledged)
        with self.assertRaises(SnapshotError):
            await self.service.render(packet(), runtime_dir=Path("."))
        self.assertEqual(1, len(FakeOwner.instances))
        FakeOwner.fail_close = True
        with self.assertRaisesRegex(SnapshotError, "shutdown was not acknowledged"):
            self.service.close()
        self.assertTrue(self.service._thread.is_alive())
        FakeOwner.fail_close = False
        self.service.close()
        self.assertFalse(self.service._thread.is_alive())

    async def test_invalid_or_oversized_requests_are_rejected_before_thread_start(self):
        for bad in ({"jobs": []}, {"jobs": [{"resolved": {"rootPath": "relative"}}]},
                    {"jobs": [{"resolved": {}, "outputs": [{"path": "relative.png"}]}]}):
            with self.assertRaises(SnapshotError):
                await self.service.render(bad, runtime_dir=Path("."))
        with patch("cadgen.snapshot_service.MAX_SERVICE_PACKET_BYTES", 10):
            with self.assertRaisesRegex(SnapshotError, "byte capacity"):
                await self.service.render(packet(), runtime_dir=Path("."))
        self.assertIsNone(self.service._thread)


class WorkerScopeTests(unittest.TestCase):
    def exercise(self, suffix, *, poisoned=False, terminate=False):
        from cadgen.daemon import worker
        import json
        import signal
        fake = Mock(poisoned=poisoned)
        seen, frames = [], []
        requests = [dict(kind="run", tool="inspect", argv=[], cwd="/tmp", store_root="/tmp/cache") for _ in range(2)]
        lines = "".join(json.dumps(value) + "\n" for value in requests) + suffix
        previous_signal = signal.getsignal(signal.SIGTERM)
        def tool(argv):
            seen.append(current_snapshot_service())
            print("request output")
            if terminate:
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            return 1 if poisoned else 0
        with patch("cadgen.snapshot_service.SnapshotService", return_value=fake), \
             patch.object(worker, "_warm_imports"), patch.object(worker, "_emit", frames.append), \
             patch.object(worker, "_tool_main", return_value=tool), patch.object(worker, "_enter", return_value=True), \
             patch.object(worker, "_park"), patch.object(worker, "_evict_first_party_modules"), \
             patch.object(worker, "_apply_request_env"), patch("sys.stdin", io.StringIO(lines)), \
             patch.dict("os.environ", {}, clear=False):
            result = worker.serve()
        fake.close.assert_called_once()
        self.assertIs(previous_signal, signal.getsignal(signal.SIGTERM))
        self.assertIsNone(current_snapshot_service())
        return result, fake, seen, frames

    def test_one_explicit_service_spans_requests_and_closes_on_shutdown_or_eof(self):
        for suffix in ("", '{"kind":"shutdown"}\n'):
            with self.subTest(suffix=suffix):
                result, service, seen, frames = self.exercise(suffix)
                self.assertEqual(0, result)
                self.assertEqual([service, service], seen)
                self.assertEqual([0, 0], [frame["exit"] for frame in frames if "exit" in frame])
                self.assertEqual(2, sum(frame.get("data") == "request output" for frame in frames))

    def test_poison_reclaims_worker_before_another_request(self):
        result, service, seen, frames = self.exercise("", poisoned=True)
        self.assertEqual(1, result)
        self.assertEqual([service], seen)
        self.assertEqual([1], [frame["exit"] for frame in frames if "exit" in frame])

    def test_sigterm_during_tool_stops_after_current_failure_and_closes_owner(self):
        import signal
        result, service, seen, frames = self.exercise("", terminate=True)
        self.assertEqual(128 + signal.SIGTERM, result)
        self.assertEqual([service], seen)

    def test_sigterm_after_normal_exit_emits_exactly_one_bound_shutdown_receipt(self):
        from cadgen.daemon import worker
        import json
        import signal
        fake = Mock(poisoned=False)
        for later_ordinary in (False, True):
            fake.reset_mock()
            frames = []
            requests = [dict(kind="snapshot", tool="snapshot-render", request="captured", argv=[])]
            if later_ordinary:
                requests.append(dict(kind="run", tool="inspect", argv=[]))
            class Input:
                def __iter__(self):
                    for value in requests:
                        yield json.dumps(value)
                    signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            with patch("cadgen.snapshot_service.SnapshotService", return_value=fake), \
                 patch.object(worker, "_warm_imports"), patch.object(worker, "_emit", frames.append), \
                 patch.object(worker, "_run", return_value=0), patch.object(worker, "_apply_request_env"), \
                 patch("sys.stdin", Input()), patch.dict("os.environ", {}, clear=False):
                with self.assertRaises(SystemExit):
                    worker.serve()
            fake.close.assert_called_once()
            receipts = [frame for frame in frames if "snapshotShutdown" in frame]
            self.assertEqual([] if later_ordinary else [{"snapshotShutdown": {"request": "captured", "closed": True}}], receipts)
            self.assertEqual(len(requests), sum("exit" in frame for frame in frames))


class CallerPreparationTests(unittest.TestCase):
    def test_synchronous_cli_preparation_stays_on_caller_and_service_render_is_remote(self):
        from cadgen.snapshot_cli import SnapshotOptions, run_snapshot
        from contextlib import nullcontext
        caller = threading.get_ident()
        stages = []
        service = SnapshotService()
        FakeOwner.instances = []
        FakeOwner.fail_close = False
        self.addCleanup(service.close)
        def resolve(*args, **kwargs):
            stages.append(("resolve", threading.get_ident()))
            return packet()
        async def render(*args, **kwargs):
            stages.append(("render", threading.get_ident()))
            return "complete"
        with patch("cadgen.snapshot_cli.load_job_from_options", return_value={"input": "one.step", "outputs": []}), \
             patch("cadgen.snapshot_cli.clear_render_output_targets"), \
             patch("cadgen.snapshot_cli.resolve_render_job_packet", resolve), \
             patch("cadgen.snapshot_cli.cli_progress_line", return_value=nullcontext(None)), \
             patch("cadgen.snapshot_cli.browser_runtime_dir", return_value=Path("/tmp/runtime")), \
             patch("cadgen.snapshot_service.BatchSnapshotRenderer", FakeOwner), \
             patch("cadgen.snapshot_service.render_snapshot", render), bind_snapshot_service(service):
            for _ in range(2):
                self.assertEqual("complete", run_snapshot(SnapshotOptions(), kinds=("step",)))
        self.assertEqual(1, len(FakeOwner.instances))
        self.assertEqual([caller, caller], [thread for phase, thread in stages if phase == "resolve"])
        self.assertTrue(all(thread != caller for phase, thread in stages if phase == "render"))
        service.close()

    def test_ordinary_library_call_creates_no_service_or_background_pool(self):
        from cadgen.snapshot_cli import SnapshotOptions, run_snapshot
        from contextlib import nullcontext
        with patch("cadgen.snapshot_cli.load_job_from_options", return_value={"input": "one.step", "outputs": []}), \
             patch("cadgen.snapshot_cli.clear_render_output_targets"), \
             patch("cadgen.snapshot_cli.resolve_render_job_packet", return_value=packet()), \
             patch("cadgen.snapshot_cli.cli_progress_line", return_value=nullcontext(None)), \
             patch("cadgen.snapshot_cli.browser_runtime_dir", return_value=Path("/tmp/runtime")), \
             patch("cadgen.snapshot_cli.render_snapshot", AsyncMock(return_value="standalone")) as render, \
             patch("cadgen.snapshot_service.SnapshotService", side_effect=AssertionError("hidden service")):
            self.assertEqual("standalone", run_snapshot(SnapshotOptions(), kinds=("step",)))
        render.assert_awaited_once()
