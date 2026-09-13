"""Saved STEP IPC captures the sole companion before entering an owner queue."""
import hashlib
import json
from pathlib import Path
import unittest

from cadgen._document.annotations import companion_path
from cadgen._document.sources import CapturedInput
from cadgen._document.worker import DocumentWorker, _Owner
from tests.python.support.tmp_root import generated_cad_directory


class AnnotationProtocolTests(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="document-annotation-wire-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()

    def test_client_captures_companion_before_request_and_can_attest_absence(self):
        payload = b"captured STEP"
        step = CapturedInput(self.directory / "part.step", payload, hashlib.sha256(payload).hexdigest())
        path = companion_path(step.path)
        path.write_bytes(b"captured annotations")
        worker = object.__new__(DocumentWorker)
        def request(operation, **values):
            path.write_bytes(b"replacement during dispatch")
            return operation, values
        worker.request = request
        operation, values = worker.open_step(step)
        self.assertEqual("open_step", operation)
        self.assertEqual((step.data, b"captured annotations"), values["payloads"])
        self.assertEqual(hashlib.sha256(b"captured annotations").hexdigest(), values["annotations"]["digest"])
        _, values = worker.open_step(step, annotations=None)
        self.assertIsNone(values["annotations"])
        self.assertEqual((step.data,), values["payloads"])

    def test_worker_rejects_old_schema_and_mismatched_companion_framing(self):
        request = {"id": 1, "operation": "open_step", "cwd": str(self.directory),
                   "environment": {}, "path": str(self.directory / "part.step"), "digest": "a" * 64,
                   "annotations": None}
        self.assertEqual("open_step", _Owner._validate_request(request, (b"step",)))
        old = {key: value for key, value in request.items() if key != "annotations"}
        with self.assertRaisesRegex(ValueError, "fields"):
            _Owner._validate_request(old, (b"step",))
        for metadata, payloads in ((None, (b"step", b"extra")),
                                   ({"digest": "b" * 64, "bytes": 5}, (b"step", b"bad")),
                                   ({"digest": "b" * 64, "bytes": True}, (b"step", b"x")),
                                   ({"digest": "b" * 64, "bytes": 1, "path": "other.json"}, (b"step", b"x"))):
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                _Owner._validate_request({**request, "annotations": metadata}, payloads)


class AnnotationWorkerNativeTests(unittest.TestCase):
    def test_captured_annotated_saved_document_survives_worker_checkpoint_restart(self):
        temporary = generated_cad_directory(prefix="document-annotation-worker-")
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name).resolve()
        source_path = directory / "part.py"
        source_path.write_text("from cadgen import step, build123d as bd\n@step\ndef part():\n"
                              "    shape = bd.Box(2, 3, 4)\n"
                              "    shape.cad_material = {'roughness': .2, 'opacity': .6}\n"
                              "    shape.material = 'steel'\n    return shape\n")
        catalog = directory / "catalog"
        def result(call):
            response, buffers = call
            return response["result"], buffers
        with DocumentWorker(catalog, startup_timeout=60) as worker:
            built, _ = result(worker.generate(CapturedInput.read(source_path), timeout=60))
            self.assertEqual(2, len(built["outputs"]))
            step = CapturedInput.read(source_path.with_suffix(".step"))
            annotation = CapturedInput.read(companion_path(step.path))
            annotation.path.write_bytes(b"replaced after capture")
            opened, _ = result(worker.open_step(step, annotations=annotation, timeout=60))
            self.assertNotEqual(built["revision"]["owner"], opened["revision"]["owner"])
            _, buffers = result(worker.display(opened["revision"], timeout=60))
            self.assertEqual({"roughness": .2, "opacity": .6},
                             json.loads(buffers[0])["occurrences"][0]["appearance"]["pbr"])
            saved, _ = result(worker.checkpoint(opened["revision"], timeout=60))
            self.assertTrue(saved["published"])
        source_path.unlink()
        with DocumentWorker(catalog, startup_timeout=60) as worker:
            reopened, _ = result(worker.open_step(step, annotations=annotation, timeout=60))
            self.assertTrue(reopened["reused"])
            _, buffers = result(worker.display(reopened["revision"], timeout=60))
            self.assertEqual("steel", json.loads(buffers[0])["occurrences"][0]["appearance"]["material"])
            saved, _ = result(worker.checkpoint(reopened["revision"], timeout=60))
            self.assertTrue(saved["published"])
