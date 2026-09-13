"""Restart and saved-byte service doors use only the new document engine."""
from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Event
import unittest
from unittest.mock import patch

from cadgen._document.checkpoint import CheckpointCodec, checkpoint_engine_version
from cadgen._document.consumers import RevisionConsumer
from cadgen._document.core import RevisionState
from cadgen._document.resources import Cancelled
from cadgen._document.service import DocumentService
from cadgen._document.sources import CapturedInput
from cadgen._document.step_import import StepImportSession
from cadgen._document.storage import Catalog
from tests.python.support.tmp_root import generated_cad_directory


SOURCE = '''from pathlib import Path
from cadgen import step, build123d as bd
@step
def model():
    calls = Path(__file__).with_suffix('.runs')
    calls.write_text((calls.read_text() if calls.exists() else '') + 'run\\n')
    return bd.Box({length}, 8, 4) - bd.Cylinder(1, 8)
'''


def volume(document, revision_id):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    def facts(native, _transform):
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(native, props)
        return props.Mass()

    with RevisionConsumer(document, revision_id) as consumer:
        return sum(consumer.query_value(occ.path, facts) for occ in consumer.occurrences())


class ServiceRecoveryTests(unittest.TestCase):
    def setUp(self):
        from cadgen._internal import op_memo

        installed = op_memo._installed
        if installed:
            op_memo.uninstall()
        self.addCleanup(op_memo.install if installed else lambda: None)
        temporary = generated_cad_directory(prefix="document-service-recovery-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.source = self.directory / "part.py"
        self.source.write_text(SOURCE.format(length=12), encoding="utf-8")
        self.target = self.source.with_suffix(".step")
        self.catalog = Catalog(self.directory / "catalog", engine_version=checkpoint_engine_version())
        self.addCleanup(self.catalog.close)
        self.codec = CheckpointCodec(self.catalog, runtime={"service-fixture": 1})

    def service(self, **kwargs):
        return DocumentService(checkpoint_codec=self.codec, **kwargs)

    def test_restart_replays_source_reuses_native_and_republishes_replaced_output(self):
        first = self.service()
        built = first.generate(self.source)
        original_volume = volume(built.document, built.revision_id)
        published = first.checkpoint(built.document)
        self.assertTrue(published.published)
        replacement = b"external bytes replacing the historical export"
        self.target.write_bytes(replacement)
        second = self.service()
        result = second.generate(self.source)
        self.assertNotEqual(built.document.owner_id, result.document.owner_id)
        self.assertEqual(["recovered"], list(second.recovery.values()))
        self.assertEqual(0, second.last_attempt.stats.computed)
        self.assertGreater(second.last_attempt.stats.reused, 0)
        self.assertEqual("run\nrun\n", self.source.with_suffix(".runs").read_text())
        # Encoded STEP products are not checkpointed yet. Re-encoding may
        # change translator IDs; the fresh receipt attests actual saved bytes.
        self.assertAlmostEqual(original_volume, volume(result.document, result.revision_id), places=6)
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).hexdigest(), result.outputs[0].sha256)
        self.assertEqual(hashlib.sha256(replacement).hexdigest(),
                         result.outputs[0].previous_sha256)
        self.assertEqual("written", result.outputs[0].action)
        self.assertEqual(RevisionState.EXPORTS_COMPLETE, result.document.state(result.revision_id))
        self.assertIs(result.document.admission, second.coordinator.admission)
        self.assertEqual((0, 0, 0), second.coordinator.admission.used)

    def test_corrupt_checkpoint_rebuilds_from_source_and_replaces_bad_head(self):
        first = self.service()
        built = first.generate(self.source)
        published = first.checkpoint(built.document)
        with self.catalog.lease(published.catalog_revision_id) as lease:
            checkpoint = self.catalog.read(lease)
        digest = hashlib.sha256(next(iter(checkpoint.payloads.values()))).hexdigest()
        (self.catalog._objects / digest).write_bytes(b"damaged derived object")
        second = self.service()
        result = second.generate(self.source)
        self.assertEqual(["discarded"], list(second.recovery.values()))
        self.assertGreater(second.last_attempt.stats.computed, 0)
        self.assertTrue(second.checkpoint(result.document).published)
        third = self.service()
        third.generate(self.source)
        self.assertEqual(["recovered"], list(third.recovery.values()))

    def test_idle_checkpoint_conflict_never_adopts_another_owners_expectation(self):
        first, second = self.service(), self.service()
        one = first.generate(self.source)
        two = second.generate(self.source)
        accepted = first.checkpoint(one.document)
        rejected = second.checkpoint(two.document)
        self.assertFalse(rejected.published)
        self.assertFalse(second.checkpoint(two.document).published)
        self.assertEqual(accepted.catalog_revision_id, self.catalog.head(one.document.document_id))
        with one.document.begin("active"):
            with self.assertRaisesRegex(RuntimeError, "idle"):
                first.checkpoint(one.document)
        self.source.write_text(SOURCE.format(length=13), encoding="utf-8")
        newer = first.generate(self.source)
        with self.assertRaisesRegex(ValueError, "current usable head"):
            first.checkpoint(newer.document, one.revision_id)

    def test_eviction_recovers_geometry_without_automatic_foreground_checkpoint(self):
        service = self.service(max_documents=1)
        first = service.generate(self.source)
        self.assertIsNone(self.catalog.head(first.document.document_id))
        service.checkpoint(first.document)
        other_source = self.directory / "other.py"
        other_source.write_text(SOURCE.format(length=20), encoding="utf-8")
        service.generate(other_source)
        restored = service.generate(self.source)
        self.assertNotEqual(first.document.owner_id, restored.document.owner_id)
        self.assertEqual(0, service.last_attempt.stats.computed)
        self.assertEqual(1, len(service._checkpoint_heads))
        self.assertEqual(1, len(service.recovery))

    def test_capacity_preserves_pinned_owner_and_cancelled_acquisition_keeps_lru(self):
        service = self.service(max_documents=1)
        first = service.generate(self.source)
        resident_key = next(iter(service._documents))
        other_source = self.directory / "other.py"
        other_source.write_text(SOURCE.format(length=20), encoding="utf-8")
        pin = first.document.pin(first.revision_id)
        try:
            with self.assertRaisesRegex(RuntimeError, "active or pinned"):
                service.generate(other_source)
            self.assertEqual([resident_key], list(service._documents))
            self.assertIs(first.document, service._documents[resident_key])
        finally:
            pin.release()

        cancellation = Event()
        cancellation.set()
        with self.assertRaises(Cancelled):
            service.generate_captured(CapturedInput.read(other_source),
                                      cancellation=cancellation)
        self.assertEqual([resident_key], list(service._documents))
        with self.assertRaises(Cancelled):
            service._document_for((str(other_source.resolve()), "model"), "cancelled",
                                  cancellation=cancellation)
        self.assertEqual([resident_key], list(service._documents))
        self.assertIs(first.document, service._documents[resident_key])

        second = service.generate(other_source)
        self.assertIsNot(first.document, second.document)
        self.assertEqual(1, len(service._documents))

    def test_generate_captured_uses_exact_buffer_after_source_replacement(self):
        captured = CapturedInput.read(self.source)
        self.source.write_text(SOURCE.format(length=20), encoding="utf-8")
        service = self.service()
        old = service.generate_captured(captured)
        current = service.generate(self.source)
        self.assertLess(volume(old.document, old.revision_id),
                        volume(current.document, current.revision_id))
        self.assertEqual(captured, old.inputs[0])
        self.assertNotEqual(old.inputs[0].digest, current.inputs[0].digest)

    def test_saved_step_is_distinct_and_recovers_without_source_or_native_parse(self):
        service = self.service()
        built = service.generate(self.source)
        captured = CapturedInput.read(self.target)
        opened = service.load_step(captured, work_directory=self.directory)
        self.assertFalse(opened.reused)
        self.assertNotEqual(built.document.owner_id, opened.document.owner_id)
        self.assertAlmostEqual(volume(built.document, built.revision_id),
                               volume(opened.document, opened.revision_id), places=6)
        service.checkpoint(opened.document)
        self.source.unlink()
        self.target.write_bytes(b"file replaced after capture")
        recovered = self.service()
        with patch.object(StepImportSession, "_parse_capture", side_effect=AssertionError("native parse")):
            result = recovered.load_step(captured, work_directory=self.directory)
        self.assertTrue(result.reused)
        self.assertEqual(captured.digest, result.input_sha256)
        self.assertAlmostEqual(volume(opened.document, opened.revision_id),
                               volume(result.document, result.revision_id), places=6)
        self.assertEqual(["recovered"], list(recovered.recovery.values()))
        self.assertEqual(RevisionState.GEOMETRY_READY, result.document.state(result.revision_id))
        self.assertIsNone(recovered.last_attempt)

    def test_same_saved_bytes_share_an_owner_but_replaced_bytes_do_not(self):
        service = self.service()
        service.generate(self.source)
        first = service.load_step(CapturedInput.read(self.target), work_directory=self.directory)
        alias = self.directory / "another.stp"
        alias.write_bytes(self.target.read_bytes())
        repeated = service.load_step(CapturedInput.read(alias), work_directory=self.directory)
        self.assertIs(first.document, repeated.document)
        self.assertEqual(first.revision_id, repeated.revision_id)
        self.assertEqual(str(alias), repeated.input_path)
        self.source.write_text(SOURCE.format(length=15), encoding="utf-8")
        service.generate(self.source)
        changed = service.load_step(CapturedInput.read(self.target), work_directory=self.directory)
        self.assertIsNot(first.document, changed.document)
        self.assertNotEqual(first.input_sha256, changed.input_sha256)
        self.assertGreater(volume(changed.document, changed.revision_id),
                           volume(first.document, first.revision_id))

    def test_retained_step_import_observes_cancellation_before_commit(self):
        from cadgen._document import step_import

        service = self.service()
        service.generate(self.source)
        captured = CapturedInput.read(self.target)
        opened = service.load_step(captured, work_directory=self.directory)
        cancellation = Event()
        importer = StepImportSession(
            opened.document, work_directory=self.directory, cancellation=cancellation)
        original_root = step_import._root_from

        def cancel_before_binding(record):
            cancellation.set()
            return original_root(record)

        with patch.object(step_import, "_root_from", side_effect=cancel_before_binding):
            with self.assertRaises(Cancelled):
                importer.load(captured)
        self.assertEqual(opened.revision_id, opened.document.head.revision_id)
        self.assertEqual((importer.metrics.retained_hits, importer.metrics.cancelled),
                         (0, 1))

    def test_cancellation_and_runtime_mutation_cannot_install_or_publish(self):
        service = self.service()
        built = service.generate(self.source)
        cancellation = Event()
        cancellation.set()
        with self.assertRaises(Cancelled):
            service.checkpoint(built.document, cancellation=cancellation)
        self.assertIsNone(self.catalog.head(built.document.document_id))
        with self.assertRaises(Cancelled):
            service.load_step(CapturedInput.read(self.target), work_directory=self.directory,
                              cancellation=cancellation)
        self.assertEqual(1, len(service._documents))
        self.codec.runtime["service-fixture"] = 2
        with self.assertRaisesRegex(ValueError, "runtime changed"):
            service.generate(self.source)
        self.assertEqual((0, 0, 0), service.coordinator.admission.used)
        self.assertFalse(service._active)


if __name__ == "__main__":
    unittest.main()
