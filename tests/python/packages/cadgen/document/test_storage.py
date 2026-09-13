"""Stdlib-only catalog contracts; synthetic byte payloads, no CAD runtime."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cadgen._document import storage
from cadgen._document.storage import (Catalog, LeaseExpired, StageExpired,
                                      StorageBusy, StorageCorrupt, StorageError)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="document-store-v2-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "managed"

    def commit(self, catalog, name="part", payload=b"geometry", expected=None):
        staged = catalog.stage(name, {"version": 1, "label": "sample"}, {"native": payload})
        self.assertTrue(catalog.checkpoint(staged, expected_head=expected))
        return staged.revision_id

    def child(self, script, *args):
        env = dict(os.environ, PYTHONPATH=str(Path(storage.__file__).parents[2]))
        return subprocess.Popen([sys.executable, "-c", script, str(self.root), *args],
                                text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=env)

    def finish_child(self, process, data=""):
        out, err = process.communicate(data, timeout=15)
        self.assertEqual(process.returncode, 0, err)
        return out

    def test_stage_checkpoint_cas_restart_and_private_return_data(self):
        with Catalog(self.root) as catalog:
            first = catalog.stage("part", {"version": 1, "tags": ["first"]}, {"native": b"one"})
            self.assertIsNone(catalog.head("part"))
            with self.assertRaises(KeyError):
                catalog.lease(first.revision_id)
            self.assertTrue(catalog.checkpoint(first, expected_head=None))
            competing = catalog.stage("part", {"version": 1}, {"native": b"two"})
            self.assertFalse(catalog.checkpoint(competing, expected_head=None))
            self.assertEqual(catalog.head("part"), first.revision_id)
            with catalog.lease(competing.revision_id) as lease:
                self.assertEqual(catalog.read(lease).payloads, {"native": b"two"})
            with catalog.lease(first.revision_id) as lease:
                result = catalog.read(lease)
                result.metadata["tags"].append("external mutation")
                result.payloads["native"] = b"mutated"
                self.assertEqual(catalog.read(lease).metadata["tags"], ["first"])
                self.assertEqual(catalog.read(lease).payloads, {"native": b"one"})
        with Catalog(self.root) as reopened:
            self.assertEqual(reopened.head("part"), first.revision_id)
            with reopened.lease(first.revision_id) as lease:
                self.assertEqual(reopened.read(lease).payloads["native"], b"one")

    def test_partitioned_read_keeps_required_integrity_and_drops_corrupt_optional(self):
        with Catalog(self.root) as catalog:
            staged = catalog.stage(
                "part", {"version": 1},
                {"manifest": b"required", "mesh-cache": b"optional"})
            self.assertTrue(catalog.checkpoint(staged, expected_head=None))
            with catalog._transaction(write=False):
                optional_digest, = catalog._db.execute(
                    "SELECT digest FROM revision_blobs WHERE revision_id=? AND role='mesh-cache'",
                    (staged.revision_id,),
                ).fetchone()
            (catalog._objects / optional_digest).unlink()
            with catalog.lease(staged.revision_id) as lease:
                with patch.object(catalog, "_open_blob",
                                  side_effect=AssertionError("planning opened payload")):
                    plan = catalog.plan_partitioned_read(
                        lease, required_roles=frozenset({"manifest"}),
                        optional_role_limits={"mesh-cache": 1024})
                self.assertEqual(len(b"optional"), plan.optional_size("mesh-cache"))
                result = catalog.read_partitioned(lease, plan)
                self.assertEqual({"manifest": b"required"}, result.payloads)
                with self.assertRaises(StorageCorrupt):
                    catalog.read(lease)
                with self.assertRaises(StorageCorrupt):
                    required_optional = catalog.plan_partitioned_read(
                        lease, required_roles=frozenset({"mesh-cache"}),
                        optional_role_limits={"manifest": 1024})
                    catalog.read_partitioned(lease, required_optional)

    def test_lease_gc_and_export_receipts_are_revision_bound(self):
        with Catalog(self.root) as catalog:
            old = self.commit(catalog, payload=b"old")
            lease = catalog.lease(old)
            latest = self.commit(catalog, payload=b"new", expected=old)
            digest = hashlib.sha256(b"completed exchange file").hexdigest()
            catalog.record_export(lease, "STEP", digest, {"version": 1, "path": "outside.step"})
            catalog.record_export(lease, "STEP", digest, {"version": 1, "path": "outside.step"})
            with self.assertRaises(StorageError):
                catalog.record_export(lease, "STEP", "0" * 64, {"version": 1})
            receipt, = catalog.exports(lease)
            self.assertEqual((receipt.product, receipt.digest), ("STEP", digest))
            with self.assertRaises(StorageBusy):
                catalog.close()
            self.assertEqual(catalog.gc(max_items=1)["revisions"], 0)
            self.assertEqual(catalog.read(lease).payloads["native"], b"old")
            lease.release()
            self.assertEqual(catalog.gc(max_items=1)["revisions"], 1)
            with self.assertRaises(KeyError):
                catalog.lease(old)
            with catalog.lease(latest) as current:
                self.assertEqual(catalog.exports(current), ())

    def test_deadlines_renewal_and_expired_stage_are_explicit(self):
        with Catalog(self.root) as catalog, patch("cadgen._document.storage.time.time", return_value=1000):
            abandoned = catalog.stage("abandoned", {"version": 1}, {"native": b"abandoned"}, seconds=1)
            revision = self.commit(catalog)
            lease = catalog.lease(revision, seconds=2)
            with patch("cadgen._document.storage.time.time", return_value=1001.5):
                lease.renew(seconds=4)
                with self.assertRaises(StageExpired):
                    catalog.checkpoint(abandoned, expected_head=None)
                self.assertEqual(catalog.read(lease).revision_id, revision)
            with patch("cadgen._document.storage.time.time", return_value=1006):
                with self.assertRaises(LeaseExpired):
                    catalog.read(lease)
                with self.assertRaises(LeaseExpired):
                    lease.renew()
                self.assertEqual(catalog.gc()["leases"], 1)
                self.assertEqual(catalog.gc()["revisions"], 0)
            lease.release()

    def test_version_reset_requires_no_holders_and_preserves_unmanaged_files(self):
        outside = self.root.parent / "source.py"
        outside.write_text("durable source", encoding="utf-8")
        catalog = Catalog(self.root)
        old = self.commit(catalog)
        unrelated = self.root / "author-owned.txt"
        unrelated.write_text("retain", encoding="utf-8")
        with Catalog(self.root) as second:
            self.assertEqual(second.head("part"), old)
        with self.assertRaises(StorageBusy):
            Catalog(self.root, engine_version="document-catalog-next")
        catalog.close()
        with Catalog(self.root, engine_version="document-catalog-next") as reset:
            self.assertIsNone(reset.head("part"))
            with self.assertRaises(KeyError):
                reset.lease(old)
        self.assertEqual(outside.read_text(encoding="utf-8"), "durable source")
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "retain")
        with Catalog(self.root, engine_version="document-catalog-next", schema_version=2) as next_schema:
            self.assertIsNone(next_schema.head("part"))

    def test_unowned_directory_and_managed_symlinks_are_rejected(self):
        self.root.mkdir()
        source = self.root / "source.py"
        source.write_text("retain", encoding="utf-8")
        with self.assertRaises(StorageError):
            Catalog(self.root)
        self.assertEqual(source.read_text(encoding="utf-8"), "retain")
        source.unlink()
        with Catalog(self.root):
            pass
        objects = self.root / "objects"
        objects.rename(self.root.parent / "outside-objects")
        try:
            objects.symlink_to(self.root.parent / "outside-objects", target_is_directory=True)
        except OSError:
            self.skipTest("symbolic links unavailable")
        with self.assertRaises(StorageError):
            Catalog(self.root)

    def test_corrupt_and_truncated_payloads_never_read_as_valid(self):
        with Catalog(self.root) as catalog:
            revision = self.commit(catalog, payload=b"verified payload")
            digest = hashlib.sha256(b"verified payload").hexdigest()
            path = catalog._objects / digest
            original = path.read_bytes()
            with catalog.lease(revision) as lease:
                for corrupted in (b"", original[:10], original[:-1], original + b"extra", b"x" + original[1:]):
                    path.write_bytes(corrupted)
                    with self.subTest(size=len(corrupted)), self.assertRaises(StorageCorrupt):
                        catalog.read(lease)
                path.write_bytes(original)
                self.assertEqual(catalog.read(lease).payloads["native"], b"verified payload")

    def test_truncated_catalog_is_rejected_instead_of_reinitialized(self):
        with Catalog(self.root) as catalog:
            self.commit(catalog)
        (self.root / "catalog.sqlite3").write_bytes(b"")
        with self.assertRaises(StorageCorrupt):
            Catalog(self.root)

    def test_manifest_rejects_valid_json_corruption_and_missing_payload_roles(self):
        with Catalog(self.root) as catalog:
            revision = self.commit(catalog)
            with catalog.lease(revision) as lease:
                original = catalog._db.execute("SELECT metadata FROM revisions WHERE id=?", (revision,)).fetchone()[0]
                catalog._db.execute("UPDATE revisions SET metadata=? WHERE id=?", ('{"version":1,"label":"wrong"}', revision))
                with self.assertRaises(StorageCorrupt):
                    catalog.read(lease)
                catalog._db.execute("UPDATE revisions SET metadata=? WHERE id=?", (original, revision))
                catalog._db.execute("DELETE FROM revision_blobs WHERE revision_id=?", (revision,))
                with self.assertRaises(StorageCorrupt):
                    catalog.read(lease)

    def test_interrupted_blob_publication_rolls_back_and_recovery_is_bounded(self):
        with Catalog(self.root) as catalog:
            put = catalog._put_blob
            def interrupted(payload):
                put(payload)
                raise RuntimeError("interrupted after blob rename")
            with patch.object(catalog, "_put_blob", side_effect=interrupted):
                with self.assertRaises(RuntimeError):
                    catalog.stage("part", {"version": 1}, {"native": b"orphan"})
            self.assertEqual(catalog._db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0], 0)
            (catalog._objects / ".write-interrupted").write_bytes(b"partial")
            self.assertEqual(catalog.recover(max_files=1), 1)
            self.assertEqual(catalog.recover(max_files=1), 1)
            self.assertEqual(catalog.recover(max_files=1), 0)

    def test_native_handles_and_unversioned_or_nonfinite_metadata_are_rejected(self):
        with Catalog(self.root) as catalog:
            for metadata in ({}, {"version": True}, {"version": 1, "value": float("nan")},
                             {"version": 1, "runtime": object()}):
                with self.subTest(metadata=metadata), self.assertRaises((TypeError, ValueError)):
                    catalog.stage("part", metadata, {"native": b"data"})
            with self.assertRaises(TypeError):
                catalog.stage("part", {"version": 1}, {"native": bytearray(b"mutable")})

    def test_crashed_process_leaves_only_recoverable_unreferenced_blob(self):
        with Catalog(self.root):
            pass
        process = self.child('''
import os,sys
from cadgen._document.storage import Catalog
c=Catalog(sys.argv[1]); original=c._put_blob
def stop(payload):
 original(payload); os._exit(17)
c._put_blob=stop
c.stage("part", {"version":1}, {"native":b"crashed"})
''')
        out, err = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 17, err)
        with Catalog(self.root) as recovered:
            self.assertIsNone(recovered.head("part"))
            self.assertEqual(recovered.recover(), 1)
            revision = self.commit(recovered)
            with recovered.lease(revision) as lease:
                self.assertEqual(recovered.read(lease).payloads["native"], b"geometry")

    def test_concurrent_processes_have_one_head_cas_winner(self):
        with Catalog(self.root) as catalog:
            initial = self.commit(catalog)
        script = '''
import json,sys
from cadgen._document.storage import Catalog
with Catalog(sys.argv[1]) as c:
 s=c.stage("part", {"version":1}, {"native":sys.argv[3].encode()})
 print("ready",flush=True); input()
 won=c.checkpoint(s,expected_head=sys.argv[2])
 print(json.dumps({"won":won,"revision":s.revision_id}),flush=True)
'''
        children = [self.child(script, initial, value) for value in ("a", "b")]
        try:
            for child in children:
                self.assertEqual(child.stdout.readline().strip(), "ready")
            for child in children:
                child.stdin.write("go\n")
                child.stdin.flush()
            results = [json.loads(self.finish_child(child).strip()) for child in children]
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
        self.assertEqual(sum(result["won"] for result in results), 1)
        with Catalog(self.root) as catalog:
            winner = next(result["revision"] for result in results if result["won"])
            self.assertEqual(catalog.head("part"), winner)
            for result in results:
                with catalog.lease(result["revision"]) as lease:
                    self.assertIn(catalog.read(lease).payloads["native"], (b"a", b"b"))

    def test_cross_process_lease_blocks_gc_and_incompatible_reset(self):
        with Catalog(self.root) as catalog:
            old = self.commit(catalog)
        process = self.child('''
import sys
from cadgen._document.storage import Catalog
with Catalog(sys.argv[1]) as c:
 with c.lease(sys.argv[2]) as lease:
  print("ready",flush=True); input()
  assert c.read(lease).payloads["native"]==b"geometry"
''', old)
        try:
            self.assertEqual(process.stdout.readline().strip(), "ready")
            with Catalog(self.root) as catalog:
                self.commit(catalog, payload=b"new", expected=old)
                self.assertEqual(catalog.gc()["revisions"], 0)
            with self.assertRaises(StorageBusy):
                Catalog(self.root, engine_version="next")
            self.finish_child(process, "release\n")
            with Catalog(self.root) as catalog:
                self.assertEqual(catalog.gc()["revisions"], 1)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_metadata_reads_use_wal_snapshots_during_unrelated_writer(self):
        with Catalog(self.root) as catalog:
            revision = self.commit(catalog)
            with catalog.lease(revision) as lease, Catalog(self.root) as writer:
                with writer._transaction():
                    writer._db.execute("UPDATE revisions SET created_at=created_at+1")
                    self.assertEqual(catalog.head("part"), revision)
                    self.assertEqual(catalog.exports(lease), ())
                    self.assertIs(lease.__enter__(), lease)

    def test_gc_commit_failures_cannot_restore_references_to_deleted_files(self):
        with Catalog(self.root) as catalog:
            for failed_phase in (1, 2):
                with self.subTest(phase=failed_phase):
                    name = f"part-{failed_phase}"
                    old = self.commit(catalog, name=name, payload=b"old")
                    latest = self.commit(catalog, name=name, payload=b"new", expected=old)
                    original_commit, calls = catalog._commit, []
                    def interrupted_commit():
                        calls.append(None)
                        if len(calls) == failed_phase:
                            raise RuntimeError("injected commit failure")
                        original_commit()
                    with patch.object(catalog, "_commit", side_effect=interrupted_commit):
                        with self.assertRaises(RuntimeError):
                            catalog.gc()
                    if failed_phase == 1:
                        with catalog.lease(old) as lease:
                            self.assertEqual(catalog.read(lease).payloads["native"], b"old")
                    else:
                        with self.assertRaises(KeyError):
                            catalog.lease(old)
                        digest = hashlib.sha256(b"old").hexdigest()
                        self.assertFalse((catalog._objects / digest).exists())
                        self.assertEqual(catalog._db.execute("SELECT size FROM blobs WHERE digest=?", (digest,)).fetchone(), (3,))
                        repaired = self.commit(catalog, name="repair", payload=b"old")
                        with catalog.lease(repaired) as lease:
                            self.assertEqual(catalog.read(lease).payloads["native"], b"old")
                    with catalog.lease(latest) as lease:
                        self.assertEqual(catalog.read(lease).payloads["native"], b"new")
                    catalog.gc()

    def test_process_death_during_each_gc_phase_preserves_retained_payloads(self):
        for failed_phase in (1, 2):
            with self.subTest(phase=failed_phase):
                name = f"part-{failed_phase}"
                with Catalog(self.root) as catalog:
                    old = self.commit(catalog, name=name, payload=b"old")
                    latest = self.commit(catalog, name=name, payload=b"new", expected=old)
                process = self.child('''
import os,sys
from cadgen._document.storage import Catalog
c=Catalog(sys.argv[1]); original=c._commit; count=0
def stop():
 global count
 count+=1
 if count==int(sys.argv[2]): os._exit(19)
 original()
c._commit=stop
c.gc()
''', str(failed_phase))
                _, err = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 19, err)
                with Catalog(self.root) as catalog:
                    self.assertEqual(catalog.head(name), latest)
                    with catalog.lease(latest) as lease:
                        self.assertEqual(catalog.read(lease).payloads["native"], b"new")
                    if failed_phase == 1:
                        with catalog.lease(old) as lease:
                            self.assertEqual(catalog.read(lease).payloads["native"], b"old")
                    else:
                        with self.assertRaises(KeyError):
                            catalog.lease(old)
                        repaired = self.commit(catalog, name="repaired-after-crash", payload=b"old")
                        with catalog.lease(repaired) as lease:
                            self.assertEqual(catalog.read(lease).payloads["native"], b"old")
                    catalog.gc()

    def test_admitted_read_survives_lease_expiry_and_concurrent_gc(self):
        with Catalog(self.root) as catalog:
            old = self.commit(catalog)
        process = self.child('''
import sys
from cadgen._document.storage import Catalog
with Catalog(sys.argv[1]) as c:
 with c.lease(sys.argv[2]) as lease:
  original=c._read_open_blob
  def admitted(fd,digest,size):
   print("opened",flush=True); input()
   return original(fd,digest,size)
  c._read_open_blob=admitted
  assert c.read(lease).payloads["native"]==b"geometry"
  print("verified",flush=True)
''', old)
        try:
            self.assertEqual(process.stdout.readline().strip(), "opened")
            with Catalog(self.root) as catalog:
                self.commit(catalog, payload=b"new", expected=old)
                # Admission already opened descriptors. Model deadline expiry
                # deterministically without introducing timing-sensitive sleeps.
                catalog._db.execute("UPDATE leases SET expires_at=0 WHERE revision_id=?", (old,))
                self.assertEqual(catalog.gc()["revisions"], 1)
            self.assertEqual(self.finish_child(process, "read\n").strip(), "verified")
            with Catalog(self.root) as catalog:
                catalog.gc()
                with self.assertRaises(KeyError):
                    catalog.lease(old)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_stage_cannot_rebind_blob_during_gc_unlink(self):
        with Catalog(self.root) as catalog, Catalog(self.root) as contender:
            old = self.commit(catalog, payload=b"shared")
            self.commit(catalog, payload=b"new", expected=old)
            contender._db.execute("PRAGMA busy_timeout=0")
            target = catalog._objects / hashlib.sha256(b"shared").hexdigest()
            original_unlink, attempts = Path.unlink, []
            def competing_unlink(path, *args, **kwargs):
                if path == target:
                    attempts.append(True)
                    with self.assertRaises(StorageBusy):
                        contender.stage("contender", {"version": 1}, {"native": b"shared"})
                return original_unlink(path, *args, **kwargs)
            with patch.object(Path, "unlink", competing_unlink):
                self.assertEqual(catalog.gc()["blobs"], 1)
            self.assertEqual(attempts, [True])
            revision = self.commit(contender, name="contender", payload=b"shared")
            with contender.lease(revision) as lease:
                self.assertEqual(contender.read(lease).payloads["native"], b"shared")


if __name__ == "__main__":
    unittest.main()
