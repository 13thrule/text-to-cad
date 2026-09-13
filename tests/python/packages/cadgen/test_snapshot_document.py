"""Native snapshot bytes, capabilities and lifetime receipts, without a CAD kernel."""
import asyncio
from array import array
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import subprocess
import struct
import sys
import time
from types import MappingProxyType
import unittest
import zlib
from unittest.mock import AsyncMock, patch

from cadgen._document.display import DisplayProduct, MeshAsset
from cadgen._document.meshing import _pack
from cadgen.snapshot_core import SnapshotError
from cadgen.snapshot_document import prepare_display_snapshot, prepare_saved_step_snapshot
from cadgen.snapshot_document_input import asset_inventory, native_job_descriptor, read_asset
from cadgen.results import SnapshotFile, SnapshotResult
from cadgen.store.paths import _bind_store_root
from tests.python.support.tmp_root import generated_cad_directory


def attest(product):
    # Explicit trusted fixture registration. Production products are registered
    # only by the native display producer; constructing the dataclass is not proof.
    from cadgen._document.display import _products
    _products[id(product)] = product
    return product


def fixture(*, edges=True, chord=.0015):
    policy = {"relative_chord": chord, "angular": .35, "edges": edges}
    header = {"version": 2, "discardedZeroAreaTriangles": 0, "options": policy,
              "linearDeflection": .01, "origin": [0, 0, 0], "bounds": {"min": [0, 0, 0], "max": [1, 1, 0]},
              "faces": [[0, 0, 3, 0, 3]], "edges": [[0, 0, 2, "boundary"]] if edges else []}
    data = _pack(header, {"positions": array("f", [0, 0, 0, 1, 0, 0, 0, 1, 0]),
        "normals": array("f", [0, 0, 1] * 3), "indices": array("I", [0, 1, 2]),
        "edgePositions": array("f", [0, 0, 0, 1, 0, 0] if edges else [])})
    digest = hashlib.sha256(data).hexdigest()
    transform = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    node = {"path": ["root"], "label": "Part", "transform": transform, "appearance": {"color": [.2, .4, .6, 1]}}
    manifest = json.dumps({"version": 1, "owner": "test-owner", "revision": 1,
        "nodes": [{**node, "kind": "part"}], "prototypes": {"prototype": {"mesh": digest, "bytes": len(data)}},
        "occurrences": [{**node, "prototype": "prototype"}]}).encode()
    asset = MeshAsset(digest, data, (0, 0, 0), (0, 0, 0), (1, 1, 0), 1, 1, int(edges))
    return attest(DisplayProduct("test-owner", 1, manifest, MappingProxyType({digest: asset}),
                                 MappingProxyType({"prototype": digest})))


def job():
    return {"outputs": [{"path": "/tmp/native-test-image.png", "width": 64, "height": 48}]}


def png(width, height):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(payload, zlib.crc32(kind)))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + b"\x20\x40\x80\xff" * width) * height)) + chunk(b"IEND", b""))


class StagingTests:
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="native-snapshot-test-")
        self.addCleanup(self._temp.cleanup)
        self.enterContext(_bind_store_root(Path(self._temp.name)))


class PreparationTests(StagingTests, unittest.TestCase):
    def test_preparation_failure_preserves_original_when_staging_cleanup_fails(self):
        from cadgen import snapshot_document as module
        from cadgen.snapshot_staging import StagingSlot
        previous = set(module._owners)
        product = fixture()
        try:
            with patch("cadgen._document.meshing.unpack_mesh", side_effect=KeyboardInterrupt("original preparation")), \
                 patch.object(StagingSlot, "release", side_effect=OSError("slot cleanup failed")):
                with self.assertRaisesRegex(KeyboardInterrupt, "original preparation") as caught:
                    prepare_display_snapshot(product, job())
            retained = set(module._owners) - previous
            self.assertEqual(1, len(retained))
            self.assertTrue(next(iter(retained))._slot.path.exists())
            self.assertIn("slot cleanup failed", caught.exception.__notes__[0])
        finally:
            for prepared in set(module._owners) - previous: prepared.close()

    def test_saved_release_failure_still_releases_lease_after_staging_cleanup_error(self):
        product = fixture()
        calls = []
        class Ticket:
            def __init__(self, value): self.value = value
            def result(self):
                if isinstance(self.value, BaseException): raise self.value
                return self.value
            def cancel(self): pass
        class Dispatcher:
            def submit(self, operation, **kwargs):
                calls.append(operation)
                if operation == "open_step": return Ticket(({"result": {"revision": {"lease": "l"}}}, ()))
                if operation == "display":
                    asset = next(iter(product.assets.values()))
                    return Ticket(({"result": {"assets": [{"identity": asset.identity, "bytes": len(asset.payload)}]}},
                                   (product.manifest, asset.payload)))
                return Ticket(KeyboardInterrupt("original release") if calls.count("release") == 1 else ({"result": {"released": True}}, ()))
        class Prepared:
            def close(self): raise OSError("staging cleanup failed")
        with generated_cad_directory(prefix="native-saved-release-failed-") as directory:
            path = Path(directory) / "saved.step"
            path.write_bytes(b"captured saved bytes")
            with patch("cadgen.snapshot_document.PreparedDocumentSnapshot", return_value=Prepared()):
                with self.assertRaisesRegex(KeyboardInterrupt, "original release") as caught:
                    prepare_saved_step_snapshot(path, job(), dispatcher=Dispatcher())
            self.assertEqual(["open_step", "display", "release", "release"], calls)
            self.assertIn("staging cleanup failed", caught.exception.__notes__[0])

    def test_constructed_product_is_not_a_resident_display_attestation(self):
        product = fixture()
        with self.assertRaisesRegex(TypeError, "attested DisplayProduct"):
            prepare_display_snapshot(replace(product), job())

    def test_invalid_output_bounds_and_saved_input_collision_fail_before_clearing(self):
        with generated_cad_directory(prefix="native-output-admission-") as directory:
            path = Path(directory) / "model.step"
            path.write_bytes(b"saved input")
            for target in (path, path.with_name(path.name + ".json")):
                target.write_bytes(b"preserved")
                with self.assertRaisesRegex(SnapshotError, "cannot replace"):
                    prepare_saved_step_snapshot(path, {"outputs": [{"path": str(target)}]}, dispatcher=None)
                self.assertEqual(b"preserved", target.read_bytes())
            output = Path(directory) / "old.png"
            output.write_bytes(b"previous")
            for outputs in ([{"path": str(output), "width": 8193, "height": 1}],
                            [{"path": str(output), "width": 8192, "height": 8192}],
                            [{"path": str(output)}, {"path": str(output)}]):
                with self.assertRaises(ValueError): prepare_display_snapshot(fixture(), {"outputs": outputs})
                self.assertEqual(b"previous", output.read_bytes())

    def test_png_verification_bounds_inflate_and_rejects_incomplete_or_extra_streams(self):
        from cadgen.snapshot_document_outputs import verify_png
        value = png(512, 512)
        verify_png(value, 512, 512, time.monotonic() + 2)
        for bad in (value[:-12], value + b"trailing", value[:-1] + bytes([value[-1] ^ 1])):
            with self.assertRaises(ValueError): verify_png(bad, 512, 512, time.monotonic() + 2)
        with self.assertRaises(TimeoutError): verify_png(value, 512, 512, time.monotonic() - 1)

    def test_valid_request_clears_previous_image_before_saved_import_can_fail(self):
        with generated_cad_directory(prefix="native-saved-failed-") as directory:
            path = Path(directory)
            output = path / "previous.png"
            output.write_bytes(b"previous image")
            with self.assertRaises(FileNotFoundError):
                prepare_saved_step_snapshot(path / "missing.step", {"outputs": [{"path": str(output)}]}, dispatcher=None)
            self.assertFalse(output.exists())

    def test_packet_is_captured_before_caller_mutation_and_assets_are_exact(self):
        source = job()
        product = fixture()
        prepared = prepare_display_snapshot(product, source)
        self.addCleanup(prepared.close)
        source["outputs"][0]["width"] = 999
        captured = prepared.operation["packet"]["jobs"][0]
        self.assertNotEqual(source["outputs"][0]["path"], captured["outputs"][0]["path"])
        self.assertEqual(prepared._slot.path / "outputs", Path(captured["outputs"][0]["path"]).parent)
        self.assertEqual(64, captured["outputs"][0]["width"])
        descriptor = native_job_descriptor(captured)
        inventory = asset_inventory(descriptor)
        self.assertEqual(2, len(inventory))
        for identity, asset in product.assets.items():
            self.assertEqual(asset.payload, read_asset(prepared.root, inventory, identity))
            (prepared.root / identity).write_bytes(b"x" * len(asset.payload))
            with self.assertRaisesRegex(ValueError, "captured hash"):
                read_asset(prepared.root, inventory, identity)
        with self.assertRaises(FileNotFoundError):
            read_asset(prepared.root, inventory, "../outside")

    def test_rejects_membership_hash_and_policy_errors_without_retaining_staging(self):
        from cadgen import snapshot_document as module
        product = fixture()
        original_charge = module._staged_bytes
        bad_asset = replace(next(iter(product.assets.values())), payload=b"x" * len(next(iter(product.assets.values())).payload))
        broken = attest(replace(product, assets={bad_asset.identity: bad_asset}))
        for candidate, request in ((broken, job()), (attest(replace(product, assets={})), job()),
                                   (product, {**job(), "render": {"quality": "preview"}}),
                                   (product, {**job(), "selection": {}}),
                                   (product, {**job(), "kinematics": None}),
                                   (product, {**job(), "mode": "section"})):
            with self.subTest(request=request), self.assertRaises((ValueError, SnapshotError)):
                prepare_display_snapshot(candidate, request)
        self.assertEqual(original_charge, module._staged_bytes)

    def test_render_quality_rungs_and_edge_policy_are_exact(self):
        for quality, chord in (("preview", .0015), ("final", .00015)):
            prepared = prepare_display_snapshot(fixture(edges=False, chord=chord), {**job(), "render": {"quality": quality}})
            self.assertEqual(chord, prepared.operation["packet"]["jobs"][0]["resolved"]["document"]["meshing"]["relative_chord"])
            prepared.close()

    def test_saved_step_capture_supplies_exact_bytes_and_companion_absence_once(self):
        product = fixture()
        with generated_cad_directory(prefix="native-saved-capture-") as directory:
            path = Path(directory) / "saved.step"
            path.write_bytes(b"saved original")
            calls = []
            class Ticket:
                def __init__(self, value): self.value = value
                def result(self): return self.value
                def cancel(self): raise AssertionError("unnecessary cancellation")
            class Dispatcher:
                def submit(self, operation, **kwargs):
                    calls.append((operation, kwargs))
                    if operation == "open_step":
                        path.write_bytes(b"new saved bytes")
                        path.with_name(path.name + ".json").write_bytes(b"new companion")
                        return Ticket(({"result": {"revision": {"lease": "l", "owner": "o", "revision": 1, "document": "d"}}}, ()))
                    if operation == "display":
                        asset = next(iter(product.assets.values()))
                        return Ticket(({"result": {"assets": [{"identity": asset.identity, "bytes": len(asset.payload)}]}},
                                       (product.manifest, asset.payload)))
                    self.assertEqual("release", operation)
                    return Ticket(({"result": {"released": True}}, ()))
                assertEqual = self.assertEqual
            before = time.monotonic()
            prepared = prepare_saved_step_snapshot(path, job(), dispatcher=Dispatcher(), timeout=20)
            self.addCleanup(prepared.close)
            self.assertEqual(["open_step", "display", "release"], [row[0] for row in calls])
            self.assertEqual((b"saved original",), calls[0][1]["payloads"])
            self.assertIsNone(calls[0][1]["annotations"])
            self.assertLessEqual(calls[1][1]["timeout"], calls[0][1]["timeout"])
            self.assertEqual(calls[0][1]["context"], calls[1][1]["context"])
            self.assertLessEqual(prepared.operation["deadline"], before + 50.1)
            self.assertEqual(hashlib.sha256(b"saved original").hexdigest(),
                             prepared.operation["packet"]["jobs"][0]["resolved"]["inputHash"])
            prepared.close()
            calls.clear()
            path.write_bytes(b"next captured saved")
            path.with_name(path.name + ".json").write_bytes(b"captured annotations")
            annotated = prepare_saved_step_snapshot(path, job(), dispatcher=Dispatcher())
            self.addCleanup(annotated.close)
            self.assertEqual((b"next captured saved", b"captured annotations"), calls[0][1]["payloads"])
            self.assertEqual({"digest": hashlib.sha256(b"captured annotations").hexdigest(), "bytes": len(b"captured annotations")},
                             calls[0][1]["annotations"])

    def test_runtime_and_cache_roots_are_bound_before_product_preparation(self):
        from cadgen import snapshot_document as module
        cache = (Path(self._temp.name) / "captured").resolve()
        later = (Path(self._temp.name) / "later").resolve()
        current = [cache]
        original = module._manifest
        def capture(data):
            current[0] = later
            return original(data)
        with patch("cadgen.store.paths.store_root", side_effect=lambda: current[0]), \
             patch.object(module, "_manifest", capture):
            prepared = prepare_display_snapshot(fixture(), job())
        self.addCleanup(prepared.close)
        self.assertEqual(str(cache), prepared.operation["storeRoot"])
        self.assertTrue(prepared.root.is_relative_to(cache))
        self.assertFalse(later.exists())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO")
    def test_fifo_asset_step_and_companion_are_rejected_without_waiting_for_writer(self):
        prepared = prepare_display_snapshot(fixture(), job())
        self.addCleanup(prepared.close)
        descriptor = prepared.operation["packet"]["jobs"][0]["resolved"]["document"]
        identity = next(iter(descriptor["assets"]))
        asset = prepared.root / identity
        asset.unlink(); os.mkfifo(asset)
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, "size/type"):
            read_asset(prepared.root, asset_inventory(descriptor), identity)
        with self.assertRaisesRegex(ValueError, "size/type"):
            from cadgen.snapshot_document_input import read_regular
            read_regular(asset, 1024)
        from cadgen.snapshot_staging import write_staged
        with self.assertRaises(FileExistsError):
            write_staged(asset, b"must not wait for FIFO reader")
        with generated_cad_directory(prefix="native-saved-fifo-") as directory:
            path = Path(directory) / "fifo.step"
            os.mkfifo(path)
            with self.assertRaisesRegex(ValueError, "size/type"):
                prepare_saved_step_snapshot(path, job(), dispatcher=None)
            path.unlink(); path.write_bytes(b"captured saved bytes")
            os.mkfifo(path.with_name(path.name + ".json"))
            with self.assertRaisesRegex(ValueError, "size/type"):
                prepare_saved_step_snapshot(path, job(), dispatcher=None)
        self.assertLess(time.monotonic() - started, .2)

    def test_persistent_slots_remain_charged_after_independent_callers_exit(self):
        from cadgen.snapshot_staging import MAX_SLOTS
        code = "from cadgen.snapshot_staging import StagingSlot; import sys; StagingSlot(sys.argv[1], 16)"
        for index in range(MAX_SLOTS):
            result = subprocess.run([sys.executable, "-c", code, self._temp.name], capture_output=True, timeout=5)
            self.assertEqual(0, result.returncode, result.stderr.decode())
        denied = subprocess.run([sys.executable, "-c", code, self._temp.name], capture_output=True, timeout=5)
        self.assertNotEqual(0, denied.returncode)
        self.assertIn(b"persistent staging capacity is full", denied.stderr)
        self.assertEqual(MAX_SLOTS, len(list((Path(self._temp.name) / "runtime/native-snapshot-staging").iterdir())))

    def test_persistent_slot_refuses_unacknowledged_or_changed_ownership_release(self):
        from cadgen.snapshot_staging import StagingSlot
        from cadgen.snapshot_operation import RenderCleanup
        slot = StagingSlot(self._temp.name, 12)
        with self.assertRaisesRegex(RuntimeError, "acknowledged"):
            slot.release(RenderCleanup())
        (slot.path / "owner.json").write_bytes(b"another owner")
        with self.assertRaises((RuntimeError, ValueError)):
            slot.release(RenderCleanup(True))
        if hasattr(os, "mkfifo"):
            (slot.path / "owner.json").unlink()
            os.mkfifo(slot.path / "owner.json")
            with self.assertRaisesRegex(ValueError, "size/type"):
                slot.release(RenderCleanup(True))
            (slot.path / "owner.json").unlink()
        (slot.path / "owner.json").write_bytes(slot.receipt)
        slot.release(RenderCleanup(True))
        self.assertFalse(slot.path.exists())


class LifetimeTests(StagingTests, unittest.IsolatedAsyncioTestCase):
    async def test_multiple_cameras_publish_verified_pngs_and_remap_results_after_ack(self):
        with generated_cad_directory(prefix="native-multi-output-") as directory:
            targets = [Path(directory) / "first.png", Path(directory) / "second.png"]
            request = {"outputs": [{"path": str(target), "width": 7 + i, "height": 5 + i} for i, target in enumerate(targets)]}
            prepared = prepare_display_snapshot(fixture(), request)
            class Service:
                async def render_operation(self, operation, **kwargs):
                    outputs = operation["packet"]["jobs"][0]["outputs"]
                    assert all(Path(row["path"]) not in targets for row in outputs)
                    assert not any(target.exists() for target in targets)
                    for row in outputs:
                        Path(row["path"]).write_bytes(png(row["width"], row["height"]))
                    kwargs["cleanup"].acknowledged = True
                    return SnapshotResult(True, files=tuple(SnapshotFile(Path(row["path"]), "png", view="iso") for row in outputs),
                        debug=({"stageTimings": {"outputs": [{"path": row["path"], "encodeImageMs": 1} for row in outputs]}},))
            result = await prepared.render(service=Service())
            self.assertEqual(targets, [row.path for row in result.files])
            self.assertEqual([str(target) for target in targets], [row["path"] for row in result.debug[0]["stageTimings"]["outputs"]])
            for i, target in enumerate(targets): self.assertEqual(png(7 + i, 5 + i), target.read_bytes())
            self.assertFalse(prepared._slot.path.exists())

    async def test_unknown_cleanup_can_only_write_late_private_outputs(self):
        with generated_cad_directory(prefix="native-late-output-") as directory:
            target = Path(directory) / "frame.png"
            prepared = prepare_display_snapshot(fixture(), {"outputs": [{"path": str(target), "width": 7, "height": 5}]})
            release = asyncio.Event()
            tasks = []
            class Service:
                async def render_operation(self, operation, **kwargs):
                    output = operation["packet"]["jobs"][0]["outputs"][0]
                    async def late():
                        await release.wait()
                        Path(output["path"]).write_bytes(png(7, 5))
                    tasks.append(asyncio.create_task(late()))
                    kwargs["cleanup"].acknowledged = False
                    raise asyncio.CancelledError("worker cleanup unknown")
            try:
                with self.assertRaises(asyncio.CancelledError): await prepared.render(service=Service())
                release.set(); await tasks[0]
                self.assertFalse(target.exists())
                self.assertTrue(prepared._private_paths[0].exists())
                self.assertTrue(prepared._slot.path.exists())
            finally:
                prepared.cleanup.acknowledged = True
                prepared.close()

    async def test_wrong_dimensions_or_incomplete_output_set_never_publish_any_camera(self):
        with generated_cad_directory(prefix="native-invalid-output-") as directory:
            targets = [Path(directory) / "one.png", Path(directory) / "two.png"]
            for mode in ("dimensions", "membership", "crc"):
                prepared = prepare_display_snapshot(fixture(), {"outputs": [{"path": str(target), "width": 7, "height": 5} for target in targets]})
                class Service:
                    async def render_operation(self, operation, **kwargs):
                        outputs = operation["packet"]["jobs"][0]["outputs"]
                        for i, row in enumerate(outputs):
                            data = png(8 if mode == "dimensions" and i == 1 else 7, 5)
                            if mode == "crc" and i == 1: data = data[:-1] + bytes([data[-1] ^ 1])
                            Path(row["path"]).write_bytes(data)
                        kwargs["cleanup"].acknowledged = True
                        return SnapshotResult(True, files=tuple(SnapshotFile(Path(row["path"]), "png")
                            for row in (outputs[:1] if mode == "membership" else outputs)))
                with self.assertRaises(ValueError): await prepared.render(service=Service())
                self.assertFalse(any(path.exists() for path in targets))
                self.assertFalse(prepared._slot.path.exists())

    async def test_service_construction_failure_releases_unconsumed_slot_and_original_error(self):
        from cadgen import snapshot_document as module
        prepared = prepare_display_snapshot(fixture(), job())
        with patch("cadgen.snapshot_service.SnapshotService", side_effect=RuntimeError("service constructor failed")):
            with self.assertRaisesRegex(RuntimeError, "service constructor failed"):
                await prepared.render()
        self.assertTrue(prepared.cleanup.acknowledged)
        self.assertFalse(prepared.root.exists())
        self.assertNotIn(prepared, module._owners)

    async def test_expiry_and_cancellation_before_dispatch_release_unconsumed_slots(self):
        from cadgen.snapshot_operation import CLEANUP_SECONDS
        prepared = prepare_display_snapshot(fixture(), job())
        prepared.operation["deadline"] = time.monotonic() + CLEANUP_SECONDS - .01
        with patch("cadgen.snapshot_service.SnapshotService", side_effect=AssertionError("expired packet constructed service")):
            with self.assertRaisesRegex(TimeoutError, "original deadline"):
                await prepared.render()
        self.assertFalse(prepared.root.exists())
        pending = prepare_display_snapshot(fixture(), job())
        class Service:
            async def render_operation(self, *args, **kwargs):
                raise asyncio.CancelledError("cancelled before admission")
        with self.assertRaisesRegex(asyncio.CancelledError, "before admission"):
            await pending.render(service=Service())
        self.assertTrue(pending.cleanup.acknowledged)
        self.assertFalse(pending.root.exists())

    async def test_failed_render_with_cleanup_ack_retires_files_and_preserves_exception(self):
        prepared = prepare_display_snapshot(fixture(), job())
        class Service:
            async def render_operation(self, operation, **kwargs):
                kwargs["cleanup"].acknowledged = False
                self.assert_exists = prepared.root.is_dir()
                kwargs["cleanup"].acknowledged = True
                raise asyncio.CancelledError("original cancellation")
        service = Service()
        with self.assertRaisesRegex(asyncio.CancelledError, "original cancellation"):
            await prepared.render(service=service)
        self.assertTrue(service.assert_exists)
        self.assertFalse(prepared.root.exists())

    async def test_failure_before_publication_preserves_another_producers_output(self):
        with generated_cad_directory(prefix="native-failed-output-") as directory:
            output = Path(directory) / "frame.png"
            prepared = prepare_display_snapshot(fixture(), {"outputs": [{"path": str(output)}]})
            class Service:
                async def render_operation(self, operation, **kwargs):
                    # This simulates an unrelated producer. Only private paths
                    # are included in the renderer's actual operation.
                    output.write_bytes(b"independent producer")
                    kwargs["cleanup"].acknowledged = True
                    raise SnapshotError("late transport error")
            with self.assertRaisesRegex(SnapshotError, "late transport error"):
                await prepared.render(service=Service())
            self.assertEqual(b"independent producer", output.read_bytes())
            self.assertFalse(prepared.root.exists())

    async def test_publication_readback_and_rollback_preserve_replaced_outputs(self):
        from cadgen import snapshot_document_outputs as outputs_module
        original_write = outputs_module.write_bytes_atomic
        with generated_cad_directory(prefix="native-publication-receipt-") as directory:
            targets = [Path(directory) / "one.png", Path(directory) / "two.png"]
            class Service:
                async def render_operation(self, operation, **kwargs):
                    rows = operation["packet"]["jobs"][0]["outputs"]
                    for row in rows: Path(row["path"]).write_bytes(png(7, 5))
                    kwargs["cleanup"].acknowledged = True
                    return SnapshotResult(True, files=tuple(SnapshotFile(Path(row["path"]), "png") for row in rows))
            for mode in ("second_write_failure", "replacement_then_failure", "replacement_then_readback"):
                with self.subTest(mode=mode):
                    prepared = prepare_display_snapshot(fixture(), {"outputs": [
                        {"path": str(target), "width": 7, "height": 5} for target in targets]})
                    def write(path, data):
                        if path == targets[1]:
                            if mode.startswith("replacement"):
                                targets[0].write_bytes(b"independent producer")
                            if mode.endswith("failure"):
                                raise OSError("second camera publication failed")
                        original_write(path, data)
                    with patch.object(outputs_module, "write_bytes_atomic", write):
                        with self.assertRaises((OSError, ValueError)):
                            await prepared.render(service=Service())
                    if mode.startswith("replacement"):
                        self.assertEqual(b"independent producer", targets[0].read_bytes())
                    else:
                        self.assertFalse(targets[0].exists())
                    self.assertFalse(targets[1].exists())
                    self.assertFalse(prepared._slot.path.exists())

    async def test_retirement_failure_rolls_back_only_still_matching_publication(self):
        with generated_cad_directory(prefix="native-retirement-receipt-") as directory:
            targets = [Path(directory) / "one.png", Path(directory) / "two.png"]
            prepared = prepare_display_snapshot(fixture(), {"outputs": [
                {"path": str(target), "width": 7, "height": 5} for target in targets]})
            self.addCleanup(prepared.close)
            class Service:
                async def render_operation(self, operation, **kwargs):
                    rows = operation["packet"]["jobs"][0]["outputs"]
                    for row in rows: Path(row["path"]).write_bytes(png(7, 5))
                    kwargs["cleanup"].acknowledged = True
                    return SnapshotResult(True, files=tuple(SnapshotFile(Path(row["path"]), "png") for row in rows))
            def fail_retirement():
                targets[0].write_bytes(b"independent producer")
                raise OSError("staging retirement failed")
            with patch.object(prepared, "close", side_effect=fail_retirement):
                with self.assertRaisesRegex(OSError, "staging retirement failed"):
                    await prepared.render(service=Service())
            self.assertEqual(b"independent producer", targets[0].read_bytes())
            self.assertFalse(targets[1].exists())
            self.assertTrue(prepared._slot.path.exists())

    async def test_uncertain_consumer_retains_charged_files_and_caps_repeated_admission(self):
        from cadgen import snapshot_document as module
        prepared = prepare_display_snapshot(fixture(), job())
        class Service:
            async def render_operation(self, operation, **kwargs):
                kwargs["cleanup"].acknowledged = False
                raise asyncio.CancelledError("transport ended without worker receipt")
        try:
            with self.assertRaises(asyncio.CancelledError):
                await prepared.render(service=Service())
            self.assertTrue(prepared.root.is_dir())
            with self.assertRaisesRegex(SnapshotError, "cleanup is acknowledged"):
                prepared.close()
            with patch.object(module, "MAX_PREPARED_SNAPSHOTS", len(module._owners)):
                with self.assertRaisesRegex(SnapshotError, "staging capacity"):
                    prepare_display_snapshot(fixture(), job())
        finally:
            # This fake consumer owns no browser. Its explicit acknowledgement is
            # the test's reclamation receipt, never inferred by production code.
            prepared.cleanup.acknowledged = True
            prepared.close()

    async def test_local_shutdown_failure_does_not_replace_cancellation(self):
        prepared = prepare_display_snapshot(fixture(), job())
        class Service:
            fail_close = True
            async def render_operation(self, operation, **kwargs):
                kwargs["cleanup"].acknowledged = False
                raise asyncio.CancelledError("cancel")
            def close(self):
                if self.fail_close: raise RuntimeError("shutdown not proven")
        try:
            with patch("cadgen.snapshot_service.SnapshotService", Service):
                with self.assertRaises(asyncio.CancelledError) as error:
                    await prepared.render()
            self.assertIn("shutdown not proven", error.exception.__notes__[0])
            self.assertTrue(prepared.root.exists())
        finally:
            prepared._owned_service.fail_close = False
            prepared.close()


if __name__ == "__main__":
    unittest.main()
