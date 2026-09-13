"""In-process ownership and build lifecycle for the document-engine proof.

Only internal integration/benchmark callers activate this service until the
document frontend passes its cutover gates. There is no user-facing engine
flag. A successful geometry transaction is deliberately distinct from a
successful explicit build, which still owes all its declared files.

This module imports no CAD kernel. Native documents and the frontend are
created only inside the owning build process.
"""

from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
from pathlib import Path
import threading
import time
from typing import Any, Iterator


_SERVICE: ContextVar[DocumentService | None] = ContextVar("cadgen_document_service", default=None)
_ATTEMPT: ContextVar[BuildAttempt | None] = ContextVar("cadgen_document_attempt", default=None)


@dataclass(frozen=True)
class CapturedSource:
    """The exact buffer compiled for an entry, rather than a later path hash."""

    path: Path
    data: bytes
    digest: str

    @classmethod
    def read(cls, path: Path) -> CapturedSource:
        resolved = Path(path).resolve()
        data = resolved.read_bytes()
        return cls(resolved, data, hashlib.sha256(data).hexdigest())


@dataclass
class BuildAttempt:
    document: Any
    source: CapturedSource
    function: str
    required_exports: tuple[str, ...] = ()
    state: str = "building"
    revision: Any = None
    error: str | None = None
    stats: Any = None
    source_seconds: float | None = None
    fallback_counts: dict[str, int] | None = None

    @contextmanager
    def source_execution(self) -> Iterator[Any]:
        """Run authored code in the frontend, then publish native readiness."""
        from cadgen._document.frontend import FrontendSession

        if self.state != "building" or self.revision is not None:
            raise RuntimeError("a build attempt may execute its source only once")
        started = time.perf_counter()
        try:
            with self.document.begin(source_identity=self.source.digest, required_exports=self.required_exports) as transaction:
                try:
                    with FrontendSession(transaction) as frontend:
                        yield frontend
                        self.fallback_counts = dict(frontend._fallback_counts)
                        if transaction._root is None:
                            raise RuntimeError("source execution did not bind its returned model")
                    self.revision = transaction.commit()
                finally:
                    self.stats = transaction.stats
        finally:
            self.source_seconds = time.perf_counter() - started
        self.state = "geometry_ready"

    def complete_exports(self) -> None:
        if self.state != "geometry_ready":
            raise RuntimeError("exports cannot complete before document geometry")
        missing = [path for path in self.required_exports if not Path(path).is_file()]
        if missing:
            raise RuntimeError(f"build returned without declared exports: {', '.join(missing)}")
        self.document.complete_exports(self.revision.revision_id, self.required_exports)
        self.state = "exports_complete"


class DocumentService:
    """A bounded, thread-affine set of retained documents in a kernel worker.

    Registry eviction forgets a document only after its build is finished.
    Native revision pins remain owned by the document itself. This registry
    bounds document count; it is not a claim of a process RSS limit.
    """

    def __init__(self, *, max_documents: int = 8, document_factory: Any = None):
        if isinstance(max_documents, bool) or not isinstance(max_documents, int) or max_documents < 1:
            raise ValueError("max_documents must be a positive integer")
        self.max_documents = max_documents
        self._factory = document_factory
        self._thread = threading.get_ident()
        self._documents: OrderedDict[tuple[str, str], Any] = OrderedDict()
        self._active: set[tuple[str, str]] = set()
        self.last_attempt: BuildAttempt | None = None

    def _check_owner(self) -> None:
        if threading.get_ident() != self._thread:
            raise RuntimeError("native document service must run in its owning thread")

    @contextmanager
    def activate(self) -> Iterator[DocumentService]:
        self._check_owner()
        if current_service() is not None:
            raise RuntimeError("a document service is already active in this context")
        token = _SERVICE.set(self)
        try:
            yield self
        finally:
            _SERVICE.reset(token)

    @contextmanager
    def build(self, path: Path, function: str, *, required_exports: tuple[str, ...] = ()) -> Iterator[BuildAttempt]:
        self._check_owner()
        source = CapturedSource.read(path)
        key = (str(source.path), function)
        if key in self._active:
            raise RuntimeError(f"recursive document build: {source.path.name}::{function}")
        if key not in self._documents:
            while len(self._documents) >= self.max_documents:
                victim = next((candidate for candidate in self._documents if candidate not in self._active), None)
                if victim is None:
                    raise RuntimeError("document capacity exhausted by active builds")
                self._documents.pop(victim)
            factory = self._factory
            if factory is None:
                from cadgen._document import Document

                factory = Document
            self._documents[key] = factory(f"{source.path}::{function}")
        document = self._documents[key]
        self._documents.move_to_end(key)
        self._active.add(key)
        attempt = BuildAttempt(document, source, function, required_exports)
        token = _ATTEMPT.set(attempt)
        try:
            yield attempt
            attempt.complete_exports()
        except BaseException as error:
            attempt.state = "failed"
            attempt.error = str(error)
            if attempt.revision is not None:
                document.fail(attempt.revision.revision_id)
            raise
        finally:
            _ATTEMPT.reset(token)
            self._active.remove(key)
            self.last_attempt = attempt
            document.collect(keep_revisions=2)


def current_service() -> DocumentService | None:
    return _SERVICE.get()


def current_attempt() -> BuildAttempt | None:
    return _ATTEMPT.get()
