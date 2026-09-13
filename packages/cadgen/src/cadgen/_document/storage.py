"""Disposable document checkpoints: one transactional catalog and opaque blobs.

This module has no kernel, native-handle codec, or legacy store reader. A caller
owns source/exchange files and passes only immutable payload bytes and JSON value
metadata. Committed geometry and successful export receipts are separate facts.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import struct
import time
from typing import Any, Iterator, Mapping
from uuid import uuid4


SCHEMA_VERSION = 2
ENGINE_VERSION = "document-catalog-v2"
_OWNER = b"CADGEN DOCUMENT STORE\x00v1\n"
_OWNER_READY = _OWNER + b"initialized\n"
_MAGIC = "cadgen.document.catalog"
_BLOB_MAGIC = b"CADGEN DOCUMENT BLOB\x00\x01"
_APP_ID = 0x43474431
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class StorageError(RuntimeError):
    pass


class StorageBusy(StorageError):
    pass


class StorageCorrupt(StorageError):
    pass


class LeaseExpired(StorageError):
    pass


class StageExpired(StorageError):
    pass


class _Guard:
    """Shared open-catalog lifetime; exclusive initialization/version reset."""
    def __init__(self, path: Path):
        if path.is_symlink():
            raise StorageError("document store guard cannot be a symlink")
        self.fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        self.locked = False
        self.overlapped = None

    def lock(self, *, exclusive: bool, blocking: bool = True) -> None:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            import msvcrt

            class Overlapped(ctypes.Structure):
                _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                            ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                            ("hEvent", wintypes.HANDLE)]

            self.overlapped = Overlapped()
            api = ctypes.WinDLL("kernel32", use_last_error=True).LockFileEx
            api.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                            wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped))
            api.restype = wintypes.BOOL
            flags = (2 if exclusive else 0) | (0 if blocking else 1)
            if not api(msvcrt.get_osfhandle(self.fd), flags, 0, 1, 0,
                       ctypes.byref(self.overlapped)):
                raise StorageBusy("document store is in use")
        else:
            import fcntl
            flags = (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            if not blocking:
                flags |= fcntl.LOCK_NB
            try:
                fcntl.flock(self.fd, flags)
            except BlockingIOError as exc:
                raise StorageBusy("document store is in use") from exc
        self.locked = True

    def unlock(self) -> None:
        if not self.locked:
            return
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            import msvcrt
            api = ctypes.WinDLL("kernel32", use_last_error=True).UnlockFileEx
            api.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                            wintypes.DWORD, ctypes.c_void_p)
            api.restype = wintypes.BOOL
            if not api(msvcrt.get_osfhandle(self.fd), 0, 1, 0, ctypes.byref(self.overlapped)):
                raise StorageError("cannot release document store guard")
        else:
            import fcntl
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        self.locked = False

    def close(self) -> None:
        self.unlock()
        os.close(self.fd)


def _json(value: Any) -> str:
    def check(item):
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item:
                check(child)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                check(child)
            return
        raise TypeError("checkpoint metadata requires finite JSON values, not runtime objects")
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _metadata(value: Mapping[str, Any]) -> str:
    if type(value) is not dict or type(value.get("version")) is not int or value["version"] < 1:
        raise ValueError("checkpoint metadata requires a positive integer version")
    return _json(value)


def _text(value: str, name: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _deadline(seconds: float) -> float:
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("lease duration must be positive and finite")
    return time.time() + seconds


def _sync_directory(path: Path) -> None:
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


@dataclass(frozen=True)
class Stage:
    revision_id: str
    document_id: str
    expires_at: float


@dataclass(frozen=True)
class Checkpoint:
    revision_id: str
    document_id: str
    metadata: dict[str, Any]
    payloads: dict[str, bytes]


@dataclass(frozen=True)
class ExportReceipt:
    product: str
    digest: str
    metadata: dict[str, Any]


class Lease:
    def __init__(self, store: Catalog, token: str, revision_id: str, expires_at: float):
        self.store, self.token = store, token
        self.revision_id, self.expires_at = revision_id, expires_at
        self.released = False

    def renew(self, seconds: float = 60) -> None:
        deadline = _deadline(seconds)
        with self.store._transaction():
            self.store._check_lease(self)
            self.store._db.execute("UPDATE leases SET expires_at=? WHERE token=?", (deadline, self.token))
        self.expires_at = deadline

    def release(self) -> None:
        if self.released:
            return
        with self.store._transaction():
            self.store._db.execute("DELETE FROM leases WHERE token=?", (self.token,))
        self.store._local_leases.discard(self.token)
        self.released = True

    def __enter__(self) -> Lease:
        with self.store._transaction(write=False):
            self.store._check_lease(self)
        return self

    def __exit__(self, *exc) -> None:
        self.release()


_DDL = (
    "CREATE TABLE catalog_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), magic TEXT NOT NULL, schema_version INTEGER NOT NULL, engine_version TEXT NOT NULL, epoch TEXT NOT NULL)",
    "CREATE TABLE blobs (digest TEXT PRIMARY KEY, size INTEGER NOT NULL)",
    "CREATE TABLE revisions (id TEXT PRIMARY KEY, document_id TEXT NOT NULL, metadata TEXT NOT NULL, manifest_hash TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('staged','committed')), created_at REAL NOT NULL, stage_deadline REAL NOT NULL)",
    "CREATE TABLE revision_blobs (revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE, role TEXT NOT NULL, digest TEXT NOT NULL REFERENCES blobs(digest), PRIMARY KEY(revision_id,role))",
    "CREATE TABLE heads (document_id TEXT PRIMARY KEY, revision_id TEXT NOT NULL REFERENCES revisions(id))",
    "CREATE TABLE leases (token TEXT PRIMARY KEY, revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE, expires_at REAL NOT NULL)",
    "CREATE TABLE exports (revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE, product TEXT NOT NULL, digest TEXT NOT NULL, metadata TEXT NOT NULL, receipt_hash TEXT NOT NULL, PRIMARY KEY(revision_id,product))",
    "CREATE INDEX revision_documents ON revisions(document_id,created_at)",
    "CREATE INDEX lease_revisions ON leases(revision_id,expires_at)",
    "CREATE INDEX payload_references ON revision_blobs(digest)",
)


class Catalog:
    """Thread-affine catalog. Open instances prevent incompatible hard reset.

    Leases have explicit deadlines, not a GC grace period. A lease must be
    renewed before expiry and released before closing its catalog. Read methods
    open immutable payload descriptors in a short admission transaction, then
    verify bytes outside the writer lock. Admitted reads survive lease expiry:
    POSIX retains opened inodes; Windows reclamation defers open files.

    Initial publication writes and fsyncs blob files under the writer lock.
    Large-payload staging therefore serializes writers; an incoming-payload
    reservation protocol is required before moving that IO outside the lock.
    """
    def __init__(self, root: Path, *, engine_version: str = ENGINE_VERSION,
                 schema_version: int = SCHEMA_VERSION):
        _text(engine_version, "engine version")
        if type(schema_version) is not int or schema_version < 1:
            raise ValueError("schema version must be positive")
        root = Path(root)
        if root.is_symlink():
            raise StorageError("document store root cannot be a symlink")
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve()
        self._closed = False
        self._local_leases: set[str] = set()
        self._db = None
        self._owner_ready = False
        sentinel = self.root / "OWNER"
        if not sentinel.exists() and any(p.name != "GUARD" for p in self.root.iterdir()):
            raise StorageError("refusing to initialize an unowned nonempty directory")
        self._guard = _Guard(self.root / "GUARD")
        try:
            for _ in range(4):
                self._guard.lock(exclusive=False)
                if sentinel.exists():
                    self._verify_owner()
                    self._connect()
                    meta = self._meta()
                    if (meta is not None and self._owner_ready
                            and meta[1:3] == (schema_version, engine_version)):
                        self.epoch = meta[3]
                        self._verify_epoch()
                        return
                    self._disconnect()
                self._guard.unlock()
                self._guard.lock(exclusive=True, blocking=False)
                if sentinel.exists():
                    self._verify_owner()
                else:
                    if any(p.name != "GUARD" for p in self.root.iterdir()):
                        raise StorageError("refusing to initialize an unowned directory")
                    with sentinel.open("xb") as stream:
                        stream.write(_OWNER)
                        stream.flush()
                        os.fsync(stream.fileno())
                    _sync_directory(self.root)
                self._connect()
                meta = self._meta()
                if meta is None or meta[1:3] != (schema_version, engine_version):
                    self._initialize(schema_version, engine_version)
                self._mark_ready()
                self._disconnect()
                self._guard.unlock()
            raise StorageBusy("document store version changed during initialization")
        except BaseException:
            self._disconnect()
            self._guard.close()
            self._closed = True
            raise

    def _verify_owner(self) -> None:
        path = self.root / "OWNER"
        if path.is_symlink() or path.read_bytes() not in (_OWNER, _OWNER_READY):
            raise StorageError("document store ownership sentinel is invalid")
        self._owner_ready = path.read_bytes() == _OWNER_READY
        for name in ("catalog.sqlite3", "catalog.sqlite3-wal", "catalog.sqlite3-shm", "objects"):
            if (self.root / name).is_symlink():
                raise StorageError("document store managed paths cannot be symlinks")

    def _mark_ready(self) -> None:
        temporary = self.root / (".owner-ready-" + uuid4().hex)
        try:
            with temporary.open("xb") as stream:
                stream.write(_OWNER_READY)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.root / "OWNER")
            _sync_directory(self.root)
            self._owner_ready = True
        finally:
            temporary.unlink(missing_ok=True)

    def _connect(self) -> None:
        try:
            self._db = sqlite3.connect(self.root / "catalog.sqlite3", timeout=10,
                                       isolation_level=None)
            self._db.execute("PRAGMA foreign_keys=ON")
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("PRAGMA busy_timeout=10000")
        except sqlite3.DatabaseError as exc:
            if getattr(exc, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise StorageBusy("document catalog is in use") from exc
            raise StorageCorrupt("document catalog is unreadable") from exc

    def _disconnect(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None

    def _meta(self):
        try:
            tables = {row[0] for row in self._db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not tables:
                if self._owner_ready:
                    raise StorageCorrupt("initialized document catalog is empty or truncated")
                return None
            row = self._db.execute("SELECT magic,schema_version,engine_version,epoch FROM catalog_meta WHERE singleton=1").fetchone()
            if row is None or row[0] != _MAGIC:
                raise StorageCorrupt("document catalog magic is invalid")
            if type(row[1]) is not int or row[1] < 1 or type(row[2]) is not str or not row[2]:
                raise StorageCorrupt("document catalog version metadata is invalid")
            if self._db.execute("PRAGMA application_id").fetchone()[0] != _APP_ID:
                raise StorageCorrupt("document catalog application identity is invalid")
            if self._db.execute("PRAGMA user_version").fetchone()[0] != row[1]:
                raise StorageCorrupt("document catalog schema metadata disagrees")
            return row
        except sqlite3.DatabaseError as exc:
            raise StorageCorrupt("document catalog metadata is unreadable") from exc

    def _initialize(self, schema_version: int, engine_version: str) -> None:
        epoch = uuid4().hex
        objects = self.root / "objects"
        objects.mkdir(exist_ok=True)
        (objects / epoch).mkdir()
        _sync_directory(objects)
        with self._transaction():
            self._db.execute("PRAGMA defer_foreign_keys=ON")
            names = [row[0] for row in self._db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            # This entire database is sentinel-owned disposable state.
            for name in reversed(names):
                self._db.execute('DROP TABLE "' + name.replace('"', '""') + '"')
            for statement in _DDL:
                self._db.execute(statement)
            self._db.execute(f"PRAGMA application_id={_APP_ID}")
            self._db.execute(f"PRAGMA user_version={schema_version}")
            self._db.execute("INSERT INTO catalog_meta VALUES(1,?,?,?,?)",
                             (_MAGIC, schema_version, engine_version, epoch))
        # The new catalog cannot reference older epochs. Interrupted deletion is
        # harmless; recovery finishes it while no checkpoint can name old files.
        for old in objects.iterdir():
            if old.name != epoch and re.fullmatch(r"[0-9a-f]{32}", old.name):
                if old.is_symlink():
                    raise StorageCorrupt("document blob epoch cannot be a symlink")
                shutil.rmtree(old)

    def _verify_epoch(self) -> None:
        if type(self.epoch) is not str or not re.fullmatch(r"[0-9a-f]{32}", self.epoch):
            raise StorageCorrupt("document blob epoch is invalid")
        self._objects = self.root / "objects" / self.epoch
        if self._objects.is_symlink() or not self._objects.is_dir():
            raise StorageCorrupt("document blob epoch is unavailable")

    @contextmanager
    def _transaction(self, *, write: bool = True):
        if self._closed or self._db is None:
            raise StorageError("document catalog is closed")
        try:
            self._db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield
                self._commit()
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
        except sqlite3.DatabaseError as exc:
            if getattr(exc, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise StorageBusy("document catalog is in use") from exc
            raise StorageCorrupt("document catalog transaction failed") from exc

    def _commit(self) -> None:
        self._db.execute("COMMIT")

    def _open_blob(self, digest: str, expected_size: int) -> int:
        if type(digest) is not str or not _DIGEST.fullmatch(digest):
            raise StorageCorrupt("invalid checkpoint payload digest")
        if type(expected_size) is not int or expected_size < 0:
            raise StorageCorrupt("invalid checkpoint payload size")
        path = self._objects / digest
        fd = None
        try:
            if path.is_symlink():
                raise StorageCorrupt("checkpoint payload cannot be a symlink")
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size != len(_BLOB_MAGIC) + 8 + expected_size:
                raise StorageCorrupt("checkpoint payload size or file type is invalid")
            return fd
        except BaseException as exc:
            if fd is not None:
                os.close(fd)
            if isinstance(exc, OSError):
                raise StorageCorrupt("checkpoint payload is unavailable") from exc
            raise

    def _read_open_blob(self, fd: int, digest: str, expected_size: int) -> bytes:
        try:
            with os.fdopen(os.dup(fd), "rb") as stream:
                raw = stream.read(expected_size + len(_BLOB_MAGIC) + 9)
        except OSError as exc:
            raise StorageCorrupt("checkpoint payload is unavailable") from exc
        header = len(_BLOB_MAGIC) + 8
        if not raw.startswith(_BLOB_MAGIC) or len(raw) < header:
            raise StorageCorrupt("checkpoint payload magic is invalid")
        size = struct.unpack(">Q", raw[len(_BLOB_MAGIC):header])[0]
        payload = raw[header:]
        if size != expected_size or len(payload) != size or hashlib.sha256(payload).hexdigest() != digest:
            raise StorageCorrupt("checkpoint payload failed integrity verification")
        return payload

    def _read_blob(self, digest: str, expected_size: int) -> bytes:
        fd = self._open_blob(digest, expected_size)
        try:
            return self._read_open_blob(fd, digest, expected_size)
        finally:
            os.close(fd)

    def _open_payloads(self, rows):
        opened = []
        try:
            for role, digest, size in rows:
                opened.append((role, digest, size, self._open_blob(digest, size)))
            return opened
        except BaseException:
            for _, _, _, fd in opened:
                os.close(fd)
            raise

    def _put_blob(self, payload: bytes) -> str:
        if type(payload) is not bytes:
            raise TypeError("checkpoint payloads must be immutable bytes")
        digest = hashlib.sha256(payload).hexdigest()
        path = self._objects / digest
        existing = self._db.execute("SELECT size FROM blobs WHERE digest=?", (digest,)).fetchone()
        if existing is not None and existing != (len(payload),):
            raise StorageCorrupt("checkpoint payload catalog size disagrees")
        if path.exists():
            self._read_blob(digest, len(payload))
        else:
            if existing is not None and self._db.execute("SELECT 1 FROM revision_blobs WHERE digest=? LIMIT 1", (digest,)).fetchone():
                raise StorageCorrupt("a referenced checkpoint payload is missing")
            # A failed GC phase-two commit may restore an unreferenced blob row
            # after unlink. Exact supplied bytes repair that disposable row.
            temporary = self._objects / (".write-" + uuid4().hex)
            try:
                with temporary.open("xb") as stream:
                    stream.write(_BLOB_MAGIC + struct.pack(">Q", len(payload)) + payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
                _sync_directory(self._objects)
            finally:
                temporary.unlink(missing_ok=True)
        self._db.execute("INSERT OR IGNORE INTO blobs VALUES(?,?)", (digest, len(payload)))
        return digest

    def stage(self, document_id: str, metadata: dict, payloads: dict[str, bytes],
              *, seconds: float = 300) -> Stage:
        document_id = _text(document_id, "document identity")
        encoded = _metadata(metadata)
        deadline = _deadline(seconds)
        if type(payloads) is not dict:
            raise TypeError("checkpoint payloads require a role-to-bytes mapping")
        for role, data in payloads.items():
            _text(role, "payload role")
            if type(data) is not bytes:
                raise TypeError("checkpoint payloads must be immutable bytes")
        revision = uuid4().hex
        with self._transaction():
            self._db.execute("INSERT INTO revisions VALUES(?,?,?,'','staged',?,?)",
                             (revision, document_id, encoded, time.time(), deadline))
            for role, data in payloads.items():
                digest = self._put_blob(data)
                self._db.execute("INSERT INTO revision_blobs VALUES(?,?,?)", (revision, role, digest))
            manifest = self._manifest_hash(document_id, encoded, self._payload_rows(revision))
            self._db.execute("UPDATE revisions SET manifest_hash=? WHERE id=?", (manifest, revision))
        return Stage(revision, document_id, deadline)

    def _payload_rows(self, revision_id: str):
        return self._db.execute("SELECT r.role,b.digest,b.size FROM revision_blobs r JOIN blobs b ON b.digest=r.digest WHERE r.revision_id=? ORDER BY r.role", (revision_id,)).fetchall()

    @staticmethod
    def _manifest_hash(document_id: str, metadata: str, payloads) -> str:
        encoded = _json([document_id, metadata, [list(row) for row in payloads]])
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _verified_manifest(self, revision_id: str):
        row = self._db.execute("SELECT document_id,metadata,manifest_hash FROM revisions WHERE id=?", (revision_id,)).fetchone()
        if row is None:
            raise StorageCorrupt("checkpoint revision is missing")
        payloads = self._payload_rows(revision_id)
        try:
            metadata = json.loads(row[1])
            _metadata(metadata)
            if self._manifest_hash(row[0], row[1], payloads) != row[2]:
                raise StorageCorrupt("checkpoint manifest failed integrity verification")
        except (ValueError, TypeError) as exc:
            raise StorageCorrupt("checkpoint metadata is invalid") from exc
        return row[0], metadata, payloads

    def checkpoint(self, stage: Stage, *, expected_head: str | None) -> bool:
        """Commit a staged checkpoint; CAS failure leaves a pinnable old result."""
        opened = []
        try:
            with self._transaction():
                self._check_stage(stage)
                _, _, payloads = self._verified_manifest(stage.revision_id)
                opened = self._open_payloads(payloads)
            # Large payload verification does not serialize unrelated writers.
            for _, digest, size, fd in opened:
                self._read_open_blob(fd, digest, size)
        finally:
            for _, _, _, fd in opened:
                os.close(fd)
        with self._transaction():
            # Expiry/GC or a competing checkpoint may win while bytes are read.
            self._check_stage(stage)
            _, _, current_payloads = self._verified_manifest(stage.revision_id)
            if current_payloads != payloads:
                raise StorageCorrupt("checkpoint payload manifest changed during verification")
            self._db.execute("UPDATE revisions SET state='committed' WHERE id=?", (stage.revision_id,))
            current = self._db.execute("SELECT revision_id FROM heads WHERE document_id=?", (stage.document_id,)).fetchone()
            if (current[0] if current else None) != expected_head:
                return False
            self._db.execute("INSERT INTO heads VALUES(?,?) ON CONFLICT(document_id) DO UPDATE SET revision_id=excluded.revision_id", (stage.document_id, stage.revision_id))
            return True

    def _check_stage(self, stage: Stage) -> None:
        row = self._db.execute("SELECT document_id,state,stage_deadline FROM revisions WHERE id=?", (stage.revision_id,)).fetchone()
        if row != (stage.document_id, "staged", stage.expires_at) or row[2] <= time.time():
            raise StageExpired("checkpoint stage is unavailable or expired")

    def head(self, document_id: str) -> str | None:
        with self._transaction(write=False):
            row = self._db.execute("SELECT revision_id FROM heads WHERE document_id=?", (document_id,)).fetchone()
            return row[0] if row else None

    def lease(self, revision_id: str, *, seconds: float = 60) -> Lease:
        deadline, token = _deadline(seconds), uuid4().hex
        with self._transaction():
            row = self._db.execute("SELECT state FROM revisions WHERE id=?", (revision_id,)).fetchone()
            if row != ("committed",):
                raise KeyError("checkpoint revision is unavailable")
            self._db.execute("INSERT INTO leases VALUES(?,?,?)", (token, revision_id, deadline))
        self._local_leases.add(token)
        return Lease(self, token, revision_id, deadline)

    def _check_lease(self, lease: Lease) -> None:
        if lease.store is not self or lease.released:
            raise LeaseExpired("checkpoint access requires this catalog's live lease")
        row = self._db.execute("SELECT revision_id,expires_at FROM leases WHERE token=?", (lease.token,)).fetchone()
        if row is None or row[0] != lease.revision_id or row[1] <= time.time():
            raise LeaseExpired("checkpoint lease expired")

    def read(self, lease: Lease) -> Checkpoint:
        opened = []
        try:
            with self._transaction():
                self._check_lease(lease)
                document, metadata, rows = self._verified_manifest(lease.revision_id)
                opened = self._open_payloads(rows)
            payloads = {role: self._read_open_blob(fd, digest, size)
                        for role, digest, size, fd in opened}
            return Checkpoint(lease.revision_id, document, metadata, payloads)
        finally:
            for _, _, _, fd in opened:
                os.close(fd)

    def read_partitioned(self, lease: Lease, *, required_roles: frozenset[str],
                         optional_role_limits: Mapping[str, int]) -> Checkpoint:
        """Read required payloads strictly and bounded optional payloads best-effort.

        The caller supplies both partitions from its engine schema; payload data
        cannot reclassify a required role.  The complete immutable row manifest
        is verified before opening any blob.  Optional blob absence or content
        corruption is a cache miss, while required-role and catalog integrity
        failures remain fatal.
        """
        if (type(required_roles) is not frozenset
                or any(type(role) is not str or not role for role in required_roles)):
            raise TypeError("required payload roles require a frozenset of names")
        if (type(optional_role_limits) is not dict
                or any(type(role) is not str or not role
                       or type(limit) is not int or limit < 0
                       for role, limit in optional_role_limits.items())):
            raise TypeError("optional payload roles require exact nonnegative byte limits")
        optional_roles = frozenset(optional_role_limits)
        if required_roles & optional_roles:
            raise ValueError("required and optional payload roles must be disjoint")
        opened_required = []
        opened_optional = []
        try:
            with self._transaction():
                self._check_lease(lease)
                document, metadata, rows = self._verified_manifest(lease.revision_id)
                by_role = {role: (digest, size) for role, digest, size in rows}
                actual = frozenset(by_role)
                if not required_roles <= actual:
                    raise StorageCorrupt("checkpoint required payload is missing")
                if not actual <= required_roles | optional_roles:
                    raise StorageCorrupt("checkpoint payload role is outside the engine schema")
                opened_required = self._open_payloads(
                    [(role, *by_role[role]) for role in sorted(required_roles)])
                for role in sorted(actual & optional_roles):
                    digest, size = by_role[role]
                    if size > optional_role_limits[role]:
                        continue
                    try:
                        fd = self._open_blob(digest, size)
                    except StorageCorrupt:
                        continue
                    opened_optional.append((role, digest, size, fd))
            payloads = {role: self._read_open_blob(fd, digest, size)
                        for role, digest, size, fd in opened_required}
            for role, digest, size, fd in opened_optional:
                try:
                    payloads[role] = self._read_open_blob(fd, digest, size)
                except StorageCorrupt:
                    pass
            return Checkpoint(lease.revision_id, document, metadata, payloads)
        finally:
            for _, _, _, fd in opened_required:
                os.close(fd)
            for _, _, _, fd in opened_optional:
                os.close(fd)

    def record_export(self, lease: Lease, product: str, digest: str, metadata: dict) -> None:
        """Record a completed product; this API never opens or writes its path."""
        _text(product, "export product")
        if type(digest) is not str or not _DIGEST.fullmatch(digest):
            raise ValueError("export digest requires an exact SHA-256")
        encoded = _metadata(metadata)
        with self._transaction():
            self._check_lease(lease)
            previous = self._db.execute("SELECT digest,metadata FROM exports WHERE revision_id=? AND product=?", (lease.revision_id, product)).fetchone()
            if previous is not None and previous != (digest, encoded):
                raise StorageError("an immutable export receipt already names different bytes")
            receipt_hash = hashlib.sha256(_json([lease.revision_id, product, digest, encoded]).encode("utf-8")).hexdigest()
            self._db.execute("INSERT OR IGNORE INTO exports VALUES(?,?,?,?,?)", (lease.revision_id, product, digest, encoded, receipt_hash))

    def exports(self, lease: Lease) -> tuple[ExportReceipt, ...]:
        with self._transaction(write=False):
            self._check_lease(lease)
            result = []
            for product, digest, encoded, checksum in self._db.execute("SELECT product,digest,metadata,receipt_hash FROM exports WHERE revision_id=? ORDER BY product", (lease.revision_id,)):
                try:
                    metadata = json.loads(encoded)
                    _metadata(metadata)
                    valid = (_DIGEST.fullmatch(digest) and
                             hashlib.sha256(_json([lease.revision_id, product, digest, encoded]).encode("utf-8")).hexdigest() == checksum)
                except (ValueError, TypeError) as exc:
                    raise StorageCorrupt("export receipt metadata is invalid") from exc
                if not valid:
                    raise StorageCorrupt("export receipt failed integrity verification")
                result.append(ExportReceipt(product, digest, metadata))
            return tuple(result)

    def gc(self, *, max_items: int = 100) -> dict[str, int]:
        """Reclaim at most max_items rows per category in two durable phases.

        Commit revision removal before touching files. Phase-two rollback can
        restore only unreferenced blob rows, repaired by stage or the next GC.
        Its writer lock excludes a concurrent stage from rebinding a deleted
        blob between the reachability check and unlink.
        """
        if type(max_items) is not int or max_items < 0:
            raise ValueError("GC limit must be a nonnegative integer")
        counts = {"leases": 0, "revisions": 0, "blobs": 0}
        with self._transaction():
            now = time.time()
            for (token,) in self._db.execute("SELECT token FROM leases WHERE expires_at<=? LIMIT ?", (now, max_items)).fetchall():
                self._db.execute("DELETE FROM leases WHERE token=?", (token,))
                counts["leases"] += 1
            candidates = self._db.execute("SELECT id FROM revisions WHERE (state='committed' OR stage_deadline<=?) AND id NOT IN (SELECT revision_id FROM heads) AND id NOT IN (SELECT revision_id FROM leases WHERE expires_at>?) ORDER BY created_at LIMIT ?", (now, now, max_items)).fetchall()
            for (revision,) in candidates:
                self._db.execute("DELETE FROM revisions WHERE id=?", (revision,))
                counts["revisions"] += 1
        with self._transaction():
            blobs = self._db.execute("SELECT digest FROM blobs WHERE digest NOT IN (SELECT digest FROM revision_blobs) LIMIT ?", (max_items,)).fetchall()
            for (digest,) in blobs:
                if not _DIGEST.fullmatch(digest):
                    raise StorageCorrupt("invalid catalog blob path")
                try:
                    (self._objects / digest).unlink(missing_ok=True)
                except PermissionError:
                    # Windows can deny deleting an admitted reader's open file.
                    # Keep the row and retry after that reader closes it.
                    continue
                self._db.execute("DELETE FROM blobs WHERE digest=?", (digest,))
                counts["blobs"] += 1
        return counts

    def recover(self, *, max_files: int = 100) -> int:
        """Remove abandoned temporary/unreferenced files under the writer lock."""
        if type(max_files) is not int or max_files < 0:
            raise ValueError("recovery limit must be nonnegative")
        removed = 0
        with self._transaction():
            for epoch in (self.root / "objects").iterdir():
                if removed >= max_files:
                    break
                if epoch.name == self.epoch or not re.fullmatch(r"[0-9a-f]{32}", epoch.name):
                    continue
                if epoch.is_symlink():
                    raise StorageCorrupt("document blob epoch cannot be a symlink")
                for abandoned in epoch.iterdir():
                    if removed >= max_files:
                        break
                    if abandoned.is_dir() and not abandoned.is_symlink():
                        raise StorageCorrupt("a checkpoint payload path is a directory")
                    abandoned.unlink()
                    removed += 1
                try:
                    epoch.rmdir()
                except OSError:
                    pass
            for path in self._objects.iterdir():
                if removed >= max_files:
                    break
                if path.name.startswith(".write-") or (_DIGEST.fullmatch(path.name) and
                        self._db.execute("SELECT 1 FROM blobs WHERE digest=?", (path.name,)).fetchone() is None):
                    if path.is_dir() and not path.is_symlink():
                        raise StorageCorrupt("a checkpoint payload path is a directory")
                    path.unlink()
                    removed += 1
        return removed

    def close(self) -> None:
        if self._closed:
            return
        if self._local_leases:
            raise StorageBusy("release checkpoint leases before closing the catalog")
        self._disconnect()
        self._guard.close()
        self._closed = True

    def __enter__(self) -> Catalog:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
