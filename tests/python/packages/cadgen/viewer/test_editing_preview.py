"""The editing feed cannot replace saved-byte resolution or cross a served root."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from cadgen.store.trees import put_tree
from cadgen.viewer.backend import ForbiddenAssetError
from cadgen.viewer.preview import preview_status
from tests.python.support.tmp_root import generated_cad_directory


class EditingPreviewTests(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="preview-feed-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = str(self.root / "new.step")
        self.store = str(self.root / "store")
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": self.store})
        env.start()
        self.addCleanup(env.stop)
        self.tree = put_tree({"components": {}, "occurrences": [], "links": []})

    def job(self, revision=1, **extra):
        return {"id": f"epoch:job-{revision}", "epoch": "epoch", "sequence": revision,
                "tool": "run",
                "storeRoot": self.store, "outputs": [self.output], "state": "building",
                "subject": "/private/source.py", **extra}

    def preview(self):
        return {self.output: {"tree": self.tree, "kinematics": {"mates": []}, "sequence": 4}}

    def test_first_build_serves_complete_tree_without_a_saved_file_or_record(self):
        result = preview_status(str(self.root), self.output, jobs=[self.job(previews=self.preview())])
        self.assertFalse(Path(self.output).exists())
        self.assertEqual(result["preview"]["tree"], self.tree)
        self.assertEqual(result["file"], "new.step")
        self.assertEqual(result["preview"]["url"], f"/__cad/store?file={self.tree}")
        self.assertNotIn("subject", result)
        self.assertNotIn("storeRoot", result)
        self.assertNotIn("saved", result)

    def test_newest_request_wins_even_when_old_one_finishes_later(self):
        jobs = [self.job(1, state="done", updatedAt=1000, previews=self.preview()),
                self.job(2, updatedAt=999)]
        result = preview_status(str(self.root), self.output, jobs=jobs)
        self.assertEqual(result["revision"], 2)
        self.assertNotIn("preview", result)

    def test_compiling_saved_bytes_cannot_supersede_an_editing_request(self):
        jobs = [self.job(1, previews=self.preview()),
                self.job(2, tool="step-compile", state="done")]
        result = preview_status(str(self.root), self.output, jobs=jobs)
        self.assertEqual(result["revision"], 1)
        self.assertEqual(result["preview"]["tree"], self.tree)
        self.assertNotIn("saved", result)

    def test_coalesced_subscriber_does_not_advance_edit_ordering(self):
        from cadgen.daemon.jobs import JobLedger

        ledger = JobLedger()
        producer = ledger.start(tool="run", subject="model.py", store_root=self.store)
        producer.update(outputs=[self.output], previews=self.preview(), state="building")
        follower = ledger.start(tool="run", subject="model.py", store_root=self.store, editing_producer=False)
        follower.update(outputs=[self.output])
        result = preview_status(str(self.root), self.output, jobs=ledger.snapshot())
        self.assertEqual(result["request"], producer["id"])
        ledger.accept_editing_producer(follower)
        result = preview_status(str(self.root), self.output, jobs=ledger.snapshot())
        self.assertEqual(result["request"], follower["id"])

    def test_other_store_and_output_are_not_visible(self):
        result = preview_status(str(self.root), self.output, jobs=[
            self.job(previews=self.preview(), storeRoot=str(self.root / "other")),
            self.job(outputs=[str(self.root / "other.step")]),
        ])
        self.assertEqual(result["state"], "disconnected")

    def test_missing_component_does_not_publish_an_incomplete_preview(self):
        missing = put_tree({"components": {"c": {"surf": "a" * 64, "brep": "b" * 64}}})
        result = preview_status(str(self.root), self.output, jobs=[self.job(
            previews={self.output: {"tree": missing}})])
        self.assertNotIn("preview", result)
        self.assertIn("no longer available", result["error"])
        self.assertTrue(result["previewUnavailable"])

    def test_expired_preview_preserves_a_separately_validated_saved_result(self):
        from cadgen.catalog import artifact_file_hash
        from cadgen.store.records import note_document_tree

        Path(self.output).write_bytes(b"saved document")
        digest = artifact_file_hash(Path(self.output))
        note_document_tree(digest, self.tree)
        missing = put_tree({"components": {"c": {"surf": "a" * 64, "brep": "b" * 64}}})
        job = self.job(state="done", previews={self.output: {"tree": missing}},
                       savedResults={self.output: {"tree": self.tree, "documentHash": digest}})
        with mock.patch("cadgen.store.records.read_record", side_effect=AssertionError("model read")), \
             mock.patch("cadgen.store.records.model_for_output", side_effect=AssertionError("output read")):
            result = preview_status(str(self.root), self.output, jobs=[job])
        self.assertNotIn("preview", result)
        self.assertTrue(result["previewUnavailable"])
        self.assertEqual(result["saved"]["documentHash"], digest)
        self.assertEqual(result["saved"]["tree"], self.tree)

    def test_outside_root_and_hidden_paths_are_rejected(self):
        with self.assertRaises(ForbiddenAssetError):
            preview_status(str(self.root), str(self.root.parent / "outside.step"), jobs=[])
        with self.assertRaises(ValueError):
            preview_status(str(self.root), ".hidden/new.step", jobs=[])

    def test_completed_event_cannot_label_different_disk_bytes_as_saved(self):
        Path(self.output).write_text("different saved bytes", encoding="utf-8")
        result = preview_status(str(self.root), self.output, jobs=[self.job(savedResults={
            self.output: {"tree": self.tree, "documentHash": "f" * 64}})])
        self.assertNotIn("saved", result)
        self.assertIn("changed", result["error"])

    def test_noop_completion_resolves_current_saved_bytes_without_a_record(self):
        from cadgen.catalog import artifact_file_hash
        from cadgen.store.records import note_document_tree

        Path(self.output).write_bytes(b"saved document")
        digest = artifact_file_hash(Path(self.output))
        note_document_tree(digest, self.tree)
        result = preview_status(str(self.root), self.output, jobs=[self.job(state="done")])
        self.assertEqual(result["saved"]["documentHash"], digest)
        self.assertEqual(result["saved"]["tree"], self.tree)
