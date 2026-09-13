"""Source execution directly into pinned document products.

This is the new engine's bounded STEP integration, not an adapter over a model
record or saved-scene cache. It replays authored Python and uses the retained
native graph, then publishes a STEP product from the returned root. Declared
output kinds whose new producers are not implemented fail before the body;
they never route to the previous runtime.
"""
from __future__ import annotations

from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import FunctionType
from typing import Any


_PROGRAM: ContextVar[Any] = ContextVar("cadgen_document_program", default=None)


class UnsupportedProgram(ValueError):
    pass


@dataclass(frozen=True)
class ProgramResult:
    document: Any
    revision_id: int
    outputs: tuple[Any, ...]
    inputs: tuple[Any, ...]
    product_metrics: Any


def current_program():
    return _PROGRAM.get()


@contextmanager
def _declaration_registry(sources):
    """Restore only declarations owned by this captured source execution.

    This runs inside SourceSession's import lock and before its captured-code
    index is released. Unrelated registrations, including additions made while
    author code runs, retain their current values.
    """
    from cadgen import authoring

    before = dict(authoring._REGISTRY)
    try:
        yield
    finally:
        # The code index distinguishes executed Python from read_data buffers;
        # a data file alone cannot make its declarations belong to this scope.
        owned_paths = {captured.path for _code, captured in sources._code_inputs.values()}
        registry = authoring._REGISTRY
        owned = {key for key, definition in (*before.items(), *registry.items())
                 if definition.script_path in owned_paths}
        for key in owned:
            current = registry.get(key)
            if current is not None and current.script_path not in owned_paths:
                continue
            if key in before:
                registry[key] = before[key]
            else:
                registry.pop(key, None)


def _definition(module, source: Path, function: str | None):
    # The executed module is authoritative. A process-global declaration
    # registry may still contain names deleted by this source revision.
    definitions = {}
    for name, value in vars(module).items():
        if not isinstance(value, FunctionType):
            continue
        definition = getattr(value, "__cadgen_model__", None)
        if definition is not None and definition.script_path == source:
            definitions[name] = definition
    if function is not None:
        if function not in definitions:
            raise ValueError(f"{source.name} does not declare model {function!r}")
        return definitions[function]
    unique = {definition.name: definition for definition in definitions.values()}
    if len(unique) != 1:
        raise ValueError(f"{source.name} requires an explicit model function ({len(unique)} declared)")
    return next(iter(unique.values()))


def _output_paths(destination):
    from .annotations import companion_path
    destination = Path(destination).resolve()
    companion = companion_path(destination).resolve()
    if destination == companion:
        raise ValueError("STEP and annotation destinations must be different files")
    return destination, companion


class _ProgramScope:
    def __init__(self):
        self.frontend = None
        self.sources = None
        self.stack = []
        self.outputs = []
        self.child_failures = []
        self.job = None

    @staticmethod
    def validate(definition):
        if (definition.fmt != "step" or not definition.step_output
                or definition.mesh_exports or definition.kinematics is not None):
            raise UnsupportedProgram("this document producer currently requires a STEP-only declaration without kinematics")

    def source_identity(self):
        consumed = sorted((str(item.path), item.digest) for item in self.sources.inputs)
        return hashlib.sha256(json.dumps(consumed, separators=(",", ":")).encode("utf-8")).hexdigest()

    def expected_after_children(self, destination, previous, since):
        from .core import ExportConflict

        for receipt in self.outputs[since:]:
            if receipt.destination != str(destination):
                continue
            if receipt.previous_sha256 != previous:
                raise ExportConflict("STEP destination changed outside this family's verified publications")
            previous = receipt.sha256
        return previous

    def body(self, definition):
        self.validate(definition)
        if definition.ref in self.stack:
            raise RuntimeError(f"recursive document model: {definition.ref}")
        self.sources.input_for_function(definition.func)
        self.stack.append(definition.ref)
        try:
            return definition.func()
        finally:
            self.stack.pop()

    def call(self, definition, args, kwargs):
        if args or kwargs:
            raise TypeError(f"{definition.name}() takes no arguments: a model is one configuration of one output.")
        try:
            return self._child(definition)
        except BaseException as error:
            self.child_failures.append(error)
            raise

    def _child(self, definition):
        self.validate(definition)
        destination = definition.output_path.resolve()
        source = self.sources.input_for_function(definition.func)
        with self.job.child(source, definition.name, outputs=_output_paths(destination)):
            return self._child_result(definition, destination)

    def _child_result(self, definition, destination):
        from .returned import capture_returned_shape
        from .step_product import destination_digest

        destinations = _output_paths(destination)
        previous = tuple(destination_digest(path) for path in destinations)
        publication_start = len(self.outputs)
        result = self.body(definition)
        returned = capture_returned_shape(self.frontend, result)
        transaction = self.frontend.transaction
        revision = transaction.publish_result(
            definition.ref, returned.root, source_identity=self.source_identity(),
            required_exports=tuple(map(str, destinations)),
            unrepresented_metadata=returned.unrepresented_metadata)
        try:
            self.job.geometry_ready(f"{transaction.document.owner_id}:{revision.revision_id}")
            previous = tuple(self.expected_after_children(path, prior, publication_start)
                             for path, prior in zip(destinations, previous))
            receipts, _ = _publish(transaction.document, revision, destinations, previous, self.job)
        except BaseException:
            transaction.document.fail(revision.revision_id)
            raise
        self.outputs.extend(receipts)
        # The same authored wrapper stays in the execution arena. Snapshotting
        # and saving a child neither serializes it back into the parent nor
        # detaches its aliases. Its completed outputs survive a later failure.
        return result


def _publish(document, revision, destinations, previous, job):
    from .core import ExportConflict
    from .step_product import StepProductSession, destination_digest

    with StepProductSession(document, revision.revision_id,
                            work_directory=destinations[0].parent,
                            cancellation=job.cancellation) as publisher:
        publisher.prepare(destinations[0].name)
        receipts = []
        with publisher.stage_outputs(destinations) as staged:
            with job.publications(destinations) as publications:
                # Refuse every known external conflict before changing either
                # path. The coordinator serializes competing family claims.
                for path, expected in zip(destinations, previous):
                    if destination_digest(path) != expected:
                        raise ExportConflict("output destination changed before paired publication")
                for item, publication, expected in zip(staged, publications, previous):
                    def completed(receipt):
                        if (receipt.owner_id != document.owner_id
                                or receipt.revision_id != revision.revision_id
                                or receipt.destination != str(publication.path)
                                or receipt.sha256 != item.sha256 or receipt.size != item.size):
                            raise RuntimeError("output publication receipt does not match this build")
                        publication.acknowledge(receipt.sha256)
                        receipts.append(receipt)
                    publisher.publish_staged(item, expected_prior_digest=expected, completed=completed)
                # Two renames are not atomic. If a later effect fails, receipts
                # remain truthful historical facts and the build fails. A stale
                # companion is rejected by its STEP binding on saved-file open.
                if any(destination_digest(item.destination) != item.sha256 for item in staged):
                    raise ExportConflict("output pair changed during publication")
        metrics = publisher.metrics
    return tuple(receipts), metrics


def generate(service, path: Path, function: str | None = None) -> ProgramResult:
    """Finish an explicit STEP build without the previous generation pipeline."""
    from .sources import CapturedInput

    return generate_captured(service, CapturedInput.read(path), function)


def generate_captured(service, captured, function: str | None = None, *, cancellation=None) -> ProgramResult:
    """Execute the buffer accepted by a caller before queueing or IPC."""
    from .sources import CapturedInput
    from .resources import AdmissionDenied, ResourceRequest

    if current_program() is not None:
        raise RuntimeError("a document program is already running")
    if type(captured) is not CapturedInput:
        raise TypeError("document generation requires captured source bytes")
    if function is not None and (type(function) is not str or not function):
        raise ValueError("model function must be a nonempty string or None")
    family = str(captured.path)
    request = service.coordinator.accept(
        family, f"{family}::{function or '<entry>'}", captured, function or "<entry>",
        resources=ResourceRequest(native_bytes=512 * 1024**2, derived_bytes=256 * 1024**2),
        cancellation=cancellation)
    job = None
    try:
        try:
            # Never execute an older queued request using this call's function
            # selection or accidentally consume its explicit output obligations.
            job = service.coordinator.pull(family, ticket=request.ticket)
            if job is None:
                raise AdmissionDenied("the synchronous document request cannot acquire its execution budget")
            with job:
                return _execute(service, job, function)
        finally:
            facts = service.coordinator.snapshot(request.ticket)
            if not facts.finished:
                service.coordinator.cancel(request.ticket)
                facts = service.coordinator.snapshot(request.ticket)
            service.last_request = facts
            if facts.finished:
                service.coordinator.forget(request.ticket)
    except BaseException as error:
        attempt = service.last_attempt
        if job is not None and attempt is not None and attempt.job is job:
            attempt.mark_failed(error)
        raise


def _execute(service, job, function):
    from .sources import SourceSession
    from .returned import bind_returned_shape
    from .step_product import destination_digest

    source_path = job.request.source.path
    scope = _ProgramScope()
    scope.job = job
    token = _PROGRAM.set(scope)
    try:
        with service.build(job.request.source, function or "", job=job) as attempt:
            with attempt.source_execution() as frontend:
                with SourceSession(attempt.source) as sources, _declaration_registry(sources):
                    scope.frontend, scope.sources = frontend, sources
                    module = sources.load_entry()
                    definition = _definition(module, source_path, function)
                    scope.validate(definition)
                    destination = definition.output_path.resolve()
                    destinations = _output_paths(destination)
                    job.bind_outputs(destinations)
                    previous = tuple(destination_digest(path) for path in destinations)
                    publication_start = len(scope.outputs)
                    attempt.required_exports = tuple(map(str, destinations))
                    frontend.transaction.required_exports = attempt.required_exports
                    result = scope.body(definition)
                    if scope.child_failures:
                        raise RuntimeError("a called child model did not complete its declared outputs") from scope.child_failures[0]
                    bind_returned_shape(frontend, result)
                    inputs = tuple(sources.inputs)
                    frontend.transaction.source_identity = scope.source_identity()
            job.geometry_ready(f"{attempt.document.owner_id}:{attempt.revision.revision_id}")
            previous = tuple(scope.expected_after_children(path, prior, publication_start)
                             for path, prior in zip(destinations, previous))
            receipts, metrics = _publish(attempt.document, attempt.revision, destinations, previous, job)
            attempt.output_receipts = receipts
            # Success is an attested actual-byte publication, not merely the
            # existence of a file left by an earlier call.
            output = ProgramResult(attempt.document, attempt.revision.revision_id,
                                   (*scope.outputs, *receipts), inputs, metrics)
        return output
    finally:
        _PROGRAM.reset(token)
