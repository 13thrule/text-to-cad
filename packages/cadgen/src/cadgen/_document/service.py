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
from pathlib import Path
import threading
import time
from typing import Any, Iterator

from .sources import CapturedInput


_SERVICE: ContextVar[DocumentService | None] = ContextVar("cadgen_document_service", default=None)
_ATTEMPT: ContextVar[BuildAttempt | None] = ContextVar("cadgen_document_attempt", default=None)
_ABSENT = object()


@dataclass
class BuildAttempt:
    document: Any
    source: CapturedInput
    function: str
    required_exports: tuple[str, ...] = ()
    state: str = "building"
    revision: Any = None
    error: str | None = None
    stats: Any = None
    source_seconds: float | None = None
    fallback_counts: dict[str, int] | None = None
    job: Any = None
    output_receipts: tuple[Any, ...] | None = None

    @contextmanager
    def source_execution(self) -> Iterator[Any]:
        """Run authored code in the frontend, then publish native readiness."""
        from cadgen._document.frontend import FrontendSession

        if self.state != "building" or self.revision is not None:
            raise RuntimeError("a build attempt may execute its source only once")
        started = time.perf_counter()
        try:
            with self.document.begin(source_identity=self.source.digest, required_exports=self.required_exports) as transaction:
                cancellation = (None if self.job is None
                                else getattr(self.job, "cancellation", None))
                if cancellation is not None:
                    transaction.cancellation = cancellation
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
        if self.output_receipts is None:
            missing = [path for path in self.required_exports if not Path(path).is_file()]
            if missing:
                raise RuntimeError(f"build returned without declared exports: {', '.join(missing)}")
        else:
            from .step_product import destination_digest
            receipts = {receipt.destination: receipt for receipt in self.output_receipts}
            if (len(receipts) != len(self.output_receipts)
                    or set(receipts) != set(self.required_exports)):
                raise RuntimeError("build returned without every declared output receipt")
            for path, receipt in receipts.items():
                if (receipt.owner_id != self.document.owner_id
                        or receipt.revision_id != self.revision.revision_id
                        or destination_digest(Path(path)) != receipt.sha256):
                    raise RuntimeError("declared output no longer matches its publication receipt")
        self.document.complete_exports(self.revision.revision_id, self.required_exports)
        self.state = "exports_complete"

    def mark_failed(self, error: BaseException) -> None:
        """Record late lifecycle failures without discarding completed receipts."""
        already_failed = self.state == "failed"
        self.state = "failed"
        self.error = str(error)
        if self.revision is not None and not already_failed:
            try:
                self.document.fail(self.revision.revision_id)
            except BaseException as failure:
                error.add_note(f"Could not mark native revision failed: {failure}")


@dataclass(frozen=True)
class SavedDocument:
    """A byte-bound saved artifact revision, never a source preview."""

    document: Any
    revision_id: int
    input_path: str
    input_sha256: str
    input_size: int
    reused: bool
    annotation_sha256: str | None
    annotation_size: int


@dataclass(frozen=True)
class CheckpointPublication:
    document_id: str
    revision_id: int
    catalog_revision_id: str
    published: bool


class DocumentService:
    """A bounded, thread-affine set of retained documents in a kernel worker.

    Registry eviction forgets a document only after its build is finished.
    Native revision pins remain owned by the document itself. This registry
    bounds document count; it is not a claim of a process RSS limit.
    """

    def __init__(self, *, max_documents: int = 8, document_factory: Any = None,
                 coordinator: Any = None, checkpoint_codec: Any = None):
        if isinstance(max_documents, bool) or not isinstance(max_documents, int) or max_documents < 1:
            raise ValueError("max_documents must be a positive integer")
        self.max_documents = max_documents
        self._factory = document_factory
        if checkpoint_codec is not None:
            from .checkpoint import CheckpointCodec

            if type(checkpoint_codec) is not CheckpointCodec:
                raise TypeError("document recovery requires a CheckpointCodec")
            if document_factory is not None:
                raise ValueError("a recovered document cannot use a custom document factory")
        self._codec = checkpoint_codec
        self._thread = threading.get_ident()
        self._documents: OrderedDict[tuple[str, str], Any] = OrderedDict()
        self._checkpoint_heads: dict[tuple[str, str], str | None] = {}
        self.recovery: dict[tuple[str, str], str] = {}
        self._active: set[tuple[str, str]] = set()
        self.last_attempt: BuildAttempt | None = None
        if coordinator is None:
            from .scheduler import Coordinator

            coordinator = Coordinator()
        self.coordinator = coordinator
        self.last_request = None

    def _check_owner(self) -> None:
        if threading.get_ident() != self._thread:
            raise RuntimeError("native document service must run in its owning thread")

    def generate(self, path: Path, function: str | None = None):
        """Build directly from captured source to this engine's STEP publisher."""
        self._check_owner()
        from .program import generate

        return generate(self, path, function)

    def generate_captured(self, source: CapturedInput, function: str | None = None, *,
                          cancellation=None):
        """Build one already-captured source buffer without reading its path again."""
        self._check_owner()
        from .program import generate_captured

        return generate_captured(self, source, function, cancellation=cancellation)

    @staticmethod
    def _has_live_pins(owner) -> bool:
        pins = getattr(owner, "_pins", None)
        if pins is None:
            return False
        lock = getattr(owner, "_lock", None)
        if lock is None:
            return any(pins.values())
        with lock:
            return any(pins.values())

    def _evict_one(self) -> None:
        """Remove one inactive, unpinned owner with the pin check held stable."""
        for candidate, owner in self._documents.items():
            if candidate in self._active:
                continue
            lock = getattr(owner, "_lock", None)
            if lock is None:
                if self._has_live_pins(owner):
                    continue
                victim = candidate
                break
            with lock:
                if any(getattr(owner, "_pins", {}).values()):
                    continue
                self._documents.pop(candidate)
                self._checkpoint_heads.pop(candidate, None)
                self.recovery.pop(candidate, None)
                return
        else:
            raise RuntimeError("document capacity exhausted by active or pinned owners")
        self._documents.pop(victim)
        self._checkpoint_heads.pop(victim, None)
        self.recovery.pop(victim, None)

    def _document_for(self, key, identity, *, admission=None, cancellation=None):
        """Acquire one owner, restoring only this engine's disposable checkpoint."""
        if cancellation is not None and cancellation.is_set():
            from .resources import Cancelled

            raise Cancelled("document acquisition was cancelled")
        if self._codec is not None:
            self._codec._check_runtime()
        if key in self._documents:
            self._documents.move_to_end(key)
            return self._documents[key]
        at_capacity = len(self._documents) >= self.max_documents
        if at_capacity:
            evictable = any(candidate not in self._active and not self._has_live_pins(owner)
                            for candidate, owner in self._documents.items())
            if not evictable:
                raise RuntimeError("document capacity exhausted by active or pinned owners")
        document = None
        selected = None
        status = "absent"
        if self._codec is not None:
            from .checkpoint import CheckpointError
            from .storage import StorageCorrupt

            selected = self._codec.catalog.head(identity)
            if selected is not None:
                try:
                    restored = self._codec.recover(identity, selected, admission=admission or self.coordinator.admission,
                                                   cancellation=cancellation)
                    document = restored.document
                    document.admission = self.coordinator.admission
                    status = "recovered"
                except (CheckpointError, StorageCorrupt, KeyError):
                    # Missing, corrupt or incompatible derived state is a miss.
                    # Source still executes; saved artifacts still parse their
                    # captured bytes. Never acknowledge historical file saves.
                    status = "discarded"
        if document is None:
            if self._factory is not None:
                document = self._factory(identity)
            else:
                from .core import Document

                runtime = () if self._codec is None else self._codec.runtime
                document = Document(identity, runtime=runtime, admission=self.coordinator.admission)
        if cancellation is not None and cancellation.is_set():
            from .resources import Cancelled

            raise Cancelled("document acquisition was cancelled")
        if at_capacity:
            self._evict_one()
        self._documents[key] = document
        self._checkpoint_heads[key] = selected
        self.recovery[key] = status
        return document

    def checkpoint(self, document, revision_id: int | None = None, *,
                   resources=None, cancellation=None) -> CheckpointPublication:
        """Checkpoint an idle resident owner under its original catalog CAS.

        This is internal maintenance, not an authored save queue. Source and
        completed exchange files remain durable even without a checkpoint.
        A conflict never advances the expectation to overwrite another owner.
        """
        self._check_owner()
        if self._codec is None:
            raise RuntimeError("this document service has no checkpoint catalog")
        key = next((key for key, value in self._documents.items() if value is document), None)
        if key is None:
            raise ValueError("checkpoint requires this service's resident document")
        if key in self._active or document._active:
            raise RuntimeError("checkpoint requires an idle document")
        head = document.head
        selected = head.revision_id if revision_id is None and head is not None else revision_id
        if type(selected) is not int:
            raise ValueError("checkpoint requires a committed revision")
        with document.pin(selected) as pin:
            from .core import RevisionState

            if (head is None or selected != head.revision_id
                    or document.state(selected) not in {RevisionState.GEOMETRY_READY,
                                                        RevisionState.EXPORTS_COMPLETE}):
                raise ValueError("checkpoint publication requires the current usable head")
            staged = self._codec.stage(document, pin.revision_id,
                                       resources=resources, cancellation=cancellation)
            if cancellation is not None and cancellation.is_set():
                from .resources import Cancelled

                raise Cancelled("document checkpoint was cancelled")
            published = self._codec.commit(staged, expected_head=self._checkpoint_heads[key])
        if published:
            self._checkpoint_heads[key] = staged.revision_id
        return CheckpointPublication(document.document_id, selected, staged.revision_id, published)

    def load_step(self, source: CapturedInput, *, work_directory: Path,
                  annotations=_ABSENT, cancellation=None) -> SavedDocument:
        """Open the actual captured file in a saved-artifact owner.

        Identical STEP bytes share native ownership across paths. Annotation
        revisions share those native prototypes and remain distinct from the
        STEP-only revision. Supplied None attests captured companion absence;
        omitted annotations are captured here, before any native work.
        """
        self._check_owner()
        from .resources import Cancelled
        from .step_import import (StepImportSession, step_input_identity,
                                  saved_annotation_paths, apply_saved_annotations,
                                  native_saved_root)
        from .annotations import (MAX_BYTES, capture_companion, companion_path,
                                  read_annotations)

        if cancellation is not None and cancellation.is_set():
            raise Cancelled("STEP import was cancelled")
        if annotations is _ABSENT:
            annotations = capture_companion(source.path)
        if annotations is not None:
            if (type(annotations) is not CapturedInput
                    or annotations.path != companion_path(source.path).resolve()
                    or len(annotations.data) > MAX_BYTES):
                raise ValueError("saved annotations require the bounded captured STEP companion")
        runtime = () if self._codec is None else self._codec.runtime
        identity = step_input_identity(source, runtime=runtime)
        key = ("saved-step", identity)
        if key in self._active:
            raise RuntimeError("recursive saved STEP import")
        document = self._document_for(key, f"saved-step:{identity}", cancellation=cancellation)
        self._active.add(key)
        try:
            native_identity = f"step:{source.digest}"
            selected_identity = (native_identity if annotations is None else
                                 f"step-annotations:{source.digest}:{annotations.digest}")
            revisions = tuple(document._revisions.values())
            native = next((revision for revision in reversed(revisions)
                           if revision.source_identity == native_identity
                           and revision.unrepresented_metadata == ()), None)
            prior = next((revision for revision in reversed(revisions)
                          if revision.source_identity == selected_identity
                          and revision.unrepresented_metadata == ()), None)
            if native is None:
                head = document.head
                if (head is not None and head.unrepresented_metadata == ()
                        and head.source_identity.startswith(f"step-annotations:{source.digest}:")):
                    # Checkpoints retain one selected root. Its only companion
                    # fields are PBR/tag overrides; removing those reconstructs
                    # the actual STEP-native root without copying its geometry.
                    root = native_saved_root(head.root)
                    with document.begin(native_identity) as transaction:
                        transaction.cancellation = cancellation or transaction.cancellation
                        transaction.bind_root(root, unrepresented_metadata=())
                        native = transaction.commit()
                else:
                    imported = StepImportSession(document, work_directory=work_directory,
                                                 cancellation=cancellation).load(source)
                    native = document._revisions[imported.revision_id]
            with document.pin(native.revision_id):
                paths = saved_annotation_paths(source, native.root)
                product = read_annotations(source.data, paths, None if annotations is None else annotations.data)
                if cancellation is not None and cancellation.is_set():
                    raise Cancelled("STEP annotations were cancelled")
                reused = prior is not None
                if annotations is None:
                    selected = native
                elif prior is not None:
                    selected = prior
                else:
                    root = apply_saved_annotations(native.root, product)
                    with document.begin(selected_identity) as transaction:
                        transaction.cancellation = cancellation or transaction.cancellation
                        transaction.bind_root(root, unrepresented_metadata=())
                        selected = transaction.commit()
                if selected is not document.head:
                    # Selecting a retained view still establishes the current
                    # saved-document head, so its normal checkpoint contract
                    # remains available without changing any native geometry.
                    with document.begin(selected_identity) as transaction:
                        transaction.cancellation = cancellation or transaction.cancellation
                        transaction.bind_root(selected.root, unrepresented_metadata=())
                        selected = transaction.commit()
                revision_id = selected.revision_id
                with document.pin(revision_id):
                    document.collect(keep_revisions=2)
            return SavedDocument(document, revision_id, str(source.path), source.digest,
                                 len(source.data), reused,
                                 None if annotations is None else annotations.digest,
                                 0 if annotations is None else len(annotations.data))
        finally:
            self._active.remove(key)

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
    def build(self, source: CapturedInput, function: str, *,
              required_exports: tuple[str, ...] = (), job: Any = None) -> Iterator[BuildAttempt]:
        self._check_owner()
        if type(source) is not CapturedInput:
            raise TypeError("document builds require already captured source bytes")
        key = (str(source.path), function)
        if key in self._active:
            raise RuntimeError(f"recursive document build: {source.path.name}::{function}")
        document = self._document_for(key, f"source:{source.path}::{function}",
                                      admission=None if job is None else job.admission,
                                      cancellation=None if job is None else getattr(job, "cancellation", None))
        self._active.add(key)
        attempt = BuildAttempt(document, source, function, required_exports, job=job)
        prior_admission = getattr(document, "admission", _ABSENT)
        token = None
        failure = None
        try:
            try:
                if job is not None:
                    document.admission = job.admission
                token = _ATTEMPT.set(attempt)
                yield attempt
                attempt.complete_exports()
            except BaseException as error:
                failure = error
                attempt.mark_failed(error)
                raise
            finally:
                try:
                    document.collect(keep_revisions=2)
                except BaseException as error:
                    if failure is None:
                        raise
                    failure.add_note(f"Document collection also failed: {error}")
        except BaseException as error:
            attempt.mark_failed(error)
            raise
        finally:
            try:
                if job is not None:
                    if prior_admission is _ABSENT:
                        if hasattr(document, "admission"):
                            del document.admission
                    else:
                        document.admission = prior_admission
            except BaseException as error:
                attempt.mark_failed(error)
                raise
            finally:
                if token is not None:
                    _ATTEMPT.reset(token)
                self._active.remove(key)
                self.last_attempt = attempt


def current_service() -> DocumentService | None:
    return _SERVICE.get()


def current_attempt() -> BuildAttempt | None:
    return _ATTEMPT.get()
