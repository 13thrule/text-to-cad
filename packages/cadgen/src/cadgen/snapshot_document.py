"""Caller-owned native snapshot preparation, independent of saved-file source state.

Only immutable display bytes and closed jobs reach the renderer service. This
internal door does not select a public engine or discover a source implementation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import threading
import time
from types import MappingProxyType

from .assets import runtime_root
from .snapshot_core import (SnapshotError, SUPPORTED_JOB_KEYS, _capture_snapshot_job,
                            clear_render_output_targets, normalize_common_job)
from .snapshot_document_input import (MAX_MANIFEST_BYTES, MAX_ASSET_BYTES,
                                      document_descriptor, native_job_options, native_mesh_options, read_regular)
from .snapshot_operation import CLEANUP_SECONDS, RenderCleanup, normalize_operation
from .snapshot_document_outputs import MAX_OUTPUT_BYTES, output_inventory, publish_outputs, rollback_outputs

MAX_PREPARED_SNAPSHOTS = 4
MAX_STAGED_BYTES = MAX_ASSET_BYTES + MAX_MANIFEST_BYTES + MAX_OUTPUT_BYTES
MAX_STEP_BYTES = 128 * 1024**2
_guard = threading.Lock()
_owners = set()  # Strong ownership intentionally retains uncertain consumers.
_staged_bytes = 0


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("native snapshot exhausted its original deadline")
    return remaining


def _job(job, timeout, *, saved_path=None):
    started = time.monotonic()
    from .store.paths import store_root
    provenance = {"runtimeRoot": str((runtime_root() / "browser").resolve()),
                  "storeRoot": str(store_root().resolve()),
                  "context": {"cwd": str(Path.cwd()), "environment": dict(os.environ)}}
    captured = _capture_snapshot_job(job)
    if set(captured) - SUPPORTED_JOB_KEYS:
        raise SnapshotError("native snapshot requires a closed snapshot job")
    native_job_options(captured)
    seconds = captured.get("timeoutSeconds", timeout)
    if type(seconds) not in (int, float) or not 0 < seconds <= 300:
        raise SnapshotError("native snapshot timeout must be within 0..300 seconds")
    deadline = started + seconds + CLEANUP_SECONDS
    normalized = normalize_common_job(captured, mode="view", resolved_cwd=Path(provenance["context"]["cwd"]), timestamp=None)
    normalized["timeoutSeconds"] = seconds
    provenance["outputs"], provenance["outputBytes"] = output_inventory(normalized)
    if saved_path is not None:
        canonical = (Path(provenance["context"]["cwd"]) / saved_path).resolve()
        if canonical.suffix.lower() not in {".step", ".stp"}:
            raise SnapshotError("native saved snapshot requires a STEP file")
        protected = {canonical, canonical.with_name(canonical.name + ".json").resolve()}
        if any(row["target"].resolve() in protected for row in provenance["outputs"]):
            raise SnapshotError("native snapshot output cannot replace its saved input or companion")
        provenance["inputPath"] = str(canonical)
    clear_render_output_targets([normalized])
    return normalized, deadline, provenance


def _manifest(data):
    if type(data) is not bytes or not 0 < len(data) <= MAX_MANIFEST_BYTES:
        raise SnapshotError("native display manifest exceeds the byte capacity")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise SnapshotError("native display manifest contains a duplicate field")
            result[key] = value
        return result
    value = _capture_snapshot_job(json.loads(data, object_pairs_hook=pairs))
    if set(value) != {"version", "owner", "revision", "nodes", "prototypes", "occurrences"}:
        raise SnapshotError("invalid native display manifest fields")
    if (type(value["nodes"]) is not list or not 0 < len(value["nodes"]) <= 100_000
            or type(value["occurrences"]) is not list or not 0 < len(value["occurrences"]) <= 100_000
            or type(value["prototypes"]) is not dict or not 0 < len(value["prototypes"]) <= 100_000):
        raise SnapshotError("native display inventory exceeds its limits")
    return value


class PreparedDocumentSnapshot:
    """Single-use staged packet; close only before dispatch or after cleanup proof.

    Unknown cleanup retains the directory and its global count/byte charge.
    Dropping the Python reference cannot delete files beneath an active consumer.
    The process/service owner must reclaim the consumer before retiring such a
    packet; this class never infers that from transport-process termination.
    """

    def __init__(self, manifest, assets, job, deadline, provenance, *, input_hash=None):
        from ._document.meshing import unpack_mesh

        global _staged_bytes
        value = _manifest(manifest)
        if type(assets) not in (dict, MappingProxyType) or any(type(k) is not str or type(v) is not bytes for k, v in assets.items()):
            raise TypeError("native snapshot assets require immutable byte values")
        sizes = {identity: {"bytes": len(payload)} for identity, payload in assets.items()}
        policy = native_mesh_options(job)
        descriptor = document_descriptor({"version": value["version"], "owner": value["owner"],
            "revision": value["revision"], "manifest": {"sha256": hashlib.sha256(manifest).hexdigest(), "bytes": len(manifest)},
            "assets": sizes, "meshing": policy})
        used = {}
        for row in value["prototypes"].values():
            if type(row) is not dict or set(row) != {"mesh", "bytes"} or type(row["mesh"]) is not str:
                raise SnapshotError("invalid native display prototype binding")
            if row["mesh"] in used and used[row["mesh"]] != row["bytes"]:
                raise SnapshotError("conflicting native display asset lengths")
            used[row["mesh"]] = row["bytes"]
        if used != {key: row["bytes"] for key, row in sizes.items()}:
            raise SnapshotError("native display asset inventory does not match its manifest")
        self.charge = len(manifest) + sum(len(data) for data in assets.values()) + provenance["outputBytes"]
        self.root = None
        self._slot = None
        self._owned_service = None
        self._outputs = provenance["outputs"]
        self.cleanup = RenderCleanup(acknowledged=True)
        self._used = False
        self._rendering = False
        self._closed = False
        with _guard:
            if len(_owners) >= MAX_PREPARED_SNAPSHOTS or _staged_bytes + self.charge > MAX_STAGED_BYTES:
                raise SnapshotError("native snapshot staging capacity is full; retained consumers require reclamation")
            _owners.add(self)
            _staged_bytes += self.charge
        try:
            _remaining(deadline - CLEANUP_SECONDS)
            from .snapshot_staging import StagingSlot, write_staged
            cache_root = Path(provenance["storeRoot"])
            self._slot = StagingSlot(cache_root, self.charge)
            self.root = self._slot.assets
            output_root = self._slot.path / "outputs"
            output_root.mkdir(mode=0o700)
            self._private_paths = tuple(output_root / f"{index}.png" for index in range(len(self._outputs)))
            write_staged(self.root / descriptor["manifest"]["sha256"], manifest)
            for identity, payload in assets.items():
                _remaining(deadline - CLEANUP_SECONDS)
                if hashlib.sha256(payload).hexdigest() != identity:
                    raise SnapshotError("native display mesh hash mismatch")
                header, _buffers = unpack_mesh(payload)
                if header["options"] != policy:
                    raise SnapshotError("native display mesh policy does not match snapshot quality")
                write_staged(self.root / identity, payload)
            resolved = {"kind": "step", "rootPath": str(self.root), "inputPath": job.get("input", ""), "document": descriptor}
            if input_hash is not None:
                resolved["inputHash"] = input_hash
            private_job = {**job, "outputs": [{**row, "path": str(path)} for row, path in zip(job["outputs"], self._private_paths)],
                           "resolved": resolved}
            self.operation = normalize_operation({"packet": {"single": True, "jobs": [private_job]},
                "runtimeRoot": provenance["runtimeRoot"], "storeRoot": str(cache_root),
                "encoder": None, "deadline": deadline})
            _remaining(deadline - CLEANUP_SECONDS)
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(f"Native snapshot preparation cleanup failed: {cleanup_error}")
            raise

    def close(self):
        global _staged_bytes
        if self._rendering:
            raise SnapshotError("native snapshot render is active; await its cleanup receipt before closing")
        if self._owned_service is not None:
            self._owned_service.close()
            self._owned_service = None
            self.cleanup.acknowledged = True
        with _guard:
            if self._closed:
                return
            if not self.cleanup.acknowledged:
                raise SnapshotError("native snapshot assets retained until renderer cleanup is acknowledged")
            if self._slot is not None:
                self._slot.release(self.cleanup)
            self._closed = True
            _owners.remove(self)
            _staged_bytes -= self.charge

    async def render(self, *, service=None, progress=None, narrate=None):
        if self._used or self._closed:
            raise SnapshotError("prepared native snapshot is single-use")
        self._used = True
        self._rendering = True
        from .snapshot_service import SnapshotService, current_snapshot_service
        service = service or current_snapshot_service()
        own_service = service is None
        close_attempted = False
        failure = None
        published = []
        try:
            _remaining(self.operation["deadline"] - CLEANUP_SECONDS)
            if own_service:
                service = SnapshotService()
                self._owned_service = service
            result = await service.render_operation(self.operation, progress=progress, narrate=narrate, cleanup=self.cleanup)
            if own_service:
                close_attempted = True
                try:
                    service.close()
                except BaseException:
                    self.cleanup.acknowledged = False
                    raise
                self._owned_service = None
                self.cleanup.acknowledged = True
            if not self.cleanup.acknowledged:
                raise SnapshotError("native snapshot cannot publish outputs before renderer cleanup is acknowledged")
            return publish_outputs(result, self._outputs, self._private_paths, self.operation["deadline"], published=published)
        except BaseException as error:
            failure = error
            raise
        finally:
            try:
                if own_service and service is not None and not close_attempted:
                    # Public close acknowledgement also reclaims a poisoned local owner.
                    service.close()
                    self._owned_service = None
                    self.cleanup.acknowledged = True
            except BaseException as cleanup_error:
                self.cleanup.acknowledged = False
                if failure is None:
                    failure = cleanup_error
                    raise
                failure.add_note(f"Native snapshot owner cleanup failed: {cleanup_error}")
            finally:
                self._rendering = False
                if self.cleanup.acknowledged:
                    retirement_error = None
                    try:
                        self.close()
                    except BaseException as cleanup_error:
                        if failure is None:
                            failure = retirement_error = cleanup_error
                        else:
                            failure.add_note(f"Native snapshot asset cleanup failed: {cleanup_error}")
                    if failure is not None:
                        try:
                            rollback_outputs(published)
                        except BaseException as output_error:
                            failure.add_note(f"Native snapshot failed output rollback: {output_error}")
                    if retirement_error is not None:
                        raise retirement_error


def prepare_display_snapshot(product, job, *, timeout=60):
    """Capture a resident value product on its caller, before browser submission."""
    normalized, deadline, provenance = _job(job, timeout)
    from ._document import display as display_module
    from ._document.display import DisplayProduct, MeshAsset
    if type(product) is not DisplayProduct or display_module._products.get(id(product)) is not product:
        raise TypeError("native snapshots require an attested DisplayProduct")
    if type(product.assets) not in (dict, MappingProxyType):
        raise TypeError("native snapshots require immutable DisplayProduct assets")
    value = _manifest(product.manifest)
    if value["owner"] != product.owner_id or value["revision"] != product.revision_id:
        raise SnapshotError("native display product revision differs from its manifest")
    if type(product.prototype_assets) not in (dict, MappingProxyType) or dict(product.prototype_assets) != {
            key: row["mesh"] for key, row in value["prototypes"].items()}:
        raise SnapshotError("native display product prototype inventory differs from its manifest")
    assets = {}
    for identity, asset in product.assets.items():
        if type(asset) is not MeshAsset or asset.identity != identity:
            raise TypeError("native display product contains an invalid asset")
        assets[identity] = asset.payload
    return PreparedDocumentSnapshot(product.manifest, assets, normalized, deadline, provenance)


def prepare_saved_step_snapshot(path, job, *, dispatcher, timeout=60):
    """Import actual captured STEP + companion bytes, never a source/resident alias.

    The caller explicitly owns the document dispatcher. Its immutable display
    response is copied into a prepared packet before releasing the native lease.
    File capture, queueing, import, meshing, browser work and cleanup consume one
    deadline; no stage receives a fresh whole-job timeout.
    """
    normalized, deadline, provenance = _job(job, timeout, saved_path=path)
    path = Path(provenance["inputPath"])
    normalized["input"] = str(path)
    payload = read_regular(path, MAX_STEP_BYTES)
    if not payload or len(payload) > MAX_STEP_BYTES:
        raise SnapshotError("native saved STEP exceeds the captured byte capacity")
    from ._document.annotations import companion_path, MAX_BYTES as MAX_ANNOTATION_BYTES
    from ._document.sources import CapturedInput
    annotation_path = companion_path(path)
    try:
        annotation_bytes = read_regular(annotation_path.resolve(), MAX_ANNOTATION_BYTES)
    except FileNotFoundError:
        companion = None
    else:
        companion = CapturedInput(annotation_path, annotation_bytes, hashlib.sha256(annotation_bytes).hexdigest())
    digest = hashlib.sha256(payload).hexdigest()
    lease = None
    def request(operation, *, cleanup=False, **kwargs):
        ticket = dispatcher.submit(operation, timeout=min(300, _remaining(deadline - (0 if cleanup else CLEANUP_SECONDS))),
                                   context=provenance["context"], **kwargs)
        try:
            return ticket.result()
        except BaseException:
            ticket.cancel()
            try:
                ticket.result()
            except BaseException:
                pass
            raise
    prepared = None
    try:
        response, _ = request("open_step", path=str(path), digest=digest,
            annotations=None if companion is None else {"digest": companion.digest, "bytes": len(companion.data)},
            payloads=(payload,) if companion is None else (payload, companion.data))
        lease = response["result"]["revision"]
        response, buffers = request("display", lease=lease, options=native_mesh_options(normalized), known=[])
        rows = response["result"]["assets"]
        if type(rows) is not list or len(buffers) != len(rows) + 1:
            raise SnapshotError("native display response has an incomplete asset inventory")
        assets = {}
        for row, buffer in zip(rows, buffers[1:]):
            if (type(row) is not dict or set(row) != {"identity", "bytes"} or row["identity"] in assets
                    or type(buffer) is not bytes or len(buffer) != row["bytes"]):
                raise SnapshotError("invalid native display response asset")
            assets[row["identity"]] = buffer
        prepared = PreparedDocumentSnapshot(buffers[0], assets, normalized, deadline, provenance, input_hash=digest)
        request("release", cleanup=True, lease=lease)
        lease = None
        return prepared
    except BaseException as error:
        if prepared is not None:
            try:
                prepared.close()
            except BaseException as cleanup_error:
                error.add_note(f"Native snapshot preparation cleanup failed: {cleanup_error}")
        if lease is not None:
            try:
                request("release", cleanup=True, lease=lease)
            except BaseException as cleanup_error:
                error.add_note(f"Native revision release failed: {cleanup_error}")
        raise
