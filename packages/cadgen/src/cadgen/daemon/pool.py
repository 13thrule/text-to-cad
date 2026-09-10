"""The warm worker pool: a worker per model, an extra when it is busy, spares in reserve.

One rule decides routing here: **nothing waits on another build.** A request
for a model whose worker is idle takes that worker. A request for a model whose
worker is busy gets an *extra* — a spare bound to the same model for the length
of one job — and runs now. A request for a model with no worker binds a spare. A
request with no spare left spawns if its memory reservation fits. Admission
counts resident worker trees (including extraction children), keeps headroom
for dependencies, and reclaims idle workers first. Exhaustion fails explicitly
rather than waiting while a parent retains geometry. These are soft RSS and
reservation bounds, not a hard limit on a native operation's allocations.
Publication ordering remains the publish rule's concern.

Spares: ``CADGEN_DAEMON_SPARES`` (default 2) workers that have finished importing
build123d and are bound to nothing. Binding one starts a replacement in the
background when memory permits, so a new model's first build pays no import.
An extra returns to the spare set when its job ends; a primary stays bound
until idle timeout, memory pressure or recycling reclaims it.

Recycle: a worker is dropped after ``CADGEN_DAEMON_RECYCLE`` jobs (default 1000)
as a leak hedge; its model binds a fresh worker on the next request.

Workers read frames on a thread so every read honours a timeout: a worker that
hangs before announcing itself, or mid-job, is reported instead of blocking its
caller forever.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import queue
import subprocess
import sys
import threading
import time

from cadgen.daemon.memory import MemoryPolicy, MIB, process_tree_bytes

DEFAULT_SPARES = 2
DEFAULT_RECYCLE_AFTER = 1000
DEFAULT_IDLE_UNBIND_SECONDS = 600.0
SPAWN_TIMEOUT_SECONDS = 120.0
_USE_SEQUENCE = itertools.count()


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def spare_count() -> int:
    value = _env_int("CADGEN_DAEMON_SPARES")
    return max(0, value) if value is not None else DEFAULT_SPARES


def recycle_after() -> int:
    value = _env_int("CADGEN_DAEMON_RECYCLE")
    return max(1, value) if value is not None else DEFAULT_RECYCLE_AFTER


def idle_unbind_seconds() -> float:
    raw = os.environ.get("CADGEN_DAEMON_IDLE_UNBIND", "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return DEFAULT_IDLE_UNBIND_SECONDS


class WorkerGone(RuntimeError):
    """The worker process ended, or its pipe closed, before the job produced its
    terminal frame. Carries the wait status when the process has been reaped."""

    def __init__(self, message: str, *, exit_status: int | None = None) -> None:
        super().__init__(message)
        self.exit_status = exit_status


class MemoryAdmissionError(RuntimeError):
    """A worker reservation could not fit after idle resources were reclaimed."""


_NTSTATUS_NAMES = {
    0xC0000005: "STATUS_ACCESS_VIOLATION",
    0xC00000FD: "STATUS_STACK_OVERFLOW",
    0xC0000409: "STATUS_STACK_BUFFER_OVERRUN",
    0xC0000374: "STATUS_HEAP_CORRUPTION",
    0xC000013A: "STATUS_CONTROL_C_EXIT",
}


def describe_exit(status: int | None) -> str:
    """A worker's death in words: the signal that killed it, or its exit code."""
    if status is None:
        return "closed its output while still running"
    if status < 0:
        import signal

        number = -status
        try:
            name = signal.Signals(number).name
        except ValueError:
            return f"was killed by signal {number}"
        return f"was killed by {name} (signal {number})"
    if os.name == "nt" or status > 255:
        unsigned = status & 0xFFFFFFFF
        name = _NTSTATUS_NAMES.get(unsigned)
        if name:
            return f"exited with 0x{unsigned:08X} ({name})"
        return f"exited with code {status}"
    return f"exited with code {status}"


_TIMED_OUT = object()  # _read_frame: the wait elapsed; distinct from None (pipe closed)


class Worker:
    """One warm subprocess. Owned by the pool; never shared between concurrent jobs."""

    def __init__(self) -> None:
        from cadgen.daemon.client import daemon_address
        from cadgen.daemon.executors import worker_env

        env = worker_env()
        # The broker a worker's jobs take slots from is the daemon itself; name the
        # address explicitly so a worker never guesses it from its identity.
        env["CADGEN_DAEMON_SOCKET"] = daemon_address()
        # A daemon's worker submits its children to the daemon, whatever the process
        # that started the daemon had in its environment.
        env.pop("CADGEN_DAEMON", None)
        # Guards against a worker's own top-level call routing back into the daemon
        # as a fresh request; nested SUBMITS ignore this on purpose (client.run_nested).
        env["CADGEN_DAEMON_CHILD"] = "1"
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "cadgen.daemon.worker"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
            # utf-8 EXPLICITLY: this pipe carries JSON frames and the worker encodes
            # utf-8 (worker.serve), so neither end infers the platform code page.
            env=env, text=True, encoding="utf-8", errors="backslashreplace", bufsize=1,
        )
        self.jobs_served = 0
        self.busy = False
        self.extra = False
        self.last_used = time.monotonic()
        self.use_seq = next(_USE_SEQUENCE)
        # The MODEL this worker is bound to (its script path), "" while a spare.
        self.model = ""
        self._frames: queue.Queue = queue.Queue()
        self._reader = threading.Thread(target=self._pump, name="cadgen-worker-frames", daemon=True)
        self._reader.start()
        ready = self._read_frame(timeout=SPAWN_TIMEOUT_SECONDS)
        if ready is _TIMED_OUT:
            ready = None
        if not ready or "ready" not in ready:
            self.kill()
            raise WorkerGone(
                "worker did not announce itself" + ("" if ready else f" within {SPAWN_TIMEOUT_SECONDS:.0f}s")
            )
        self.pid = int(ready["ready"])

    def _pump(self) -> None:
        stream = self.proc.stdout
        if stream is None:
            self._frames.put(None)
            return
        for line in stream:
            try:
                self._frames.put(json.loads(line))
            except ValueError:
                self._frames.put({"stream": "stderr", "data": line})
        self._frames.put(None)

    def _read_frame(self, timeout: float | None = None) -> dict | None | object:
        """The next frame; None when the pipe closed; ``_TIMED_OUT`` when ``timeout`` elapsed.

        The two are told apart on purpose: a worker that died is reported by its
        exit status, a worker that is merely quiet by the silence timeout. Folding
        them into one None let a SIGKILLed worker read as "went silent" whenever
        its pipe's EOF arrived a beat before the kernel let it be reaped.
        """
        try:
            return self._frames.get(timeout=timeout)
        except queue.Empty:
            return _TIMED_OUT

    def send(self, request: dict) -> None:
        if self.proc.poll() is not None or self.proc.stdin is None:
            raise WorkerGone("worker is not running")
        try:
            self.proc.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise WorkerGone(f"worker stdin closed: {exc}") from exc

    def frames(self, *, silence_timeout: float | None = None):
        """Yield frames until the terminating one, which is yielded last.

        ``silence_timeout`` bounds the wait for ANY frame; a worker silent that
        long is reported as gone (its process is killed) rather than waited for.
        """
        while True:
            frame = self._read_frame(timeout=silence_timeout)
            if frame is _TIMED_OUT:
                self.kill()
                raise WorkerGone(
                    f"worker {getattr(self, 'pid', self.proc.pid)} went silent for "
                    f"{silence_timeout:.0f}s and was killed"
                )
            if frame is None:
                status = self._exit_status()
                raise WorkerGone(
                    f"worker {getattr(self, 'pid', self.proc.pid)} {describe_exit(status)}",
                    exit_status=status,
                )
            yield frame
            if "exit" in frame or "pong" in frame:
                return

    def _exit_status(self) -> int | None:
        try:
            return self.proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            return None

    def alive(self) -> bool:
        return self.proc.poll() is None

    def kill(self) -> None:
        proc = self.proc
        try:
            if proc.poll() is None:
                if proc.stdin is not None:
                    with contextlib.suppress(OSError):
                        proc.stdin.close()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
        except OSError:
            pass
        finally:
            for stream in (proc.stdin, proc.stdout):
                if stream is not None:
                    with contextlib.suppress(OSError):
                        stream.close()


class Pool:
    """See the module docstring."""

    def __init__(self, clock=time.monotonic, *, policy: MemoryPolicy | None = None, memory_reader=None) -> None:
        self._cv = threading.Condition()
        self._clock = clock
        self._workers: list[Worker] = []
        self._retiring: list[Worker] = []
        self._active_pending = 0
        self._spares_pending = 0
        self._policy = policy if policy is not None else MemoryPolicy.from_environment()
        self._memory_reader = memory_reader or process_tree_bytes
        self._stats = {"jobsServed": 0, "imports": 0, "concurrent": 0, "crashes": 0, "recycles": 0, "unbinds": 0,
                       "memoryReclaims": 0, "memoryRefusals": 0}
        self._closed = False

    # --- spares -------------------------------------------------------------------

    def _spawn(self) -> Worker:
        worker = Worker()
        with self._cv:
            self._stats["imports"] += 1
        return worker

    def _spares_locked(self) -> list[Worker]:
        return [w for w in self._workers if not w.model and not w.busy]

    def ensure_spares(self) -> None:
        """Top the spare set up to ``spare_count()`` in the background."""
        with self._cv:
            if self._closed:
                return
            want = spare_count() - len(self._spares_locked()) - self._spares_pending
            if self._policy.limit_bytes:
                usage = self._memory_locked()["chargedBytes"]
                available = self._policy.limit_bytes - self._policy.dependency_bytes - usage
                want = min(want, max(0, available // self._policy.worker_bytes))
            if want <= 0:
                return
            self._spares_pending += want

        def fill(count: int) -> None:
            for _ in range(count):
                try:
                    worker = self._spawn()
                except WorkerGone:
                    worker = None
                with self._cv:
                    self._spares_pending -= 1
                    if worker is not None:
                        if self._closed:
                            worker.kill()
                        else:
                            self._workers.append(worker)
                    self._cv.notify_all()

        threading.Thread(target=fill, args=(want,), name="cadgen-spares", daemon=True).start()

    def _take_spare_locked(self) -> Worker | None:
        spares = self._spares_locked()
        return spares[0] if spares else None

    # --- acquire / release -------------------------------------------------------

    def acquire(self, model: str = "", *, dependency: bool = False) -> Worker:
        """A worker for ``model``, or an explicit memory-admission failure.

        ``model`` is the script path (the routing key); "" means a request with
        no model subject, which borrows a spare without binding it.
        """
        with self._cv:
            if self._closed:
                raise WorkerGone("worker pool is closed")
            self._reap_dead_locked()
            bound = []
            worker = None
            if model:
                bound = [w for w in self._workers if w.model == model and not w.extra]
                idle = [w for w in bound if not w.busy]
                if idle:
                    worker = idle[0]
            if worker is None:
                worker = self._take_spare_locked()
            if worker is not None:
                worker.busy = True  # reserve before releasing the bookkeeping lock
            try:
                self._admit_locked(additional=0 if worker else self._policy.worker_bytes, dependency=dependency)
            except MemoryAdmissionError:
                if worker is not None:
                    worker.busy = False
                    # Its retained cache may itself be the pressure. This was
                    # idle before our reservation, so retry with a fresh worker.
                    self._stats["memoryReclaims"] += 1
                    self._drop_locked(worker)
                    worker = None
                    self._admit_locked(additional=self._policy.worker_bytes, dependency=dependency)
                else:
                    raise
            if worker is None:
                self._active_pending += 1
        if worker is None:
            try:
                worker = self._spawn()
            except BaseException:
                with self._cv:
                    self._active_pending -= 1
                    self._cv.notify_all()
                raise
            with self._cv:
                self._active_pending -= 1
                if self._closed:
                    worker.kill()
                    raise WorkerGone("worker pool closed while starting a worker")
                worker.busy = True
                self._workers.append(worker)
        with self._cv:
            worker.busy = True
            if model:
                was_bound = worker in bound
                worker.model = model
                # An extra when a primary already exists; a primary otherwise.
                worker.extra = not was_bound and any(
                    w is not worker and w.model == model and not w.extra for w in self._workers
                )
                if worker.extra:
                    self._stats["concurrent"] += 1
            else:
                worker.extra = True  # borrowed; returns to the spare set on release
            self._used_locked(worker)
        self.ensure_spares()
        return worker

    def _memory_locked(self) -> dict:
        self._retiring[:] = [w for w in self._retiring if w.alive()]
        workers = [*self._workers, *self._retiring]
        measured = self._memory_reader([w.pid for w in workers]) if self._policy.limit_bytes else {}
        resident = sum(measured.values())
        charged = sum(
            max(measured.get(w.pid, self._policy.worker_bytes), self._policy.worker_bytes if w.busy else 0)
            for w in workers
        )
        pending = self._active_pending + self._spares_pending
        retiring_bytes = sum(measured.get(w.pid, self._policy.worker_bytes) for w in self._retiring)
        return {"limitBytes": self._policy.limit_bytes, "residentBytes": resident,
                "chargedBytes": charged + pending * self._policy.worker_bytes,
                "workerReservationBytes": self._policy.worker_bytes,
                "dependencyReserveBytes": self._policy.dependency_bytes,
                "measuredWorkers": len(measured), "unmeasuredWorkers": len(workers) - len(measured),
                "pendingWorkers": pending, "retiringWorkers": len(self._retiring),
                "retiringBytes": retiring_bytes}

    def _reclaim_pressure_locked(self) -> None:
        """Trim newly idle retained caches without waiting for active work."""
        if not self._policy.limit_bytes:
            return
        snapshot = self._memory_locked()
        # Already-retiring workers are charged for admission until they exit,
        # but must not cause us to schedule the same reclamation twice.
        planned = snapshot["chargedBytes"] - snapshot["retiringBytes"]
        ceiling = self._policy.limit_bytes - self._policy.dependency_bytes
        idle = sorted((w for w in self._workers if not w.busy), key=lambda w: w.use_seq)
        measured = self._memory_reader([w.pid for w in idle])
        for worker in idle:
            if planned <= ceiling:
                break
            planned -= measured.get(worker.pid, self._policy.worker_bytes)
            self._stats["memoryReclaims"] += 1
            self._drop_locked(worker)

    def _admit_locked(self, *, additional: int, dependency: bool) -> None:
        if not self._policy.limit_bytes:
            return
        ceiling = self._policy.limit_bytes - (0 if dependency else self._policy.dependency_bytes)
        deadline = time.monotonic() + 5.0  # wait only for idle-process teardown
        while True:
            usage = self._memory_locked()["chargedBytes"]
            if usage + additional <= ceiling:
                return
            idle = sorted((w for w in self._workers if not w.busy), key=lambda w: w.use_seq)
            if idle:
                self._stats["memoryReclaims"] += 1
                self._drop_locked(idle[0])
                continue
            if self._retiring and time.monotonic() < deadline:
                self._cv.wait(timeout=0.05)
                continue
            self._stats["memoryRefusals"] += 1
            raise MemoryAdmissionError(
                f"cadgen memory admission: {usage / MIB:.0f} MiB charged plus "
                f"{additional / MIB:.0f} MiB requested exceeds the "
                f"{ceiling / MIB:.0f} MiB {'dependency' if dependency else 'build'} allowance "
                f"({self._policy.limit_bytes / MIB:.0f} MiB total). "
                "Idle workers were reclaimed; active builds retain their geometry. "
                "Wait for active work to finish, increase CADGEN_MEMORY_MB, or reduce the workload."
            )

    def _used_locked(self, worker: Worker) -> Worker:
        worker.last_used = self._clock()
        worker.use_seq = next(_USE_SEQUENCE)
        return worker

    def unbind_idle(self) -> None:
        """A bound worker idle for ``idle_unbind_seconds()`` returns to the spare set
        (spares beyond K exit). Its model's next build rebinds a spare -- no import
        repaid, a cold RAM op-memo tier. This only releases process state;
        persistent cache objects remain available to the replacement worker."""
        limit = idle_unbind_seconds()
        with self._cv:
            now = self._clock()
            for worker in list(self._workers):
                if not worker.model or worker.busy or worker.extra:
                    continue
                if now - worker.last_used < limit:
                    continue
                self._stats["unbinds"] += 1
                if len(self._spares_locked()) + self._spares_pending >= spare_count():
                    self._drop_locked(worker)
                else:
                    worker.model = ""

    def release(self, worker: Worker, *, healthy: bool = True) -> None:
        with self._cv:
            worker.busy = False
            worker.last_used = self._clock()
            worker.jobs_served += 1
            self._stats["jobsServed"] += 1
            if not healthy or not worker.alive():
                if not healthy:
                    self._stats["crashes"] += 1
                self._drop_locked(worker)
            elif worker.jobs_served >= recycle_after():
                self._stats["recycles"] += 1
                self._drop_locked(worker)
            elif worker.extra:
                if len(self._spares_locked()) + self._spares_pending >= spare_count():
                    # The spare set is already full (a replacement was started when this
                    # one was taken); keeping it too would grow the set by one per extra.
                    self._drop_locked(worker)
                else:
                    # Back to the spare set: unbound, idle, warm.
                    worker.model = ""
                    worker.extra = False
            self._reclaim_pressure_locked()
            self._cv.notify_all()
        self.ensure_spares()

    def _drop_locked(self, worker: Worker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        if worker not in self._retiring:
            self._retiring.append(worker)

        def retire():
            try:
                worker.kill()
            finally:
                with self._cv:
                    self._cv.notify_all()

        threading.Thread(target=retire, daemon=True).start()

    def _reap_dead_locked(self) -> None:
        for worker in list(self._workers):
            if not worker.alive() and not worker.busy:
                self._drop_locked(worker)

    def reap_dead(self) -> None:
        with self._cv:
            self._reap_dead_locked()

    def shutdown(self) -> None:
        with self._cv:
            self._closed = True
            workers, self._workers = [*self._workers, *self._retiring], []
            self._retiring = []
        for worker in workers:
            worker.kill()

    def snapshot(self) -> dict:
        with self._cv:
            workers = [
                {
                    "pid": getattr(w, "pid", None),
                    "model": w.model,
                    "busy": w.busy,
                    "extra": w.extra,
                    "jobs": w.jobs_served,
                }
                for w in self._workers
            ]
            return {
                "workers": workers,
                "spares": len(self._spares_locked()),
                "sparesPending": self._spares_pending,
                "sparesWanted": spare_count(),
                "memory": self._memory_locked(),
                **self._stats,
            }
