"""Memory admission counts retained parents, pending spawns and subprocesses."""

from __future__ import annotations

import concurrent.futures
import json
import os
import threading
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.daemon import client, memory, pool  # noqa: E402
from tests.python.packages.cadgen.test_daemon_pool import _StubWorker  # noqa: E402

MIB = memory.MIB


class Accounting(unittest.TestCase):
    def test_descendant_rss_is_attributed_once_to_its_worker(self):
        rows = {10: (1, 100), 11: (10, 200), 12: (11, 300),
                20: (1, 400), 21: (20, 500), 30: (1, 900)}
        self.assertEqual(memory.process_tree_bytes([10, 20], rows=rows), {10: 600, 20: 900})

    def test_cycles_and_missing_processes_do_not_hang_or_invent_rss(self):
        rows = {10: (1, 100), 11: (12, 200), 12: (11, 300)}
        self.assertEqual(memory.process_tree_bytes([10, 99], rows=rows), {10: 100})

    def test_policy_reserves_dependency_capacity_and_honors_explicit_zero(self):
        env = {key: "" for key in ("CADGEN_MEMORY_MB", "CADGEN_WORKER_MEMORY_MB",
                                  "CADGEN_DEPENDENCY_MEMORY_MB", "CADGEN_COMPONENT_MEMORY_MB")}
        with mock.patch.dict(os.environ, env), mock.patch.object(memory, "physical_memory_bytes", return_value=12 * 1024 * MIB):
            policy = memory.MemoryPolicy.from_environment()
            self.assertEqual(policy.limit_bytes, 12 * 1024 * MIB * 7 // 10)
            self.assertEqual(policy.dependency_bytes, policy.worker_bytes)
            with mock.patch.dict(os.environ, {"CADGEN_MEMORY_MB": "0"}):
                self.assertEqual(memory.MemoryPolicy.from_environment().limit_bytes, 0)

    def test_component_processes_fit_the_parent_reservation(self):
        policy = memory.MemoryPolicy(8192 * MIB, 2048 * MIB, 2048 * MIB, 384 * MIB)
        with mock.patch.object(memory.MemoryPolicy, "from_environment", return_value=policy):
            with mock.patch.object(memory, "process_tree_bytes", return_value={os.getpid(): 300 * MIB}):
                self.assertEqual(memory.component_worker_limit(8), 4)
                self.assertEqual(memory.component_worker_limit(2), 2)
            with mock.patch.object(memory, "process_tree_bytes", return_value={os.getpid(): 1900 * MIB}):
                self.assertEqual(memory.component_worker_limit(8), 1, "no extra process fits: run inline")


class Admission(unittest.TestCase):
    def setUp(self):
        self.patchers = [mock.patch.object(pool, "Worker", _StubWorker),
                         mock.patch.dict(os.environ, {"CADGEN_DAEMON_SPARES": "0"})]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.resident = {}
        self.policy = memory.MemoryPolicy(12 * MIB, 4 * MIB, 4 * MIB)
        self.pool = pool.Pool(policy=self.policy, memory_reader=lambda pids: {
            pid: self.resident.get(pid, 2 * MIB) for pid in pids
        })
        self.addCleanup(self.pool.shutdown)

    def test_root_admission_leaves_headroom_for_a_dependency(self):
        first = self.pool.acquire("a")
        second = self.pool.acquire("b")
        with self.assertRaises(pool.MemoryAdmissionError):
            self.pool.acquire("root-without-headroom")
        child = self.pool.acquire("child", dependency=True)
        self.assertEqual(self.pool.snapshot()["memory"]["chargedBytes"], 12 * MIB)
        self.assertTrue(all(w.busy and w.alive() for w in (first, second, child)))

    def test_three_level_dependency_can_progress_and_exhaustion_fails_without_evicting_parents(self):
        parent = self.pool.acquire("parent")
        child = self.pool.acquire("child", dependency=True)
        grandchild = self.pool.acquire("grandchild", dependency=True)
        with self.assertRaisesRegex(pool.MemoryAdmissionError, "active builds retain their geometry"):
            self.pool.acquire("too-deep", dependency=True)
        self.assertTrue(all(w.busy and not w.killed for w in (parent, child, grandchild)))

    def test_idle_worker_is_reclaimed_before_new_allocation(self):
        old = self.pool.acquire("old")
        self.pool.release(old)
        self.resident[old.pid] = 6 * MIB
        fresh = self.pool.acquire("new")
        self.assertTrue(old.killed)
        self.assertTrue(fresh.alive())
        self.assertEqual(self.pool.snapshot()["memoryReclaims"], 1)

    def test_oversized_idle_cache_can_be_replaced_with_a_fresh_worker(self):
        old = self.pool.acquire("model")
        self.pool.release(old)
        self.resident[old.pid] = 10 * MIB
        fresh = self.pool.acquire("model")
        self.assertIsNot(old, fresh)
        self.assertTrue(old.killed)
        self.assertFalse(fresh.extra)

    def test_finished_oversized_worker_is_reclaimed_without_another_request(self):
        worker = self.pool.acquire("large")
        self.resident[worker.pid] = 10 * MIB
        self.pool.release(worker)
        self.assertNotIn(worker.pid, [entry["pid"] for entry in self.pool.snapshot()["workers"]])
        self.assertEqual(self.pool.snapshot()["memoryReclaims"], 1)

    def test_a_pending_spawn_keeps_its_reservation(self):
        entered, finish = threading.Event(), threading.Event()

        class StartingWorker(_StubWorker):
            def __init__(self):
                entered.set()
                if not finish.wait(5):
                    raise AssertionError("test never released the pending spawn")
                super().__init__()

        self.pool = pool.Pool(policy=memory.MemoryPolicy(8 * MIB, 4 * MIB, 4 * MIB),
                              memory_reader=lambda pids: {pid: 2 * MIB for pid in pids})
        self.addCleanup(self.pool.shutdown)
        with mock.patch.object(pool, "Worker", StartingWorker), concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(self.pool.acquire, "pending")
            try:
                self.assertTrue(entered.wait(2))
                with self.assertRaises(pool.MemoryAdmissionError):
                    self.pool.acquire("cannot-overbook")
            finally:
                finish.set()
            worker = future.result(timeout=5)
        self.assertTrue(worker.busy)
        self.assertEqual(self.pool.snapshot()["memory"]["pendingWorkers"], 0)

    def test_retiring_rss_is_not_freed_before_process_exit(self):
        old = self.pool.acquire("old")
        self.pool.release(old)
        self.resident[old.pid] = 6 * MIB
        entered, finish = threading.Event(), threading.Event()

        def delayed_kill():
            entered.set()
            finish.wait(5)
            old._alive = False
            old.killed = True

        old.kill = delayed_kill
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(self.pool.acquire, "replacement")
            try:
                self.assertTrue(entered.wait(2))
                self.assertFalse(future.done(), "replacement was admitted while old RSS was still resident")
            finally:
                finish.set()
            fresh = future.result(timeout=5)
        self.assertTrue(fresh.busy and old.killed)

    def test_spare_replenishment_cannot_consume_dependency_reserve(self):
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON_SPARES": "8"}):
            self.pool.ensure_spares()
            with self.pool._cv:
                self.assertLessEqual(self.pool._spares_pending * self.policy.worker_bytes,
                                     self.policy.limit_bytes - self.policy.dependency_bytes)
        # Joining is unnecessary: shutdown also covers workers arriving later.


class DependencyRequest(unittest.TestCase):
    def test_dependency_identity_is_independent_of_coalescing(self):
        with mock.patch.object(client, "compute_version_token", return_value="test"), \
             mock.patch.object(client, "forwarded_env", return_value={}):
            root = client._request_payload("run", ["a.py"], "/work", None, store_root="/cache")
            child = client._request_payload("run", ["b.py"], "/work", None,
                                            store_root="/cache", dependency=True)
        self.assertFalse(root["dependency"])
        self.assertTrue(child["dependency"])
        self.assertFalse(child["coalesce"])

    def test_run_nested_sets_dependency_without_a_closure(self):
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON": "1"}), \
             mock.patch.object(client, "daemon_supported", return_value=True), \
             mock.patch.object(client, "_request_payload", return_value={}) as payload, \
             mock.patch.object(client, "_run_with_retry", return_value=0):
            self.assertEqual(client.run_nested("run", ["b.py"], "/work"), 0)
        self.assertTrue(payload.call_args.kwargs["dependency"])

    def test_server_returns_admission_failure_without_cold_fallback_or_worker_release(self):
        from cadgen.daemon import server

        frames = []
        conn = mock.Mock()
        conn.send.side_effect = lambda data: frames.append(json.loads(data))
        worker_pool = mock.Mock()
        reason = "active builds retain their geometry"
        worker_pool.acquire.side_effect = pool.MemoryAdmissionError(reason)
        ledger, broker = mock.Mock(), mock.Mock()
        job = {"id": "memory-refused"}
        ledger.adopt.return_value = job
        broker.claim.return_value = None
        request = {"tool": "run", "argv": ["child.py"], "cwd": "/work",
                   "dependency": True, "closure": "abc", "coalesce": True}
        with mock.patch.object(server, "_POOL", worker_pool), \
             mock.patch.object(server, "_JOBS", ledger), \
             mock.patch.object(server, "_BROKER", broker), \
             mock.patch.object(server, "_log"):
            server._handle_request(conn, request)
        worker_pool.acquire.assert_called_once_with("/work/child.py", dependency=True)
        worker_pool.release.assert_not_called()
        ledger.finish.assert_called_once_with(job, 1, error=reason)
        broker.finish.assert_called_once_with("/work/child.py", "abc", 1)
        self.assertEqual(frames[-1], {"exit": 1})
        self.assertIn(reason, frames[0]["data"])
        self.assertFalse(any("workerDied" in frame or "restart" in frame for frame in frames))


if __name__ == "__main__":
    unittest.main()
