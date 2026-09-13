"""Native static formats: independent readers and publication failure evidence."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import struct
import threading
import time
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from cadgen._document import Document, ExportConflict, NativeResult, OperatorSpec, RevisionState
from cadgen._document.display import build_display
from cadgen._document.mesh_encoder import Budget, MeshEncoder, MeshEncodingError, _parse_output
from cadgen._document.mesh_product import MeshProductSession, destination_digest
from cadgen._document.meshing import MeshOptions, unpack_mesh
from cadgen._document.resources import Cancelled
from cadgen._document.roots import AssemblyGroup, GeometryLeaf, IDENTITY_TRANSFORM
from tests.python.support.tmp_root import generated_cad_directory


def move(x):
    result = list(IDENTITY_TRANSFORM)
    result[3] = x
    return tuple(result)


def multiply(a, b):
    return [sum(a[row * 4 + k] * b[k * 4 + column] for k in range(4))
            for row in range(4) for column in range(4)]


def transformed(matrix, position):
    return tuple(sum(matrix[row * 4 + column] * position[column] for column in range(3))
                 + matrix[row * 4 + 3] for row in range(3))


def glb_read(payload):
    magic, version, length, json_size, json_kind = struct.unpack_from("<5I", payload)
    assert (magic, version, length, json_kind) == (0x46546C67, 2, len(payload), 0x4E4F534A)
    header = json.loads(payload[20:20 + json_size])
    binary_size, binary_kind = struct.unpack_from("<2I", payload, 20 + json_size)
    assert binary_kind == 0x004E4942
    binary = payload[28 + json_size:28 + json_size + binary_size]
    points, references = [], []
    def visit(index, parent):
        node = header["nodes"][index]
        column = node.get("matrix", IDENTITY_TRANSFORM)
        local = [column[column_index * 4 + row] for row in range(4) for column_index in range(4)]
        world = multiply(parent, local)
        if "mesh" in node:
            references.append(node["mesh"])
            for primitive in header["meshes"][node["mesh"]]["primitives"]:
                accessor = header["accessors"][primitive["attributes"]["POSITION"]]
                assert accessor["componentType"] == 5126 and accessor["type"] == "VEC3"
                view = header["bufferViews"][accessor["bufferView"]]
                start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
                for vertex in range(accessor["count"]):
                    point = struct.unpack_from("<3f", binary, start + vertex * view.get("byteStride", 12))
                    points.append(transformed(world, point))
        for child in node.get("children", []):
            visit(child, world)
    for node in header["scenes"][header["scene"]]["nodes"]:
        visit(node, IDENTITY_TRANSFORM)
    return header, points, references


def mf_read(payload):
    core = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
    material = "{http://schemas.microsoft.com/3dmanufacturing/material/2015/02}"
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.testzip() is None
        model = ET.fromstring(archive.read("3D/3dmodel.model"))
    assert model.attrib["unit"] == "millimeter"
    resources = model.find(core + "resources")
    objects = {int(row.attrib["id"]): row for row in resources.findall(core + "object")}
    points, references = [], []
    def matrix(value):
        if value is None:
            return IDENTITY_TRANSFORM
        values = list(map(float, value.split()))
        assert len(values) == 12
        return [values[0], values[3], values[6], values[9], values[1], values[4], values[7], values[10],
                values[2], values[5], values[8], values[11], 0., 0., 0., 1.]
    def visit(identifier, world):
        obj = objects[identifier]
        mesh = obj.find(core + "mesh")
        if mesh is not None:
            references.append(identifier)
            for vertex in mesh.find(core + "vertices"):
                points.append(transformed(world, tuple(float(vertex.attrib[key]) for key in ("x", "y", "z"))))
        else:
            for child in obj.find(core + "components"):
                visit(int(child.attrib["objectid"]), multiply(world, matrix(child.attrib.get("transform"))))
    for item in model.find(core + "build"):
        visit(int(item.attrib["objectid"]), matrix(item.attrib.get("transform")))
    return model, resources, objects, points, references, core, material


class MeshProductTests(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="native-mesh-product-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.encoder = MeshEncoder()
        self.document = Document("native-mesh-exports")
        self.targets = {name: self.directory / f"part.{name}" for name in ("stl", "glb", "3mf")}

    def revision(self, *, document=None, shift=0, roughness=.23, prefix="source", formats=None):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        document = self.document if document is None else document
        formats = self.targets if formats is None else formats
        with document.begin(required_exports=tuple(str(self.targets[key]) for key in formats)) as tx:
            handle = tx.evaluate(OperatorSpec("native-export-box"), (2., 3., 4.), (),
                                 lambda *_: NativeResult(BRepPrimAPI_MakeBox(2., 3., 4.).Shape()))
            leaves = tuple(GeometryLeaf(f"{prefix}-leaf-{i}", handle, move(i * 10), f"Part {i}",
                {"face_colors": ((1, (.6, .3, .2, .4)),)} if i == 2 else {}) for i in range(3))
            group = AssemblyGroup(f"{prefix}-group", leaves, move(5), "Nested")
            root = AssemblyGroup(f"{prefix}-root", (group,), move(shift), "Assembly", {
                "color": (.1234567890123456, .3456789012345678, .6789012345678901, .7),
                "pbr": {"roughness": roughness, "metalness": .63, "clearcoat": .2, "clearcoatRoughness": .11, "opacity": .4},
                "material": "authored-alloy", "physical_material": {"name": "Alloy", "description": "Only authored facts",
                    "density": 2.7, "density_name": "g/cm3", "density_type": "mass"}})
            tx.bind_root(root, unrepresented_metadata=())
            return tx.commit().revision_id

    def session(self, rid, *, deadline=None):
        return MeshProductSession(self.document, rid, encoder=self.encoder, work_directory=self.directory,
                                  deadline=time.monotonic() + 30 if deadline is None else deadline)

    def assert_bounds(self, points, minimum, maximum):
        for axis in range(3):
            self.assertAlmostEqual(min(point[axis] for point in points), minimum[axis], places=10)
            self.assertAlmostEqual(max(point[axis] for point in points), maximum[axis], places=10)

    def test_real_native_formats_geometry_units_instancing_appearance_and_publication(self):
        rid = self.revision(shift=7)
        with self.session(rid) as session:
            products = {row.format: row for row in session.prepare(self.targets)}
            header, points, refs = glb_read(products["glb"].payload)
            self.assert_bounds(points, (.012, 0, -.003), (.034, .004, 0))
            self.assertEqual([0, 0, 1], refs)
            self.assertEqual(2, len(header["meshes"]))
            material = header["materials"][0]
            self.assertEqual([.1234567890123456, .3456789012345678, .6789012345678901, .7 * .4],
                             material["pbrMetallicRoughness"]["baseColorFactor"])
            self.assertEqual(.23, material["pbrMetallicRoughness"]["roughnessFactor"])
            self.assertEqual(.2, material["extensions"]["KHR_materials_clearcoat"]["clearcoatFactor"])
            self.assertEqual("authored-alloy", header["nodes"][1]["extras"]["authored"]["material"])
            _, resources, objects, points, refs, core, extension = mf_read(products["3mf"].payload)
            self.assert_bounds(points, (12, 0, 0), (34, 3, 4))
            self.assertEqual([3, 3, 4], refs)
            self.assertEqual(2, sum(row.find(core + "mesh") is not None for row in objects.values()))
            colors = resources.find(extension + "colorgroup")
            finishes = resources.find(extension + "pbmetallicdisplayproperties")
            self.assertEqual("1", colors.attrib["displaypropertiesid"])
            self.assertEqual(len(colors), len(finishes))
            self.assertEqual(.23, float(finishes[0].attrib["roughness"]))
            self.assertEqual(.63, float(finishes[0].attrib["metallicness"]))
            stl = products["stl"].payload
            triangles, = struct.unpack_from("<I", stl, 80)
            self.assertEqual(36, triangles)
            self.assertEqual(84 + triangles * 50, len(stl))
            points = [struct.unpack_from("<3f", stl, 84 + face * 50 + 12 + corner * 12)
                      for face in range(triangles) for corner in range(3)]
            self.assert_bounds(points, (12, 0, 0), (34, 3, 4))
            self.assertEqual("none", products["stl"].facts["capabilities"]["color"])
            self.assertIn("color.alpha", products["3mf"].facts["omissions"][0]["fields"])
            with self.assertRaises(TypeError):
                products["glb"].facts["codec"] = 99
            with session.stage_outputs(self.targets) as staged:
                for item in staged:
                    self.assertFalse(item.destination.exists())
                    receipt = session.publish_staged(item, expected_prior_digest=None)
                    self.assertEqual("written", receipt.action)
                    self.assertEqual(item.product.sha256, hashlib.sha256(item.destination.read_bytes()).hexdigest())
            self.assertEqual(RevisionState.EXPORTS_COMPLETE, self.document.state(rid))
            self.assertTrue(self.encoder.last_receipt.reaped)
            self.assertTrue(self.encoder.last_receipt.temporary_files_removed)
            self.assertFalse(any(self.directory.glob("native-mesh-*")))

    def test_quality_is_the_display_packet_and_warm_reuse_does_not_encode_or_stage(self):
        rid = self.revision(formats=("glb",))
        options = MeshOptions(relative_chord=.003, angular=.2, edges=False)
        previous = build_display(self.document, rid, options=options)
        with self.session(rid) as session:
            original, = session.prepare(("glb",), options=options, previous_display=previous)
            self.assertTrue(all(asset.payload is previous.assets[key].payload for key, asset in session.display.assets.items()))
            for asset in session.display.assets.values():
                header, _ = unpack_mesh(asset.payload)
                self.assertEqual(.003, header["options"]["relative_chord"])
            with session.stage_outputs({"glb": self.targets["glb"]}) as staged:
                session.publish_staged(staged[0], expected_prior_digest=None)
        newer = self.revision(formats=("glb",), prefix="different-source-keys")
        with self.session(newer) as session, patch.object(self.encoder, "_run", side_effect=AssertionError("encoded warm bytes")):
            reused, = session.prepare(("glb",), options=options, previous_display=previous)
            self.assertIs(original, reused)
            with patch("cadgen._document.mesh_product.tempfile.NamedTemporaryFile", side_effect=AssertionError("staged warm bytes")):
                with session.stage_outputs({"glb": self.targets["glb"]}) as staged:
                    self.assertIsNone(staged[0].staged_path)
                    receipt = session.publish_staged(staged[0], expected_prior_digest=original.sha256)
                    self.assertEqual("verified-existing", receipt.action)

    def test_appearance_edit_reuses_native_packet_and_changes_encoded_material(self):
        first = self.revision(formats=("glb",))
        with self.session(first) as session:
            original, = session.prepare(("glb",))
            previous = session.display
        second = self.revision(formats=("glb",), roughness=.91)
        with self.session(second) as session:
            changed, = session.prepare(("glb",), previous_display=previous)
            self.assertNotEqual(original.sha256, changed.sha256)
            self.assertEqual(.91, glb_read(changed.payload)[0]["materials"][0]["pbrMetallicRoughness"]["roughnessFactor"])
            self.assertTrue(all(asset is previous.assets[key] for key, asset in session.display.assets.items()))

    def test_replacement_and_second_output_failure_preserve_truthful_receipts(self):
        rid = self.revision(formats=("stl", "glb"))
        self.targets["stl"].write_bytes(b"old bytes")
        prior = hashlib.sha256(b"old bytes").hexdigest()
        completed = []
        with self.session(rid) as session:
            session.prepare(("stl", "glb"))
            with session.stage_outputs({key: self.targets[key] for key in ("stl", "glb")}) as staged:
                session.publish_staged(staged[0], expected_prior_digest=prior, completed=completed.append)
                with patch("cadgen._document.mesh_product.os.replace", side_effect=OSError("disk failure")):
                    with self.assertRaisesRegex(OSError, "disk failure"):
                        session.publish_staged(staged[1], expected_prior_digest=None, completed=completed.append)
            self.assertEqual(1, len(completed))
            self.assertEqual(prior, completed[0].previous_sha256)
            self.assertNotEqual(RevisionState.EXPORTS_COMPLETE, self.document.state(rid))
            self.assertFalse(self.targets["glb"].exists())
            self.assertFalse(any(self.directory.glob("*.stage")))

    def test_external_replacement_after_effect_retains_receipt_without_full_success(self):
        rid = self.revision(formats=("glb",))
        completed = []
        with self.session(rid) as session:
            session.prepare(("glb",))
            with session.stage_outputs({"glb": self.targets["glb"]}) as staged:
                def displaced(receipt):
                    completed.append(receipt)
                    self.targets["glb"].write_bytes(b"external")
                with self.assertRaisesRegex(ExportConflict, "at publication"):
                    session.publish_staged(staged[0], expected_prior_digest=None, completed=displaced)
            self.assertEqual("written", completed[0].action)
            self.assertNotEqual(RevisionState.EXPORTS_COMPLETE, self.document.state(rid))
            self.assertEqual(b"external", self.targets["glb"].read_bytes())

    def test_warm_unstaged_drift_symlink_and_deadline_fail_closed(self):
        rid = self.revision(formats=("stl",))
        target = self.targets["stl"]
        with self.session(rid) as session:
            product, = session.prepare(("stl",))
            target.write_bytes(product.payload)
            with session.stage_outputs({"stl": target}) as staged:
                target.write_bytes(b"external")
                with self.assertRaisesRegex(ExportConflict, "unstaged"):
                    session.publish_staged(staged[0], expected_prior_digest=hashlib.sha256(b"external").hexdigest())
            target.unlink()
            target.symlink_to(self.targets["glb"])
            with self.assertRaisesRegex(ExportConflict, "symlink"):
                with session.stage_outputs({"stl": target}):
                    self.fail("followed symlink")
            target.unlink()
            session._budget.deadline = time.monotonic() - 1
            with self.assertRaises(TimeoutError):
                with session.stage_outputs({"stl": target}):
                    self.fail("staged after deadline")
            self.assertFalse(target.exists())

    def test_deadline_after_rename_preserves_effect_receipt_but_not_export_completion(self):
        rid = self.revision(formats=("stl",))
        completed = []
        with self.session(rid) as session:
            product, = session.prepare(("stl",))
            with session.stage_outputs({"stl": self.targets["stl"]}) as staged:
                def expired(receipt):
                    completed.append(receipt)
                    session._budget.deadline = time.monotonic() - 1
                with self.assertRaises(TimeoutError):
                    session.publish_staged(staged[0], expected_prior_digest=None, completed=expired)
            self.assertEqual(product.sha256, hashlib.sha256(self.targets["stl"].read_bytes()).hexdigest())
            self.assertEqual("written", completed[0].action)
            self.assertNotEqual(RevisionState.EXPORTS_COMPLETE, self.document.state(rid))


class MeshEncoderLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="native-mesh-codec-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.encoder = MeshEncoder()

    def run_program(self, program, *, timeout=3, cancellation=None):
        self.encoder._program = program.encode()
        return self.encoder._run((b"closed packet",), work_directory=self.directory,
                                 budget=Budget(time.monotonic() + timeout, cancellation))

    def assert_cleanup(self):
        receipt = self.encoder.last_receipt
        self.assertTrue(receipt.reaped)
        self.assertTrue(receipt.temporary_files_removed)
        self.assertEqual([], list(self.directory.iterdir()))
        if receipt.pid is not None and os.name != "nt":
            with self.assertRaises(ProcessLookupError):
                os.kill(receipt.pid, 0)

    def test_deadline_and_cancellation_reap_encoder_and_remove_all_private_files(self):
        start = time.monotonic()
        with self.assertRaises(TimeoutError):
            self.run_program("setInterval(() => {}, 1000)", timeout=.15)
        self.assertLess(time.monotonic() - start, 2)
        self.assert_cleanup()
        cancelled = threading.Event()
        timer = threading.Timer(.15, cancelled.set)
        timer.start()
        try:
            with self.assertRaises(Cancelled):
                self.run_program("setInterval(() => {}, 1000)", cancellation=cancelled)
        finally:
            timer.join()
        self.assert_cleanup()

    def test_output_capacity_is_checked_before_read_and_failed_child_is_reaped(self):
        program = "import fs from 'node:fs'; fs.writeSync(1, Buffer.alloc(4096)); setInterval(() => {}, 1000)"
        with patch("cadgen._document.mesh_encoder.MAX_OUTPUT_BYTES", 1024):
            with self.assertRaisesRegex(MeshEncodingError, "bounded regular"):
                self.run_program(program)
        self.assert_cleanup()
        with self.assertRaisesRegex(MeshEncodingError, "concrete failure"):
            self.run_program("process.stderr.write('concrete failure'); process.exitCode=2")
        self.assert_cleanup()

    def test_input_staging_time_is_part_of_absolute_deadline(self):
        from cadgen._document import mesh_encoder
        original = mesh_encoder._write
        def delayed(*args):
            time.sleep(.05)
            return original(*args)
        with patch.object(mesh_encoder, "_write", side_effect=delayed):
            with self.assertRaises(TimeoutError):
                self.run_program("process.exitCode=0", timeout=.02)
        self.assert_cleanup()
        self.assertIsNone(self.encoder.last_receipt.pid)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires a real FIFO")
    def test_destination_fifo_is_rejected_without_opening_a_blocking_reader(self):
        target = self.directory / "part.stl"
        os.mkfifo(target)
        started = time.monotonic()
        with self.assertRaisesRegex(ExportConflict, "regular file"):
            destination_digest(target, Budget(started + .1))
        self.assertLess(time.monotonic() - started, .1)

    def test_capture_is_independent_of_later_program_file_and_environment_changes(self):
        runtime = self.directory / "runtime"
        (runtime / "node").mkdir(parents=True)
        script = runtime / "node" / "document-mesh-export.mjs"
        script.write_text("process.stdout.write('captured')")
        with patch("cadgen._document.mesh_encoder.runtime_root", return_value=runtime):
            encoder = MeshEncoder()
        script.write_text("process.stdout.write('changed')")
        with patch.dict(os.environ, {"NODE_OPTIONS": "--not-a-real-node-option"}):
            output = encoder._run((), work_directory=self.directory,
                                  budget=Budget(time.monotonic() + 3))
        self.assertEqual(b"captured", output)
        self.assertTrue(encoder.last_receipt.reaped)
        self.assertTrue(encoder.last_receipt.temporary_files_removed)

    def test_output_framing_refuses_hash_size_and_trailing_payload_changes(self):
        payload = b"mesh bytes"
        facts = {"codec": 1, "format": "stl", "triangles": 1, "prototypeVariants": 1, "occurrences": 1,
                 "capabilities": {"units": "millimeter", "instancing": False, "color": "none", "pbr": [], "authoredMetadata": False},
                 "omissions": [], "precision": {"positions": "world-float32", "color": "none", "maxPositionRoundingMm": 0}}
        value = {"version": 1, "runtime": {"node": "v22", "v8": "12"}, "products": [
            {"format": "stl", "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "facts": facts}]}
        def frame():
            header = json.dumps(value).encode()
            return b"CGEXOU01" + struct.pack("<I", len(header)) + header + payload
        with self.assertRaisesRegex(MeshEncodingError, "trailing"):
            _parse_output(frame() + b"x", formats=("stl",), name="part", program_sha256="a" * 64)
        value["products"][0]["sha256"] = "b" * 64
        with self.assertRaisesRegex(MeshEncodingError, "digest mismatch"):
            _parse_output(frame(), formats=("stl",), name="part", program_sha256="a" * 64)
        value["products"][0]["bytes"] = 128 * 1024**2 + 1
        with self.assertRaisesRegex(MeshEncodingError, "capacity"):
            _parse_output(frame(), formats=("stl",), name="part", program_sha256="a" * 64)


if __name__ == "__main__":
    unittest.main()
