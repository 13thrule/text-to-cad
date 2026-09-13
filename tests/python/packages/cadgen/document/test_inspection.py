"""Actual OCCT facts, exact mesh references, placement and ownership isolation."""
import dataclasses
import json
import math
import struct
import unittest
from threading import Event
from unittest.mock import patch

from cadgen._document import Document, GeometryLeaf, AssemblyGroup, IDENTITY_TRANSFORM
from cadgen._document.core import OperatorSpec
from cadgen._document.native import NativeResult
from cadgen._document.consumers import RevisionConsumer, OccurrencePath
from cadgen._document.inspection import TopologyReference, InvalidTopologyReference, inspect_batch, reference
from cadgen._document.meshing import MeshOptions, mesh_for_occurrence, unpack_mesh
from cadgen._document.resources import Cancelled


def document(shape, transform=IDENTITY_TRANSFORM):
    doc = Document("inspection")
    with doc.begin() as tx:
        handle = tx.evaluate(OperatorSpec("fixture"), (), (), lambda *_: NativeResult(shape))
        tx.bind_root(AssemblyGroup("root", (GeometryLeaf("part", handle, transform),)), unrepresented_metadata=())
        revision = tx.commit()
    return doc, revision, handle


def box():
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    return BRepPrimAPI_MakeBox(2., 3., 4.).Shape()


class InspectionTests(unittest.TestCase):
    def test_component_and_mesh_face_edge_ordinals_match_actual_box(self):
        doc, revision, _ = document(box())
        with RevisionConsumer(doc, revision.revision_id) as consumer:
            path = consumer.occurrences()[0].path
            mesh = mesh_for_occurrence(consumer, path)
            header, arrays = unpack_mesh(mesh)
            refs = (reference(consumer, path),
                    *(reference(consumer, path, "face", i) for i in range(6)),
                    *(reference(consumer, path, "edge", i) for i in range(12)))
            start = consumer.metrics.queries_completed
            facts = inspect_batch(consumer, refs)
            self.assertEqual(start + 1, consumer.metrics.queries_completed, "one occurrence shares maps and admission")
            whole = facts[0]
            self.assertEqual({"solid": 1, "face": 6, "edge": 12, "vertex": 8}, whole["counts"])
            self.assertAlmostEqual(24, whole["volume"])
            self.assertEqual(52, whole["area"])
            self.assertEqual(36, whole["edge_length"])
            self.assertEqual((1., 1.5, 2.), whole["centroid"])
            self.assertEqual("volume", whole["centroid_basis"])
            self.assertEqual({"length": "mm", "area": "mm²", "volume": "mm³"}, whole["units"])
            coords = [v for v, in struct.iter_unpack("<f", arrays["positions"])]
            indices = [v for v, in struct.iter_unpack("<I", arrays["indices"])]
            for ordinal, _, _, first, count in header["faces"]:
                area = 0.
                for offset in range(first, first + count, 3):
                    a, b, c = [coords[index * 3:index * 3 + 3] for index in indices[offset:offset + 3]]
                    u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
                    cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
                    area += math.sqrt(sum(value*value for value in cross)) / 2
                self.assertAlmostEqual(area, facts[ordinal + 1]["area"])
                self.assertEqual("plane", facts[ordinal + 1]["geometry_kind"])
            self.assertEqual([2., 2., 2., 2., 3., 3., 3., 3., 4., 4., 4., 4.], sorted(row["length"] for row in facts[7:]))
            with self.assertRaises(TypeError):
                whole["counts"]["face"] = 999

    def test_trimmed_hole_area_length_and_centroid_are_native_not_bbox_guesses(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
        shape = BRepAlgoAPI_Cut(BRepPrimAPI_MakeBox(20., 15., 10.).Shape(),
                               BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(6, 5, -2), gp_Dir(0, 0, 1)), 3., 14.).Shape()).Shape()
        doc, revision, _ = document(shape)
        with RevisionConsumer(doc, revision.revision_id) as consumer:
            path = consumer.occurrences()[0].path
            root = inspect_batch(consumer, (reference(consumer, path),))[0]
            faces = inspect_batch(consumer, tuple(reference(consumer, path, "face", i) for i in range(root["counts"]["face"])))
            self.assertAlmostEqual(3000 - 90 * math.pi, root["volume"], places=6)
            hole = next(face for face in faces if face["geometry_kind"] == "cylinder")
            self.assertAlmostEqual(60 * math.pi, hole["area"], places=6)
            for actual, expected in zip(hole["centroid"], (6, 5, 5)):
                self.assertAlmostEqual(expected, actual, places=6)
            top = next(face for face in faces if abs(face["centroid"][2] - 10) < 1e-8)
            area = 300 - 9 * math.pi
            self.assertAlmostEqual(area, top["area"], places=6)
            self.assertAlmostEqual((3000 - 54 * math.pi) / area, top["centroid"][0], places=6)
            self.assertAlmostEqual((2250 - 45 * math.pi) / area, top["centroid"][1], places=6)

    def test_curved_and_degenerate_edges_have_correct_measure_semantics(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
        doc, revision, _ = document(BRepPrimAPI_MakeSphere(10.).Shape())
        with RevisionConsumer(doc, revision.revision_id) as consumer:
            path = consumer.occurrences()[0].path
            facts = inspect_batch(consumer, (reference(consumer, path), reference(consumer, path, "face", 0)))
            self.assertAlmostEqual(4 * math.pi * 1000 / 3, facts[0]["volume"], places=6)
            self.assertAlmostEqual(400 * math.pi, facts[1]["area"], places=6)
            self.assertEqual("sphere", facts[1]["geometry_kind"])
            edges = inspect_batch(consumer, tuple(reference(consumer, path, "edge", i) for i in range(facts[0]["counts"]["edge"])))
            poles = [edge for edge in edges if edge["geometry_kind"] == "degenerate"]
            self.assertEqual(2, len(poles))
            self.assertTrue(all(edge["length"] == 0 and edge["centroid"] is None for edge in poles))

    def test_placed_rotated_mirrored_scaled_and_general_affine_facts(self):
        transforms = (
            ((0, -2, 0, 100, -2, 0, 0, 20, 0, 0, 2, 5, 0, 0, 0, 1),
             192., 208., (97, 18, 9), (94, 16, 5), (100, 20, 13)),
            ((2, 0, 0, 0, 0, 3, 0, 0, 0, 0, 4, 0, 0, 0, 0, 1),
             576., 488., (2, 4.5, 8), (0, 0, 0), (4, 9, 16)),
        )
        for matrix, volume, area, center, low, high in transforms:
            doc, revision, _ = document(box(), matrix)
            with RevisionConsumer(doc, revision.revision_id) as consumer:
                ref = reference(consumer, consumer.occurrences()[0].path)
                result = inspect_batch(consumer, (ref,))[0]
                self.assertAlmostEqual(volume, result["volume"], places=6)
                self.assertAlmostEqual(area, result["area"], places=6)
                for actual, expected in zip(result["centroid"], center):
                    self.assertAlmostEqual(expected, actual, places=6)
                for bound, expected in (("min", low), ("max", high)):
                    for a, e in zip(result["bounds"][bound], expected):
                        self.assertAlmostEqual(e, a, places=6)
                prototype = inspect_batch(consumer, (ref,), space="prototype")[0]
                self.assertAlmostEqual(24, prototype["volume"])
                self.assertEqual((1., 1.5, 2.), prototype["centroid"])
                face, edge = inspect_batch(consumer, (reference(consumer, ref.path, "face", 0),
                                                     reference(consumer, ref.path, "edge", 0)))
                self.assertAlmostEqual(48. if matrix[0] == 0 else 144., face["area"], places=6)
                self.assertAlmostEqual(8. if matrix[0] == 0 else 16., edge["length"], places=6)

    def test_open_geometry_reversed_solid_and_singular_placement(self):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace
        from OCP.gp import gp_Pnt, gp_Pln, gp_Dir
        fixtures = (
            (BRepBuilderAPI_MakeEdge(gp_Pnt(1, 2, 3), gp_Pnt(4, 6, 3)).Shape(),
             "edge", 0., 5., (2.5, 4., 3.), "length"),
            (BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 3), gp_Dir(0, 0, 1)), 0., 2., 0., 4.).Shape(),
             "face", 8., 12., (1., 2., 3.), "area"),
        )
        for shape, kind, area, length, center, basis in fixtures:
            doc, revision, _ = document(shape)
            with RevisionConsumer(doc, revision.revision_id) as consumer:
                facts = inspect_batch(consumer, (reference(consumer, consumer.occurrences()[0].path),))[0]
                self.assertEqual(kind, facts["geometry_kind"])
                self.assertIsNone(facts["volume"])
                self.assertEqual("no-solid", facts["volume_status"])
                self.assertAlmostEqual(area, facts["area"])
                self.assertAlmostEqual(length, facts["edge_length"])
                self.assertEqual(center, facts["centroid"])
                self.assertEqual(basis, facts["centroid_basis"])
        doc, revision, _ = document(box().Reversed())
        with RevisionConsumer(doc, revision.revision_id) as consumer:
            result = inspect_batch(consumer, (reference(consumer, consumer.occurrences()[0].path),))[0]
            self.assertAlmostEqual(24., result["volume"])
            self.assertEqual((1., 1.5, 2.), result["centroid"])
        singular = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1)
        doc, revision, _ = document(box(), singular)
        with RevisionConsumer(doc, revision.revision_id) as consumer:
            ref = reference(consumer, consumer.occurrences()[0].path)
            with self.assertRaisesRegex(ValueError, "nonsingular"):
                inspect_batch(consumer, (ref,))
            self.assertAlmostEqual(24., inspect_batch(consumer, (ref,), space="prototype")[0]["volume"])

    def test_composed_transform_overflow_is_rejected_before_native_transform(self):
        from cadgen._document import inspection
        huge = (1e308, 0, 0, 0, 0, 1e308, 0, 0, 0, 0, 1e308, 0, 0, 0, 0, 1)
        doc, _, handle = document(box())
        with doc.begin() as tx:
            tx.bind_root(AssemblyGroup("root", (GeometryLeaf("part", handle, huge),), transform=huge))
            revision = tx.commit()
        with RevisionConsumer(doc, revision.revision_id) as consumer:
            ref = reference(consumer, consumer.occurrences()[0].path)
            with patch.object(inspection, "_facts", side_effect=AssertionError("invalid transform reached facts")):
                with self.assertRaisesRegex(ValueError, "finite composed"):
                    inspect_batch(consumer, (ref,))

    def test_closed_reference_schema_stale_forged_and_out_of_range_rejected(self):
        doc, revision, handle = document(box())
        with RevisionConsumer(doc, revision.revision_id) as consumer:
            ref = reference(consumer, consumer.occurrences()[0].path, "face", 0)
            encoded = json.loads(json.dumps(dict(ref.to_value())))
            self.assertEqual(ref, TopologyReference.from_value(encoded))
            with self.assertRaises(dataclasses.FrozenInstanceError):
                ref.ordinal = 1
            for bad in (dataclasses.replace(ref, prototype_id="forged"),
                        dataclasses.replace(ref, path=OccurrencePath("foreign", revision.revision_id, ref.path.nodes)),
                        dataclasses.replace(ref, ordinal=99)):
                with self.assertRaises(InvalidTopologyReference):
                    inspect_batch(consumer, (bad,))
            for key, value in (("unknown", 1), ("version", 2), ("ordinal", True)):
                with self.assertRaises((InvalidTopologyReference, TypeError)):
                    TopologyReference.from_value({**encoded, key: value})
            with doc.begin() as tx:
                tx.bind_root(GeometryLeaf("new-root", handle))
                newer = tx.commit()
            with RevisionConsumer(doc, newer.revision_id) as current:
                with self.assertRaises(InvalidTopologyReference):
                    inspect_batch(current, (ref,))
        with self.assertRaises(RuntimeError):
            inspect_batch(consumer, (ref,))

    def test_inspection_keeps_native_mesh_locations_and_allocations_unchanged(self):
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRep import BRep_Tool
        from OCP.TopExp import TopExp
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopTools import TopTools_IndexedMapOfShape
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS
        shape = box()
        BRepMesh_IncrementalMesh(shape, .01, False, .2, False)
        matrix = (-1, 0, 0, 100, 0, 2, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
        doc, revision, _ = document(shape, matrix)
        def state(native, _):
            faces = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(native, TopAbs_FACE, faces)
            values = []
            for i in range(1, faces.Extent() + 1):
                mesh = BRep_Tool.Triangulation_s(TopoDS.Face_s(faces.FindKey(i)), TopLoc_Location())
                values.append((mesh.NbTriangles(), mesh.Deflection(), tuple(mesh.Node(j).Coord() for j in range(1, mesh.NbNodes() + 1))))
            return (native.Location().IsIdentity(), values)
        with RevisionConsumer(doc, revision.revision_id) as consumer:
            path = consumer.occurrences()[0].path
            before = consumer.query_value(path, state)
            allocations = len(doc._allocations)
            refs = (reference(consumer, path), reference(consumer, path, "face", 0), reference(consumer, path, "edge", 0))
            inspect_batch(consumer, refs)
            self.assertEqual(before, consumer.query_value(path, state))
            self.assertEqual(allocations, len(doc._allocations))

    def test_batch_limits_deduplication_and_cancellation(self):
        from cadgen._document import inspection
        doc, revision, _ = document(box())
        event = Event()
        with RevisionConsumer(doc, revision.revision_id, cancellation=event) as consumer:
            path = consumer.occurrences()[0].path
            a, b = reference(consumer, path), reference(consumer, path, "face", 0)
            with patch.object(inspection, "_facts", wraps=inspection._facts) as compute:
                facts = inspect_batch(consumer, (a, b, a))
                self.assertEqual(2, compute.call_count)
                self.assertIs(facts[0], facts[2])
            with patch.object(consumer, "query_value", side_effect=AssertionError("oversized batch executed")):
                for requests in ((a,) * 65, [], ()):
                    with self.assertRaises(ValueError):
                        inspect_batch(consumer, requests)
            original = inspection._facts
            def cancel_after_first(*args):
                result = original(*args)
                event.set()
                return result
            with patch.object(inspection, "_facts", side_effect=cancel_after_first):
                with self.assertRaises(Cancelled):
                    inspect_batch(consumer, (a, b))
            self.assertEqual(1, consumer.metrics.cancelled)
