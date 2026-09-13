"""Actual-byte STEP imports preserve XCAF structure without source/store reuse."""
from __future__ import annotations

import math
from pathlib import Path
from threading import Event
import unittest
from unittest.mock import patch

from cadgen._document import Document, NativeResult, OperatorSpec
from cadgen._document.consumers import RevisionConsumer
from cadgen._document.resources import AdmissionDenied, Cancelled, ResourceAdmission
from cadgen._document.roots import AssemblyGroup, GeometryLeaf, IDENTITY_TRANSFORM
from cadgen._document.sources import CapturedInput
from cadgen._document.step_import import StepImportSession, UnsupportedStepImport
from cadgen._document.step_product import (StepProductSession, _owned_xcaf_document,
                                           destination_digest)
from tests.python.support.tmp_root import generated_cad_directory


def translation(x=0., y=0., z=0.):
    result = list(IDENTITY_TRANSFORM)
    result[3], result[7], result[11] = x, y, z
    return tuple(result)


def _box(tx, size=(4., 3., 2.)):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

    return tx.evaluate(OperatorSpec("test.step-import.box"), size, (),
                       lambda _inputs, _arena: NativeResult(BRepPrimAPI_MakeBox(*size).Shape()))


def _plate(tx):
    def compute(_inputs, _arena):
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

        result = BRepPrimAPI_MakeBox(16., 8., 2.).Shape()
        for x in (4., 12.):
            hole = BRepPrimAPI_MakeCylinder(
                gp_Ax2(gp_Pnt(x, 4., -1.), gp_Dir(0., 0., 1.)), 1., 4.).Shape()
            result = BRepAlgoAPI_Cut(result, hole).Shape()
        return NativeResult(result)

    return tx.evaluate(OperatorSpec("test.step-import.plate"), (), (), compute)


def _native_facts(native, _transform):
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    volume = GProp_GProps()
    BRepGProp.VolumeProperties_s(native, volume)
    return {"valid": bool(BRepCheck_Analyzer(native).IsValid()),
            "volume": float(volume.Mass())}


class StepImportTests(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="document-step-import-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.target = self.directory / "fixture.step"
        self.imported = Document("imported STEP", runtime={"fixture": "import-v1"})
        self.session = StepImportSession(
            self.imported, work_directory=self.directory / "import-staging")

    def _write(self, root_builder, *, primitive=_box, size=(4., 3., 2.)):
        source = Document("writer only", runtime={"fixture": "writer-v1"})
        with source.begin("authored geometry", required_exports=(str(self.target),)) as tx:
            handle = primitive(tx) if primitive is not _box else primitive(tx, size)
            tx.bind_root(root_builder(handle), unrepresented_metadata=())
            revision = tx.commit()
        with StepProductSession(source, revision.revision_id,
                                work_directory=self.directory / "writer-staging") as product:
            prepared = product.prepare(self.target.name)
            product.publish(self.target, expected_prior_digest=destination_digest(self.target))
        return source, handle, prepared

    def _single(self, *, primitive=_box, size=(4., 3., 2.), label="part"):
        return self._write(lambda handle: GeometryLeaf("part", handle, label=label),
                           primitive=primitive, size=size)

    def test_small_plate_is_a_byte_bound_mm_document_after_source_removal(self):
        self._single(primitive=_plate, label="drilled plate")
        source_file = self.directory / "plate.py"
        source_file.write_text("this source must not be read\n")
        captured = CapturedInput.read(self.target)
        source_file.unlink()
        imported = self.session.load(captured)
        self.assertFalse(source_file.exists())
        self.assertEqual((self.session.metrics.native_parses,
                          self.session.metrics.prototype_captures), (1, 1))
        self.assertEqual(imported.coordinate_unit, "MM")
        self.assertEqual(imported.metadata_attestation,
                         ("names-preserved", "occurrence-colors-preserved",
                      "per-face-colors-exact-native-map", "physical-materials-preserved"))
        self.assertEqual(imported.input_sha256, captured.digest)
        self.assertEqual(imported.root_bounds, (0., 0., 0., 16., 8., 2.))
        with RevisionConsumer(self.imported, imported.revision_id) as consumer:
            occurrence = consumer.occurrences()[0]
            self.assertEqual(occurrence.label, "drilled plate")
            facts = consumer.query_value(occurrence.path, _native_facts)
        self.assertTrue(facts["valid"])
        self.assertAlmostEqual(facts["volume"], 256. - 4. * math.pi, places=5)

    def test_inch_step_coordinates_are_normalized_to_millimeters(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.Interface import Interface_Static
        from OCP.STEPControl import (STEPControl_AsIs, STEPControl_Controller,
                                     STEPControl_Writer)

        STEPControl_Controller.Init_s()
        previous = Interface_Static.CVal_s("write.step.unit")
        try:
            Interface_Static.SetCVal_s("write.step.unit", "INCH")
            writer = STEPControl_Writer()
            self.assertEqual(
                writer.Transfer(BRepPrimAPI_MakeBox(25.4, 12.7, 6.35).Shape(),
                                STEPControl_AsIs), IFSelect_RetDone)
            self.assertEqual(writer.Write(str(self.target)), IFSelect_RetDone)
        finally:
            Interface_Static.SetCVal_s("write.step.unit", previous)
        self.assertIn("INCH", self.target.read_text(errors="ignore"))
        imported = self.session.load(CapturedInput.read(self.target))
        self.assertEqual(imported.coordinate_unit, "MM")
        self.assertEqual(imported.root_bounds, (0., 0., 0., 25.4, 12.7, 6.35))

    def test_24_occurrences_share_one_canonical_definition_and_retained_hit(self):
        self._write(lambda handle: AssemblyGroup(
            "assembly", tuple(GeometryLeaf(f"p{i}", handle, translation(i * 5., 0., 0.),
                                            f"part-{i}") for i in range(24)),
            label="assembly"))
        captured = CapturedInput.read(self.target)
        first = self.session.load(captured)
        self.assertEqual((first.geometry_occurrences, first.node_count), (24, 25))
        self.assertEqual(len(first.prototype_ids), 1)
        with RevisionConsumer(self.imported, first.revision_id) as consumer:
            occurrences = consumer.occurrences()
            self.assertEqual(len(occurrences), 24)
            self.assertEqual(len({item.prototype_id for item in occurrences}), 1)
            self.assertEqual([item.label for item in occurrences],
                             [f"part-{i}" for i in range(24)])
        with patch.object(self.session, "_parse_capture",
                          side_effect=AssertionError("native parse/capture on retained hit")):
            second = self.session.load(CapturedInput.read(self.target))
        self.assertNotEqual(first.revision_id, second.revision_id)
        self.assertEqual((self.session.metrics.native_parses,
                          self.session.metrics.retained_hits,
                          self.session.metrics.prototype_captures), (1, 1, 1))

    def test_nested_placements_names_and_distinct_colors_are_occurrence_values(self):
        red, blue = (1., 0., 0., 1.), (0., 0., 1., 1.)

        def root(handle):
            group = AssemblyGroup(
                "group",
                (GeometryLeaf("red", handle, translation(2., 0., 0.), "red", {"color": red}),
                 GeometryLeaf("blue", handle, translation(8., 0., 0.), "blue", {"color": blue})),
                translation(0., 10., 0.), "group")
            return AssemblyGroup("root", (group,), translation(20., 0., 3.), "root")

        self._write(root)
        imported = self.session.load(CapturedInput.read(self.target))
        with RevisionConsumer(self.imported, imported.revision_id) as consumer:
            by_label = {item.label: item for item in consumer.occurrences()}
        self.assertEqual(set(by_label), {"red", "blue"})
        self.assertEqual(tuple(by_label["red"].appearance["color"]), red)
        self.assertEqual(tuple(by_label["blue"].appearance["color"]), blue)
        self.assertEqual((by_label["red"].transform[3], by_label["red"].transform[7],
                          by_label["red"].transform[11]), (22., 10., 3.))
        self.assertEqual((by_label["blue"].transform[3], by_label["blue"].transform[7],
                          by_label["blue"].transform[11]), (28., 10., 3.))
        self.assertEqual(imported.root_bounds, (22., 10., 3., 32., 13., 5.))

    def test_imported_geometry_follows_lossy_saved_bytes_not_source_shape(self):
        import build123d as bd

        def cap(tx):
            def compute(_inputs, _arena):
                sphere = bd.Rot(90, 0, 0) * bd.Rot(0, 0, -90) * bd.Sphere(1)
                ellipsoid = sphere.transform_geometry(
                    bd.Matrix([[2.7, 0, 0, 0], [0, 2.7, 0, 0],
                               [0, 0, 1.4, 0], [0, 0, 0, 1]]))
                pad = bd.Pos(0, 0, 5.4) * ellipsoid
                return NativeResult(
                    (pad - bd.Pos(0, 0, 4.15 - 10) * bd.Box(30, 30, 20)).wrapped)
            return tx.evaluate(OperatorSpec("test.step-import.lossy-cap"), (), (), compute)

        source, handle, _product = self._single(primitive=cap, label="lossy cap")
        authored_volume = _native_facts(source._get(handle).shape, ())["volume"]
        imported = self.session.load(CapturedInput.read(self.target))
        with RevisionConsumer(self.imported, imported.revision_id) as consumer:
            occurrence = consumer.occurrences()[0]
            saved_volume = consumer.query_value(occurrence.path, _native_facts)["volume"]
        independent = bd.import_step(str(self.target)).volume
        self.assertGreater(authored_volume, 40.)
        self.assertLess(saved_volume, 1.)
        self.assertAlmostEqual(saved_volume, independent, places=6)

    def test_same_path_changed_bytes_reparse_and_pin_controls_collection(self):
        self._single(size=(4., 3., 2.))
        first = self.session.load(CapturedInput.read(self.target))
        pin = self.imported.pin(first.revision_id)
        self._single(size=(7., 3., 2.))
        second = self.session.load(CapturedInput.read(self.target))
        self.assertNotEqual(first.input_sha256, second.input_sha256)
        self.assertEqual((self.session.metrics.native_parses,
                          self.session.metrics.prototype_captures), (2, 2))
        self.imported.collect(keep_revisions=0)
        self.assertIn(first.identity, self.imported._step_imports.entries)
        pin.release()
        self.imported.collect(keep_revisions=0)
        self.assertNotIn(first.identity, self.imported._step_imports.entries)
        self.assertIn(second.identity, self.imported._step_imports.entries)

    def test_cancellation_admission_and_supported_native_appearance(self):
        self._single()
        event = Event()
        event.set()
        cancelled = StepImportSession(self.imported,
                                      work_directory=self.directory / "cancelled",
                                      cancellation=event)
        with self.assertRaises(Cancelled):
            cancelled.load(CapturedInput.read(self.target))
        self.assertEqual(cancelled.metrics.cancelled, 1)
        self.assertEqual(cancelled.metrics.admitted_native_jobs, 0)
        self.assertIsNone(self.imported.head)

        mid_event = Event()
        mid_document = Document("mid-parse cancellation")
        mid = StepImportSession(mid_document,
                                work_directory=self.directory / "mid-cancelled",
                                cancellation=mid_event)

        def cancel_after_parse(*_args):
            mid_event.set()

        with patch("cadgen._document.step_import._reject_unrepresented_metadata",
                   side_effect=cancel_after_parse), self.assertRaises(Cancelled):
            mid.load(CapturedInput.read(self.target))
        self.assertEqual((mid.metrics.native_parses, mid.metrics.admitted_native_jobs,
                          mid.metrics.prototype_captures, mid.metrics.cancelled),
                         (1, 1, 0, 1))
        self.assertIsNone(mid_document.head)

        import build123d as bd
        from cadgen.step_export import export_build123d_step_file

        colored = bd.Box(3, 3, 3)
        colored.cad_face_ordinal_colors = {1: (1., 0., 0., 1.)}
        export_build123d_step_file(colored, self.target)
        fresh = Document("colored STEP metadata")
        importer = StepImportSession(fresh, work_directory=self.directory / "colored")
        colored_result = importer.load(CapturedInput.read(self.target))
        self.assertEqual(1, len(colored_result.root.appearance["face_colors"]))
        self.assertEqual((1., 0., 0., 1.), colored_result.root.appearance["face_colors"][0][1])
        self.assertIsNotNone(fresh.head)
        self.assertEqual(importer.metrics.native_parses, 1)
        self.assertEqual(importer.metrics.prototype_captures, 1)

        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.TCollection import TCollection_HAsciiString
        from OCP.XCAFDoc import XCAFDoc_DocumentTool
        from cadgen.step_export import write_xcaf_doc_step_file

        with _owned_xcaf_document() as material_document:
            shapes = XCAFDoc_DocumentTool.ShapeTool_s(material_document.Main())
            label = shapes.AddShape(BRepPrimAPI_MakeBox(2., 2., 2.).Shape(), False)
            materials = XCAFDoc_DocumentTool.MaterialTool_s(material_document.Main())
            def text(value):
                return TCollection_HAsciiString(value)
            materials.SetMaterial(label, text("steel"), text("fixture"), 7.8,
                                  text("density"), text("g/cm3"))
            write_xcaf_doc_step_file(material_document, self.target)
        material_import = StepImportSession(
            Document("physical STEP material"),
            work_directory=self.directory / "physical-material")
        imported_material = material_import.load(CapturedInput.read(self.target))
        self.assertEqual({"name": "steel", "description": "fixture", "density": 7.8,
                          "density_name": "density", "density_type": ""},
                         imported_material.root.appearance["physical_material"])
        self.assertEqual((material_import.metrics.native_parses,
                          material_import.metrics.prototype_captures), (1, 1))

        denied_document = Document(
            "denied STEP import", admission=ResourceAdmission(cpu_slots=0))
        denied = StepImportSession(denied_document,
                                   work_directory=self.directory / "denied")
        with self.assertRaises(AdmissionDenied):
            denied.load(CapturedInput.read(self.target))
        self.assertEqual(denied.metrics.admission_denied, 1)
        self.assertEqual(denied.metrics.admitted_native_jobs, 0)
        self.assertEqual(denied.metrics.native_parses, 0)
        self.assertIsNone(denied_document.head)


if __name__ == "__main__":
    unittest.main()
