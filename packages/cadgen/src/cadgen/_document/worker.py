"""Resident document owner behind a private, value-only process connection.

This internal bridge is used by integration clients until public cutover. It
does not invoke the previous daemon, generation backend or geometry store.
The parent imports no kernel; only the spawned owner creates native documents.
"""
from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass
import io
import math
import multiprocessing
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time
import traceback

from . import wire


MAX_LEASES = 64
MAX_REQUEST_ID = 2**63 - 1
MAX_TEXT = 32768
MAX_ENVIRONMENT_ENTRIES = 4096
MAX_GRACE_SECONDS = 10
MAX_STARTUP_SECONDS = 120
PARENT_DEATH_GRACE_SECONDS = 2
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_OPERATIONS = {"generate", "open_step", "release", "checkpoint", "display", "query"}


class WorkerError(RuntimeError):
    def __init__(self, message, *, details=None):
        super().__init__(message)
        self.details = details


class WorkerTimeout(TimeoutError):
    pass


def _duration(value, name, maximum, *, allow_zero=False):
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite number of seconds")
    minimum_ok = value >= 0 if allow_zero else value > 0
    if not math.isfinite(value) or not minimum_ok or value > maximum:
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{name} must be {qualifier}, finite and at most {maximum} seconds")
    return float(value)


def _text(value, name, *, maximum=MAX_TEXT):
    if type(value) is not str or not value or len(value) > maximum or "\x00" in value:
        raise ValueError(f"{name} must be bounded nonempty text")
    return value


@dataclass(frozen=True)
class RemoteRevision:
    lease: str
    owner: str
    revision: int
    document: str


class _Log(io.TextIOBase):
    def __init__(self):
        self.parts = []
        self.size = 0
        self.truncated = False

    def write(self, text):
        text = str(text)
        remaining = max(0, 65536 - self.size)
        self.parts.append(text[:remaining]) if remaining else None
        self.size += min(remaining, len(text))
        self.truncated |= len(text) > remaining
        return len(text)

    def value(self):
        return "".join(self.parts)


class _Cancellation:
    def __init__(self):
        self.lock = threading.Lock()
        self.current = None
        self.latest = 0
        self.closed = False

    def bind(self, request):
        event = threading.Event()
        with self.lock:
            self.current = request, event
            if self.closed or request <= self.latest:
                event.set()
        return event

    def listen(self, connection):
        try:
            while True:
                value, payloads = wire.receive(connection)
                if (payloads or type(value) is not dict or set(value) != {"cancel"}
                        or type(value["cancel"]) is not int or value["cancel"] < 1):
                    raise wire.WireError("invalid document cancellation request")
                with self.lock:
                    self.latest = max(self.latest, value["cancel"])
                    if self.current is not None and self.current[0] <= self.latest:
                        self.current[1].set()
        except (EOFError, OSError, wire.WireError):
            with self.lock:
                self.closed = True
                if self.current is not None:
                    self.current[1].set()
            # The control writer exists only in the parent. If it disappears
            # while authored/native work is stuck, force the non-daemon owner
            # down after a bounded cooperative cancellation interval.
            time.sleep(PARENT_DEATH_GRACE_SECONDS)
            os._exit(70)


@contextmanager
def _environment(request):
    environment, directory = request.get("environment"), request.get("cwd")
    if (type(environment) is not dict or len(environment) > MAX_ENVIRONMENT_ENTRIES
            or any(type(k) is not str or not k or len(k) > MAX_TEXT or "=" in k
                   or "\x00" in k or type(v) is not str or len(v) > wire.MAX_HEADER
                   or "\x00" in v for k, v in environment.items())
            or sum(len(k) + len(v) for k, v in environment.items()) > wire.MAX_HEADER
            or type(directory) is not str or not directory or len(directory) > MAX_TEXT
            or "\x00" in directory or not Path(directory).is_dir()):
        raise ValueError("document request requires its environment and existing working directory")
    old_environment, old_path = dict(os.environ), list(__import__("sys").path)
    try:
        os.environ.clear()
        os.environ.update(environment)
        os.chdir(directory)
        yield
    finally:
        os.environ.clear()
        os.environ.update(old_environment)
        __import__("sys").path[:] = old_path
        os.chdir(tempfile.gettempdir())


class _Owner:
    def __init__(self, root, max_documents):
        from .checkpoint import CheckpointCodec, checkpoint_engine_version
        from .service import DocumentService
        from .storage import Catalog

        self.catalog = Catalog(Path(root), engine_version=checkpoint_engine_version())
        self.service = DocumentService(max_documents=max_documents,
                                       checkpoint_codec=CheckpointCodec(self.catalog))
        self.leases = {}
        self.previous_display = None

    def _lease(self, token):
        if type(token) is not str or token not in self.leases:
            raise ValueError("document revision lease is unavailable")
        return self.leases[token]

    def _retain(self, document, revision_id):
        if len(self.leases) >= MAX_LEASES:
            raise ValueError("document revision lease limit reached; release unused revisions")
        pin = document.pin(revision_id)
        try:
            token = secrets.token_urlsafe(24)
            self.leases[token] = document, pin
            return asdict(RemoteRevision(token, document.owner_id, revision_id,
                                         document.document_id))
        except BaseException:
            pin.release()
            raise

    @staticmethod
    def _validate_request(request, payloads):
        operation = request.get("operation")
        if type(operation) is not str or operation not in _OPERATIONS:
            raise ValueError(f"unknown document operation: {operation!r}")
        common = {"id", "operation", "cwd", "environment"}
        allowed = {
            "generate": common | {"path", "digest", "function"},
            "open_step": common | {"path", "digest"},
            "release": common | {"lease"},
            "checkpoint": common | {"lease"},
            "display": common | {"lease", "options", "known"},
            "query": common | {"lease", "references", "space"},
        }[operation]
        optional = {"options", "known"} if operation == "display" else set()
        required = allowed - optional
        if not required.issubset(request) or set(request) - allowed:
            raise ValueError("invalid fields for document operation")
        if operation in {"generate", "open_step"}:
            _text(request["path"], "document input path")
            if type(request["digest"]) is not str or _SHA256.fullmatch(request["digest"]) is None:
                raise ValueError("document input digest must be a SHA-256")
            if len(payloads) != 1:
                raise ValueError("document inputs require exactly one captured buffer")
            if operation == "generate":
                function = request["function"]
                if function is not None:
                    _text(function, "document function", maximum=1024)
        elif payloads:
            raise ValueError("this document operation takes no binary input")
        if operation in {"release", "checkpoint", "display", "query"}:
            _text(request["lease"], "document revision lease", maximum=256)
        if operation == "query":
            references = request["references"]
            if type(references) is not list or not 0 < len(references) <= 64:
                raise ValueError("document inspection requires 1..64 reference values")
            if (type(request["space"]) is not str
                    or request["space"] not in {"world", "prototype"}):
                raise ValueError("document inspection space must be world or prototype")
        return operation

    def execute(self, request, payloads, cancellation):
        from .resources import Cancelled

        if cancellation.is_set():
            raise Cancelled("document request was cancelled")
        operation = self._validate_request(request, payloads)
        if operation in {"generate", "open_step"}:
            from .sources import CapturedInput

            if len(self.leases) >= MAX_LEASES:
                raise ValueError("document revision lease limit reached; release unused revisions")
            captured = CapturedInput(Path(request["path"]), payloads[0], request["digest"])
            if operation == "generate":
                result = self.service.generate_captured(captured, request.get("function"),
                                                        cancellation=cancellation)
                attempt = self.service.last_attempt
                prepared = {"outputs": [asdict(receipt) for receipt in result.outputs],
                            "inputs": [{"path": str(item.path), "digest": item.digest,
                                        "bytes": len(item.data)} for item in result.inputs],
                            "sourceSeconds": attempt.source_seconds,
                            "evaluations": asdict(attempt.stats),
                            "products": asdict(result.product_metrics)}
                response = {"revision": self._retain(result.document, result.revision_id),
                            **prepared}
            else:
                result = self.service.load_step(captured, work_directory=captured.path.parent,
                                                 cancellation=cancellation)
                prepared = {"input": {"path": result.input_path,
                                      "digest": result.input_sha256,
                                      "bytes": result.input_size}, "reused": result.reused}
                response = {"revision": self._retain(result.document, result.revision_id),
                            **prepared}
            return response, ()
        if payloads:
            raise ValueError("this document operation takes no binary input")
        document, pin = self._lease(request.get("lease"))
        if operation == "release":
            pin.release()
            del self.leases[request["lease"]]
            document.collect(keep_revisions=2)
            if (self.previous_display is not None
                    and self.previous_display.owner_id == document.owner_id
                    and not any(owner is document for owner, _pin in self.leases.values())):
                self.previous_display = None
            return {"released": True}, ()
        if operation == "checkpoint":
            result = self.service.checkpoint(document, pin.revision_id, cancellation=cancellation)
            return asdict(result), ()
        if operation == "query":
            from .consumers import RevisionConsumer
            from .inspection import TopologyReference, inspect_batch

            references = tuple(TopologyReference.from_value(value)
                               for value in request["references"])
            with RevisionConsumer(document, pin.revision_id,
                                  cancellation=cancellation) as consumer:
                facts = inspect_batch(consumer, references, space=request["space"])
            return {"facts": facts}, ()
        if operation == "display":
            from .display import build_display
            from .meshing import MeshOptions

            options = request.get("options", {})
            known = request.get("known", [])
            if type(options) is not dict or set(options) - {"relative_chord", "angular", "edges"}:
                raise ValueError("invalid document mesh options")
            if (type(known) is not list or len(known) > wire.MAX_PAYLOADS
                    or any(type(value) is not str or _SHA256.fullmatch(value) is None
                           for value in known)):
                raise ValueError("invalid known document assets")
            product = build_display(document, pin.revision_id, options=MeshOptions(**options),
                                    previous=self.previous_display, cancellation=cancellation)
            self.previous_display = product
            known_assets = set(known)
            missing = [asset for identity, asset in product.assets.items()
                       if identity not in known_assets]
            return {"assets": [{"identity": asset.identity, "bytes": len(asset.payload)}
                               for asset in missing]}, (
                                   product.manifest,
                                   *(asset.payload for asset in missing))
        raise ValueError(f"unknown document operation: {operation!r}")

    def close(self):
        for _document, pin in self.leases.values():
            pin.release()
        self.leases.clear()
        self.previous_display = None
        self.catalog.close()


def _serve(connection, control, root, max_documents):
    cancellation = _Cancellation()
    threading.Thread(target=cancellation.listen, args=(control,), daemon=True).start()
    owner = None
    try:
        owner = _Owner(root, max_documents)
        wire.send(connection, {"ready": wire.PROTOCOL, "pid": os.getpid()})
        last_request = 0
        while True:
            request, payloads = wire.receive(connection)
            if request == {"shutdown": True} and not payloads:
                break
            if (type(request) is not dict or type(request.get("id")) is not int
                    or not last_request < request["id"] <= MAX_REQUEST_ID):
                raise wire.WireError("document requests require increasing identities")
            last_request = request["id"]
            event = cancellation.bind(last_request)
            log, started = _Log(), time.perf_counter()
            try:
                with _environment(request), redirect_stdout(log), redirect_stderr(log):
                    result, buffers = owner.execute(request, payloads, event)
                response = {"id": last_request, "ok": True, "result": result}
            except BaseException as error:
                response = {"id": last_request, "ok": False,
                            "error": {"type": type(error).__name__, "message": str(error),
                                      "traceback": traceback.format_exc()[-32768:]}}
                buffers = ()
            response.update(seconds=time.perf_counter() - started, log=log.value(),
                            logTruncated=log.truncated)
            wire.send(connection, response, buffers)
    except (EOFError, OSError, wire.WireError):
        pass
    finally:
        if owner is not None:
            owner.close()
        connection.close()
        control.close()


class DocumentWorker:
    """One serial parent client; a terminated owner is never silently retried."""

    def __init__(self, root: Path, *, max_documents=8, startup_timeout=30):
        if (type(max_documents) is not int or isinstance(max_documents, bool)
                or not 1 <= max_documents <= MAX_LEASES):
            raise ValueError(f"max_documents must be within {MAX_LEASES}")
        startup_timeout = _duration(startup_timeout, "startup timeout",
                                    MAX_STARTUP_SECONDS)
        self._thread = threading.get_ident()
        self._next = 0
        self._closed = False
        context = multiprocessing.get_context("spawn")
        self.connection, child = context.Pipe(duplex=True)
        child_control, self.control = context.Pipe(duplex=False)
        self.process = context.Process(target=_serve, args=(child, child_control,
                                       str(Path(root).resolve()), max_documents), daemon=False)
        started = time.monotonic()
        try:
            self.process.start()
            child.close()
            child_control.close()
            value, payloads = wire.receive(
                self.connection,
                before_read=lambda: self._wait(started + startup_timeout))
            if (payloads or type(value) is not dict or set(value) != {"ready", "pid"}
                    or type(value["ready"]) is not int or value["ready"] != wire.PROTOCOL
                    or type(value["pid"]) is not int or value["pid"] != self.process.pid):
                raise WorkerError("document owner did not initialize")
            self.pid = value["pid"]
            self.startup_seconds = time.monotonic() - started
        except BaseException:
            child.close()
            child_control.close()
            self.close(force=True)
            raise

    def _check(self):
        if threading.get_ident() != self._thread:
            raise RuntimeError("document worker client belongs to its owning thread")
        if self._closed:
            raise WorkerError("document worker is closed")

    def _wait(self, deadline):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WorkerTimeout("document request exceeded its time limit")
            if self.connection.poll(min(.05, remaining)):
                return
            if not self.process.is_alive():
                raise WorkerError("document owner exited before completing the request")

    def _validate_response(self, response):
        common = {"id", "ok", "seconds", "log", "logTruncated"}
        if (type(response) is not dict or type(response.get("ok")) is not bool
                or set(response) != common | ({"result"} if response.get("ok") else {"error"})
                or type(response.get("id")) is not int or response["id"] != self._next
                or type(response.get("seconds")) not in (int, float)
                or not math.isfinite(response["seconds"])
                or not 0 <= response["seconds"] <= 3600
                or type(response.get("log")) is not str or len(response["log"]) > 65536
                or type(response.get("logTruncated")) is not bool):
            raise WorkerError("document owner returned an invalid response")
        if not response["ok"]:
            error = response["error"]
            if (type(error) is not dict or set(error) != {"type", "message", "traceback"}
                    or any(type(error.get(name)) is not str
                           for name in ("type", "message", "traceback"))
                    or len(error["type"]) > 1024 or len(error["message"]) > 65536
                    or len(error["traceback"]) > 32768):
                raise WorkerError("document owner returned an invalid failure")

    def request(self, operation, *, payloads=(), timeout=60, cancellation_grace=2, **parameters):
        self._check()
        if type(operation) is not str or operation not in _OPERATIONS:
            raise ValueError(f"unknown document operation: {operation!r}")
        timeout = _duration(timeout, "document request timeout", 300)
        cancellation_grace = _duration(cancellation_grace, "cancellation grace",
                                       MAX_GRACE_SECONDS, allow_zero=True)
        if self._next >= MAX_REQUEST_ID:
            raise WorkerError("document request identity space is exhausted")
        self._next += 1
        request = {**parameters, "id": self._next, "operation": operation,
                   "cwd": os.getcwd(), "environment": dict(os.environ)}
        deadline = time.monotonic() + timeout
        try:
            wire.send(self.connection, request, payloads)
        except wire.WireError:
            raise
        except (EOFError, OSError):
            self.close(force=True)
            raise WorkerError("document owner connection failed") from None
        try:
            response, buffers = wire.receive(
                self.connection, before_read=lambda: self._wait(deadline))
        except WorkerTimeout:
            # Give supported native/Python boundaries a short cancellation
            # interval, then always destroy this owner. A late successful
            # response may already contain a newly-created revision lease.
            try:
                wire.send(self.control, {"cancel": self._next})
            except BaseException:
                pass
            try:
                if cancellation_grace:
                    grace_deadline = time.monotonic() + cancellation_grace
                    wire.receive(self.connection,
                                 before_read=lambda: self._wait(grace_deadline))
            except BaseException:
                pass
            self.close(force=True)
            raise
        except wire.WireStreamInterrupted as error:
            # Once any payload frame has been consumed, neither the current
            # response nor a later one can be identified safely.
            try:
                wire.send(self.control, {"cancel": self._next})
            except BaseException:
                pass
            self.close(force=True)
            if isinstance(error.__cause__, WorkerTimeout):
                raise error.__cause__
            raise WorkerError("document owner payload stream failed") from None
        except WorkerError:
            self.close(force=True)
            raise
        except (EOFError, OSError, wire.WireError):
            self.close(force=True)
            raise WorkerError("document owner connection failed") from None
        try:
            self._validate_response(response)
        except WorkerError:
            self.close(force=True)
            raise
        if not response["ok"]:
            error = response.get("error", {})
            raise WorkerError(error.get("message", "document request failed"), details=response)
        return response, buffers

    def generate(self, source, function=None, **limits):
        return self.request("generate", path=str(source.path), digest=source.digest,
                            function=function, payloads=(source.data,), **limits)

    def open_step(self, source, **limits):
        return self.request("open_step", path=str(source.path), digest=source.digest,
                            payloads=(source.data,), **limits)

    @staticmethod
    def _lease_token(revision):
        if type(revision) is RemoteRevision:
            return revision.lease
        if type(revision) is dict and set(revision) == {"lease", "owner", "revision", "document"}:
            return revision["lease"]
        if type(revision) is str:
            return revision
        raise TypeError("document operation requires a remote revision lease")

    def display(self, revision, *, options=None, known=(), **limits):
        parameters = {"lease": self._lease_token(revision),
                      "options": {} if options is None else dict(options),
                      "known": list(known)}
        return self.request("display", **parameters, **limits)

    def checkpoint(self, revision, **limits):
        return self.request("checkpoint", lease=self._lease_token(revision), **limits)

    def inspect(self, revision, references, *, space="world", **limits):
        if type(references) not in (list, tuple) or not 0 < len(references) <= 64:
            raise ValueError("document inspection requires 1..64 reference values")
        values = [dict(value.to_value()) if hasattr(value, "to_value") else value
                  for value in references]
        return self.request("query", lease=self._lease_token(revision),
                            references=values, space=space, **limits)

    def release(self, revision, **limits):
        return self.request("release", lease=self._lease_token(revision), **limits)

    def close(self, *, force=False):
        if self._closed:
            return
        self._closed = True
        if self.process.pid is not None:
            if force and self.process.is_alive():
                self.process.terminate()
            elif self.process.is_alive():
                try:
                    wire.send(self.connection, {"shutdown": True})
                except (OSError, EOFError):
                    pass
            self.process.join(timeout=2)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=2)
        self.connection.close()
        self.control.close()

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *exc):
        self.close()
