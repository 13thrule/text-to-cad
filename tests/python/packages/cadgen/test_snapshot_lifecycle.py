"""Browser ownership, immutable job capabilities and cancellation without Chromium."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from cadgen.snapshot_core import BatchSnapshotRenderer, SnapshotError, render_resolved_job_packet
from cadgen.store.paths import store_root


class FakeAssets:
    instances = []

    def __init__(self, root):
        self.root = root
        self.store = store_root()
        self.closed = False
        self.base_url = f"http://127.0.0.1:12000/job-{len(self.instances)}"
        self.instances.append(self)

    def close(self):
        self.closed = True


class FakePage:
    def __init__(self, runtime):
        self.runtime = runtime
        self.calls = []
        self.handler = None

    async def route(self, glob, handler):
        self.handler = handler
        await self.runtime.step("route")

    async def goto(self, url, **kwargs):
        self.calls.append(("goto", url))
        await self.runtime.step("goto")

    async def wait_for_function(self, *args, **kwargs):
        await self.runtime.step("ready")

    async def set_viewport_size(self, size):
        self.calls.append(("size", size))

    async def evaluate(self, code, job=None):
        self.calls.append(("evaluate", code))
        self.calls.append(("job", job))
        await self.runtime.step("evaluate")
        return {"ok": True, "outputs": []}


class FakeContext:
    def __init__(self, runtime):
        self.runtime = runtime
        self.closed = False
        self.scripts = []
        self.page = FakePage(runtime)

    async def add_init_script(self, script):
        self.scripts.append(script)
        await self.runtime.step("init")

    async def new_page(self):
        await self.runtime.step("page")
        return self.page

    async def close(self):
        await self.runtime.step("context-close")
        self.closed = True


class FakeBrowser:
    def __init__(self, runtime):
        self.runtime = runtime
        self.connected = True
        self.closed = False
        self.contexts = []

    def is_connected(self):
        return self.connected

    async def new_context(self, **kwargs):
        await self.runtime.step("context")
        context = FakeContext(self.runtime)
        self.contexts.append(context)
        return context

    async def close(self):
        await self.runtime.step("browser-close")
        self.connected = False
        self.closed = True


class FakeRuntime:
    def __init__(self):
        self.browsers = []
        self.providers = []
        self.failure = None
        self.block = None
        self.entered = asyncio.Event()
        self.unblock = asyncio.Event()
        self.partial_stops = 0

    async def step(self, phase):
        if self.failure == phase:
            self.failure = None
            raise RuntimeError(phase)
        if self.block == phase:
            self.entered.set()
            await self.unblock.wait()

    async def launch(self, **kwargs):
        await self.step("launch")
        browser = FakeBrowser(self)
        self.browsers.append(browser)
        return browser

    async def start(self):
        await self.step("handshake")
        provider = SimpleNamespace(chromium=SimpleNamespace(launch=self.launch), stop=AsyncMock())
        self.providers.append(provider)
        return provider

    async def __aexit__(self):
        self.partial_stops += 1


class SnapshotLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        FakeAssets.instances = []
        self.runtime = FakeRuntime()
        self.owner = BatchSnapshotRenderer(Path("."))
        for target, value in (
            ("cadgen.snapshot_core.SnapshotAssetServer", FakeAssets),
            ("playwright.async_api.async_playwright", lambda: self.runtime),
        ):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addAsyncCleanup(self.owner.close)

    def job(self, name="one"):
        return {"input": name, "resolved": {"rootPath": f"/tmp/{name}"}, "outputs": []}

    async def test_injected_owner_reuses_only_browser_across_packets_and_roots(self):
        for name in ("one", "two"):
            with patch.dict("os.environ", {"CADGEN_CACHE_DIR": f"/tmp/store-{name}"}):
                await render_resolved_job_packet({"single": True, "jobs": [self.job(name)]},
                                                 runtime_dir=Path("."), renderer=self.owner)
        self.assertEqual(1, len(self.runtime.browsers))
        browser = self.runtime.browsers[0]
        self.assertEqual(2, len(browser.contexts))
        self.assertTrue(all(context.closed for context in browser.contexts))
        self.assertIsNone(self.owner.page)
        self.assertIsNone(self.owner.asset_server)
        self.assertFalse(browser.closed)
        self.assertEqual([Path("/tmp/one").resolve(), Path("/tmp/two").resolve()],
                         [asset.root for asset in FakeAssets.instances])
        self.assertEqual([Path("/tmp/store-one").resolve(), Path("/tmp/store-two").resolve()],
                         [asset.store for asset in FakeAssets.instances])
        self.assertTrue(all(asset.closed for asset in FakeAssets.instances))
        for context, asset in zip(browser.contexts, FakeAssets.instances):
            self.assertIn(asset.base_url, context.scripts[0])
        await self.owner.close()
        self.assertTrue(browser.closed)
        self.runtime.providers[0].stop.assert_awaited_once()

    async def test_packet_closes_owner_it_creates(self):
        with patch("cadgen.snapshot_core.BatchSnapshotRenderer", return_value=self.owner):
            await render_resolved_job_packet({"single": True, "jobs": [self.job()]}, runtime_dir=Path("."))
        self.assertTrue(self.runtime.browsers[0].closed)
        with self.assertRaisesRegex(SnapshotError, "closed"):
            await self.owner.render(self.job())

    async def test_each_startup_failure_and_render_failure_releases_then_next_job_succeeds(self):
        for phase in ("launch", "context", "init", "page", "route", "goto", "ready", "evaluate"):
            with self.subTest(phase=phase):
                self.runtime.failure = phase
                with self.assertRaisesRegex(RuntimeError, phase):
                    await self.owner.render(self.job())
                self.assertIsNone(self.owner.context)
                self.assertIsNone(self.owner.browser)
                self.assertTrue(FakeAssets.instances[-1].closed)
                self.assertTrue((await self.owner.render(self.job()))["ok"])

    async def test_cancelled_render_releases_context_browser_and_capability_before_next_job(self):
        self.runtime.block = "evaluate"
        task = asyncio.create_task(self.owner.render(self.job()))
        await asyncio.wait_for(self.runtime.entered.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.runtime.browsers[0].contexts[0].closed)
        self.assertTrue(self.runtime.browsers[0].closed)
        self.assertTrue(FakeAssets.instances[0].closed)
        self.runtime.block = None
        await self.owner.render(self.job("two"))
        self.assertEqual(2, len(self.runtime.browsers))

    async def test_job_timeout_releases_the_page_that_may_still_have_javascript_running(self):
        self.runtime.block = "evaluate"
        with self.assertRaisesRegex(SnapshotError, "timed out"):
            await self.owner.render({**self.job(), "timeoutSeconds": 1})
        self.assertTrue(self.runtime.browsers[0].contexts[0].closed)
        self.assertTrue(self.runtime.browsers[0].closed)
        self.assertTrue(FakeAssets.instances[0].closed)

    async def test_partial_driver_start_and_launch_timeouts_release_their_owner(self):
        for phase in ("handshake", "launch"):
            with self.subTest(phase=phase), patch("cadgen.snapshot_core.RENDER_BROWSER_STARTUP_TIMEOUT_MS", 10):
                self.runtime.block = phase
                with self.assertRaises(asyncio.TimeoutError):
                    await self.owner.render(self.job())
                self.assertIsNone(self.owner._playwright_manager)
                self.assertTrue(FakeAssets.instances[-1].closed)
        self.assertEqual(1, self.runtime.partial_stops)
        self.runtime.providers[0].stop.assert_awaited_once()
        self.runtime.block = None
        await self.owner.render(self.job())

    async def test_repeated_cancellation_during_context_disposal_finishes_cleanup(self):
        self.runtime.block = "context-close"
        task = asyncio.create_task(self.owner.render(self.job()))
        await asyncio.wait_for(self.runtime.entered.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        self.runtime.unblock.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.runtime.browsers[0].contexts[0].closed)
        self.assertTrue(FakeAssets.instances[0].closed)
        self.assertTrue(self.runtime.browsers[0].closed)

    async def test_stalled_context_close_discards_browser_with_bounded_wait(self):
        self.runtime.block = "context-close"
        with patch("cadgen.snapshot_core.RENDER_BROWSER_CLOSE_SECONDS", .01):
            await self.owner.render(self.job())
        self.assertTrue(self.runtime.browsers[0].closed)
        self.assertTrue(FakeAssets.instances[0].closed)
        self.runtime.block = None
        await self.owner.render(self.job("two"))
        self.assertEqual(2, len(self.runtime.browsers))

    async def test_idle_expiry_and_disconnect_retire_browser_before_later_job(self):
        with patch("cadgen.snapshot_core.RENDER_BROWSER_IDLE_SECONDS", .01):
            await self.owner.render(self.job())
            await asyncio.sleep(.03)
        self.assertTrue(self.runtime.browsers[0].closed)
        await self.owner.render(self.job("two"))
        self.runtime.browsers[1].connected = False
        await self.owner.render(self.job("three"))
        self.assertEqual(3, len(self.runtime.browsers))
        self.assertTrue(self.runtime.browsers[1].closed)

    async def test_owner_close_cancels_active_job_and_does_not_leave_pending_idle_work(self):
        self.runtime.block = "evaluate"
        task = asyncio.create_task(self.owner.render(self.job()))
        await asyncio.wait_for(self.runtime.entered.wait(), 2)
        await self.owner.close()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.runtime.browsers[0].closed)
        self.assertIsNone(self.owner._idle_handle)
        self.assertTrue(FakeAssets.instances[0].closed)

    async def test_concurrent_submissions_serialize_and_late_routes_keep_old_capability(self):
        self.runtime.block = "evaluate"
        first = asyncio.create_task(self.owner.render(self.job("one")))
        await asyncio.wait_for(self.runtime.entered.wait(), 2)
        old_handler = self.owner.page.handler
        second = asyncio.create_task(self.owner.render(self.job("two")))
        await asyncio.sleep(0)
        self.assertEqual(1, len(self.runtime.browsers[0].contexts))
        self.runtime.block = None
        self.runtime.unblock.set()
        await asyncio.gather(first, second)
        route = SimpleNamespace(request=SimpleNamespace(method="GET", url="http://localhost/__render_asset/file"),
                                fulfill=AsyncMock())
        await old_handler(route)
        self.assertEqual(FakeAssets.instances[0].base_url + "/__render_asset/file",
                         route.fulfill.call_args.kwargs["headers"]["location"])
        self.assertNotIn(FakeAssets.instances[1].base_url, str(route.fulfill.call_args))
        for url, method, status in (("http://localhost.evil/__render_asset/file", "GET", 403),
                                    ("http://localhost/__render_asset/file", "POST", 405)):
            route.request = SimpleNamespace(method=method, url=url)
            await old_handler(route)
            self.assertEqual(status, route.fulfill.call_args.kwargs["status"])

    async def test_queued_job_detaches_all_values_before_caller_mutation(self):
        self.runtime.block = "evaluate"
        first = asyncio.create_task(self.owner.render(self.job("one")))
        await asyncio.wait_for(self.runtime.entered.wait(), 2)
        original = {**self.job("two"), "timeoutSeconds": 9,
                    "camera": {"position": [1, 2, 3]},
                    "outputs": [{"width": 80, "height": 60}]}
        second = asyncio.create_task(self.owner.render(original))
        await asyncio.sleep(0)
        original["resolved"]["rootPath"] = "/tmp/wrong"
        original["camera"]["position"][0] = 999
        original["outputs"][0]["width"] = 999
        original["timeoutSeconds"] = .01
        self.runtime.block = None
        self.runtime.unblock.set()
        await asyncio.gather(first, second)
        page = self.runtime.browsers[0].contexts[1].page
        captured = next(value for kind, value in page.calls if kind == "job")
        self.assertEqual("/tmp/two", captured["resolved"]["rootPath"])
        self.assertEqual([1, 2, 3], captured["camera"]["position"])
        self.assertEqual(80, captured["outputs"][0]["width"])
        self.assertEqual(9, captured["timeoutSeconds"])
        self.assertEqual(Path("/tmp/two").resolve(), FakeAssets.instances[1].root)

    async def test_closed_job_validation_does_not_call_arbitrary_copy_or_iteration(self):
        class Custom(dict):
            def __iter__(self):
                raise AssertionError("author iteration")
            def __deepcopy__(self, memo):
                raise AssertionError("author copying")
        for bad in (Custom(), {"camera": Custom()}, {"outputs": [object()]}, {"camera": float("nan")}):
            with self.assertRaises(SnapshotError):
                await self.owner.render(bad)
        cyclic = {}
        cyclic["self"] = cyclic
        with self.assertRaisesRegex(SnapshotError, "cycles"):
            await self.owner.render(cyclic)
        self.assertFalse(self.runtime.browsers)

    async def test_dual_teardown_failure_is_observed_retains_handles_and_refuses_new_jobs(self):
        with patch("cadgen.snapshot_core.RENDER_BROWSER_IDLE_SECONDS", .01):
            await self.owner.render(self.job())
            browser = self.runtime.browsers[0]
            provider = self.runtime.providers[0]
            provider.stop.side_effect = RuntimeError("driver teardown")
            with patch.object(browser, "close", AsyncMock(side_effect=RuntimeError("browser teardown"))):
                await asyncio.sleep(.03)
                self.assertIsNotNone(self.owner._shutdown_error)
                self.assertIs(browser, self.owner.browser)
                self.assertIs(provider, self.owner.playwright)
                self.assertIsNone(self.owner._idle_task.exception())
                with self.assertRaisesRegex(SnapshotError, "teardown failed"):
                    await self.owner.render(self.job("refused"))
                self.assertEqual(1, len(self.runtime.browsers))
                with self.assertRaisesRegex(SnapshotError, "teardown failed"):
                    await self.owner.close()
            provider.stop.side_effect = None
            await self.owner.close()
            self.assertIsNone(self.owner.browser)
            self.assertIsNone(self.owner.playwright)

    async def test_driver_shutdown_acknowledgement_covers_disconnected_browser_close_failure(self):
        await self.owner.render(self.job())
        browser = self.runtime.browsers[0]
        with patch.object(browser, "close", AsyncMock(side_effect=RuntimeError("disconnected"))):
            await self.owner.close()
        self.runtime.providers[0].stop.assert_awaited_once()
        self.assertIsNone(self.owner._shutdown_error)
        self.assertIsNone(self.owner.browser)

    async def test_video_and_still_use_separate_contexts_and_failed_video_cannot_poison_next(self):
        import base64
        pages = []
        async def video_evaluate(page, code, arg=None):
            pages.append(page)
            await self.runtime.step("evaluate")
            if "__snapshotRenderSequence(" in code:
                return {"ok": True, "frames": 1, "fps": 1, "seconds": 1, "start": 0}
            if "__snapshotRenderSequenceFrame" in code:
                return {"dataUrl": "data:image/png;base64," + base64.b64encode(b"png").decode(), "camera": "iso"}
            return {"ok": True, "outputs": []}
        job = {**self.job(), "video": {"fps": 1, "quality": "normal"},
               "outputs": [{"path": "/tmp/fake.mp4", "width": 10, "height": 10}]}
        with patch.object(FakePage, "evaluate", video_evaluate), patch(
                "cadgen.snapshot_video.encode_video", new_callable=AsyncMock):
            await self.owner.render_video(job)
            await self.owner.render(self.job("still"))
            self.assertEqual(1, len(self.runtime.browsers))
            self.assertEqual(2, len(self.runtime.browsers[0].contexts))
            self.assertIsNot(pages[0], pages[-1])
            self.runtime.failure = "evaluate"
            with self.assertRaisesRegex(RuntimeError, "evaluate"):
                await self.owner.render_video(job)
            self.assertTrue(self.runtime.browsers[0].closed)
            await self.owner.render(self.job("next"))
            self.assertEqual(2, len(self.runtime.browsers))


class SnapshotOwnerLoopTests(unittest.TestCase):
    def test_browser_owner_cannot_move_between_event_loops(self):
        owner = BatchSnapshotRenderer(Path("."))
        first, second = asyncio.new_event_loop(), asyncio.new_event_loop()
        try:
            async def bind():
                owner._bind_loop()
            first.run_until_complete(bind())
            with self.assertRaisesRegex(SnapshotError, "owning event loop"):
                second.run_until_complete(bind())
            first.run_until_complete(owner.close())
        finally:
            first.close()
            second.close()


class AsyncEncoderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import tempfile
        self.temporary = tempfile.TemporaryDirectory(prefix="snapshot-encoder-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "result.mp4"
        self.options = dict(output_path=self.output, fps=30, container="mp4", quality="review", loop=True, binary="fake-ffmpeg")

    def process(self, *, status=None, ignore_terminate=False, stderr=b""):
        finished = asyncio.Event()
        if status is not None:
            finished.set()
        stream = asyncio.StreamReader()
        stream.feed_data(stderr)
        stream.feed_eof()
        process = SimpleNamespace(returncode=status, stderr=stream, terminated=0, killed=0, waited=0)
        async def wait():
            process.waited += 1
            await finished.wait()
            return process.returncode
        def terminate():
            process.terminated += 1
            if not ignore_terminate:
                process.returncode = -15
                finished.set()
        def kill():
            process.killed += 1
            process.returncode = -9
            finished.set()
        process.wait, process.terminate, process.kill = wait, terminate, kill
        return process

    async def test_encoding_cancellation_terminates_kills_and_reaps_before_removing_stage(self):
        from cadgen.snapshot_video import encode_video
        process = self.process(ignore_terminate=True)
        entered = asyncio.Event()
        async def launch(*argv, **kwargs):
            Path(argv[-1]).write_bytes(b"partial")
            entered.set()
            return process
        with patch("asyncio.create_subprocess_exec", launch), patch("cadgen.snapshot_video.VIDEO_ENCODER_STOP_SECONDS", .01):
            task = asyncio.create_task(encode_video(self.root, **self.options))
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual((1, 1), (process.terminated, process.killed))
        self.assertGreaterEqual(process.waited, 3)
        self.assertEqual([], list(self.root.iterdir()))

    async def test_success_publishes_exact_completed_file_and_error_keeps_only_bounded_stderr(self):
        from cadgen.snapshot_video import encode_video, MP4_QUALITY_SETTINGS
        self.options["quality"] = next(iter(MP4_QUALITY_SETTINGS))
        process = self.process(status=0)
        commands = []
        async def launch(*argv, **kwargs):
            commands.append(argv)
            Path(argv[-1]).write_bytes(b"complete")
            return process
        with patch("asyncio.create_subprocess_exec", launch):
            await encode_video(self.root, **self.options)
        self.assertEqual(b"complete", self.output.read_bytes())
        self.assertIn("-nostdin", commands[0])
        self.output.unlink()
        process = self.process(status=1, stderr=b"x" * (1024 * 1024) + b"\nfinal diagnostic")
        with patch("asyncio.create_subprocess_exec", launch):
            with self.assertRaisesRegex(SnapshotError, "final diagnostic") as caught:
                await encode_video(self.root, **self.options)
        self.assertLess(len(str(caught.exception)), 66000)
        self.assertEqual([], list(self.root.iterdir()))
