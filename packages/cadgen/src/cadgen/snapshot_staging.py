"""Persistent native snapshot slots, released only by acknowledged ownership.

An atomic directory claim survives its caller process. No PID/age heuristic may
free a slot: the browser worker can outlive that caller. Four slots, each charged
at its maximum admitted size, bound leftovers across independent CLI processes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil

from .snapshot_document_input import MAX_ASSET_BYTES, MAX_MANIFEST_BYTES, read_regular
from .snapshot_document_outputs import MAX_OUTPUT_BYTES

MAX_SLOTS = 4
MAX_SLOT_BYTES = MAX_ASSET_BYTES + MAX_MANIFEST_BYTES + MAX_OUTPUT_BYTES


def write_staged(path, payload):
    """Create each private file once; a substituted FIFO/symlink is never opened."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)


class StagingSlot:
    def __init__(self, cache_root, size):
        if type(size) is not int or not 0 < size <= MAX_SLOT_BYTES:
            raise ValueError("native snapshot staging exceeds a slot's byte capacity")
        self.catalog = Path(cache_root) / "runtime" / "native-snapshot-staging"
        self.catalog.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = None
        self.closed = False
        self.token = secrets.token_hex(32)
        for index in range(MAX_SLOTS):
            candidate = self.catalog / str(index)
            try:
                candidate.mkdir(mode=0o700)
            except FileExistsError:
                continue
            self.path = candidate
            break
        if self.path is None:
            raise RuntimeError("native snapshot persistent staging capacity is full; retained consumers require proven reclamation")
        self.receipt = json.dumps({"version": 1, "owner": self.token, "bytes": size}, separators=(",", ":")).encode()
        # A crash before this marker is complete leaves the atomic slot occupied.
        # No other caller treats a partial claim as abandoned.
        try:
            write_staged(self.path / "owner.json", self.receipt)
            self.assets = self.path / "assets"
            self.assets.mkdir(mode=0o700)
        except BaseException as error:
            # No capability was published, so this constructor still owns all IO.
            try:
                shutil.rmtree(self.path)
            except BaseException as cleanup_error:
                error.add_note(f"Native snapshot unconsumed slot cleanup failed: {cleanup_error}")
            raise

    def release(self, cleanup):
        from .snapshot_operation import RenderCleanup
        if self.closed:
            return
        if type(cleanup) is not RenderCleanup or not cleanup.acknowledged:
            raise RuntimeError("native snapshot staging requires acknowledged renderer cleanup")
        recorded = read_regular(self.path / "owner.json", len(self.receipt), expected_bytes=len(self.receipt))
        if recorded != self.receipt:
            raise RuntimeError("native snapshot staging ownership changed; refusing release")
        shutil.rmtree(self.path)
        self.closed = True
