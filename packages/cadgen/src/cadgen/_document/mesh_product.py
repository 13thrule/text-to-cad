"""Static native mesh products and truthful staged publication.

This is a producer interface, not a source declaration or old package adapter.
The caller owns grouped scheduler claims. The session pins the exact revision,
shares its display meshes, and accounts every completed filesystem effect before
final attestation. Several renames are not one atomic filesystem transaction.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from .core import ExportConflict
from .display import build_display
from .mesh_encoder import Budget, CHUNK, MAX_EXPORT_BYTES, MeshEncoder, MeshExportProduct
from .meshing import MeshOptions
from .resources import ResourceRequest


@dataclass(frozen=True)
class MeshPublishReceipt:
    owner_id: str
    revision_id: int
    destination: str
    product_identity: str
    sha256: str
    size: int
    previous_sha256: str | None
    action: str
    format: str
    facts: object


@dataclass(frozen=True)
class StagedMeshOutput:
    destination: Path
    staged_path: Path | None
    product: MeshExportProduct


def destination_digest(path, budget):
    """Read only a bounded regular final component; never follow a symlink."""
    budget.check()
    path = Path(path)
    try:
        before = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_EXPORT_BYTES:
        raise ExportConflict("mesh destination is not a bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        raise ExportConflict("mesh destination disappeared during inspection") from None
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_EXPORT_BYTES
                or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)):
            raise ExportConflict("mesh destination changed during inspection")
        digest, count = hashlib.sha256(), 0
        while True:
            budget.check()
            data = stream.read(CHUNK)
            if not data:
                break
            count += len(data)
            if count > MAX_EXPORT_BYTES:
                raise ExportConflict("mesh destination grew beyond capacity")
            digest.update(data)
        after = os.fstat(stream.fileno())
    try:
        current = path.lstat()
    except FileNotFoundError:
        raise ExportConflict("mesh destination disappeared during inspection") from None
    if ((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            or count != after.st_size or not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != (after.st_dev, after.st_ino)):
        raise ExportConflict("mesh destination changed during inspection")
    budget.check()
    return digest.hexdigest()


class MeshProductSession:
    def __init__(self, document, revision_id, *, encoder, work_directory, deadline, cancellation=None):
        document._assert_owner()
        if type(encoder) is not MeshEncoder:
            raise TypeError("mesh producer requires its explicitly owned encoder")
        self._budget = Budget(deadline, cancellation)
        self._budget.check()
        self.document, self.encoder = document, encoder
        self.work_directory = Path(work_directory)
        self._pin = document.pin(revision_id)
        self._closed, self._products, self._staged = False, {}, {}
        self.display = None

    def _check(self):
        self.document._assert_owner()
        if self._closed:
            raise RuntimeError("mesh product session is closed")
        self._budget.check()

    def prepare(self, formats, *, name="model", options=MeshOptions(), previous_display=None):
        self._check()
        if self._products:
            raise RuntimeError("mesh session already has prepared products")
        if type(options) is not MeshOptions:
            raise TypeError("native mesh export quality requires MeshOptions")
        self.display = build_display(self.document, self._pin.revision_id, options=options,
                                     previous=previous_display, cancellation=self._budget)
        self._check()
        # This estimate reserves the largest allowed encoded result. It is an
        # admission estimate, not a promise to measure total JS/native RSS.
        with self.document.admission.admit(ResourceRequest(kind="export", derived_bytes=MAX_EXPORT_BYTES),
                                           cancellation=self._budget):
            products = self.encoder.encode(self.display, formats, name=name, work_directory=self.work_directory,
                                           deadline=self._budget.deadline, cancellation=self._budget.cancellation)
        self._products = {product.format: product for product in products}
        return products

    @contextmanager
    def stage_outputs(self, destinations):
        self._check()
        if not self._products or self._staged or set(destinations) != set(self._products):
            raise ValueError("stage the exact prepared mesh output set once")
        targets = {}
        for format, value in destinations.items():
            raw = Path(value).expanduser().absolute()
            if raw.is_symlink():
                raise ExportConflict("mesh destination cannot be a symlink")
            target = raw.parent.resolve() / raw.name
            if target.suffix.lower() != f".{format}":
                raise ValueError("mesh destination extension differs from its format")
            targets[format] = target
        if (len(set(targets.values())) != len(targets)
                or not set(map(str, targets.values())) <= set(self._pin.revision.required_exports)):
            raise ValueError("every mesh destination must be a distinct declared output obligation")
        staged = []
        try:
            for format, target in targets.items():
                self._check()
                product = self._products[format]
                if destination_digest(target, self._budget) == product.sha256:
                    item = StagedMeshOutput(target, None, product)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tempfile.NamedTemporaryFile(prefix=f".{target.name}-", suffix=".stage",
                                                     dir=target.parent, delete=False) as output:
                        item = StagedMeshOutput(target, Path(output.name), product)
                        staged.append(item)
                        view = memoryview(product.payload)
                        for offset in range(0, len(view), CHUNK):
                            self._check()
                            chunk = view[offset:offset + CHUNK]
                            if output.write(chunk) != len(chunk):
                                raise RuntimeError("short mesh output staging write")
                        output.flush()
                        os.fsync(output.fileno())
                    if destination_digest(item.staged_path, self._budget) != product.sha256:
                        raise RuntimeError("staged mesh output failed verification")
                    continue
                staged.append(item)
            self._staged = {id(item): item for item in staged}
            self._check()
            yield tuple(staged)
        finally:
            self._staged.clear()
            for item in staged:
                if item.staged_path is not None:
                    item.staged_path.unlink(missing_ok=True)

    def publish_staged(self, staged, *, expected_prior_digest, completed=None):
        self._check()
        if self._staged.get(id(staged)) is not staged:
            raise ValueError("mesh publication requires this session's live staged output")
        if (expected_prior_digest is not None and (type(expected_prior_digest) is not str
                or len(expected_prior_digest) != 64 or any(c not in "0123456789abcdef" for c in expected_prior_digest))):
            raise ValueError("expected prior digest must be lowercase SHA-256 or None")
        target, product = staged.destination, staged.product
        def write():
            self._check()
            current = destination_digest(target, self._budget)
            if current != expected_prior_digest:
                raise ExportConflict("mesh destination changed since its selected prior bytes")
            if current == product.sha256:
                action = "verified-existing"
            else:
                if staged.staged_path is None:
                    raise ExportConflict("unstaged mesh destination changed before publication")
                if destination_digest(staged.staged_path, self._budget) != product.sha256:
                    raise ExportConflict("staged mesh bytes changed before publication")
                if destination_digest(target, self._budget) != expected_prior_digest:
                    raise ExportConflict("mesh destination changed during publication")
                self._check()
                os.replace(staged.staged_path, target)
                action = "written"
            receipt = MeshPublishReceipt(self.document.owner_id, self._pin.revision_id, str(target),
                product.identity, product.sha256, len(product.payload), current, action, product.format, product.facts)
            if completed is not None:
                completed(receipt)
            if destination_digest(target, self._budget) != product.sha256:
                raise ExportConflict("mesh destination changed at publication")
            self._check()
            return receipt
        return self.document.publish_export(self._pin, str(target), write)

    def close(self):
        self.document._assert_owner()
        if not self._closed:
            self._pin.release()
            self._closed = True

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *_exc):
        self.close()
