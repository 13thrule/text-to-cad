"""Pinned revision consumers over real native prototypes and root metadata."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from threading import Event, Thread, get_ident
from types import MappingProxyType
import unittest

from cadgen._document import (AssemblyGroup, Document, GeometryLeaf,
                              IDENTITY_TRANSFORM, ResourceAdmission,
                              ResourceRequest)
from cadgen._document.consumers import (AmbiguousOccurrencePath, RevisionConsumer,
                                        StaleOccurrencePath)
from cadgen._document.identities import normalize
from cadgen._document.resources import AdmissionDenied, Cancelled


def translated(x=0., y=0., z=0.):
    result = list(IDENTITY_TRANSFORM)
    result[3], result[7], result[11] = x, y, z
    return tuple(result)


def native_plate():
    """A small valid through-holed plate with real OCCT fillets."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    box = BRepPrimAPI_MakeBox(20., 12., 2.).Shape()
    fillet = BRepFilletAPI_MakeFillet(box)
    edges = TopExp_Explorer(box, TopAbs_EDGE)
    selected = []
    while edges.More():
        edge = TopoDS.Edge_s(edges.Current())
        curve = BRepAdaptor_Curve(edge)
        first = curve.Value(curve.FirstParameter())
        last = curve.Value(curve.LastParameter())
        if (abs(first.X() - last.X()) < 1e-8
                and abs(first.Y() - last.Y()) < 1e-8
                and abs(first.Z() - last.Z()) > 1.9
                and not any(edge.IsSame(other) for other in selected)):
            fillet.Add(.6, edge)
            selected.append(edge)
        edges.Next()
    if len(selected) != 4:
        raise AssertionError(f"expected four vertical plate edges, found {len(selected)}")
    fillet.Build()
    if not fillet.IsDone():
        raise AssertionError("plate fillet failed")
    hole = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(10., 6., -1.), gp_Dir(0., 0., 1.)), 2., 4.).Shape()
    cut = BRepAlgoAPI_Cut(fillet.Shape(), hole)
    cut.SetNonDestructive(True)
    cut.Build()
    if not cut.IsDone() or not BRepCheck_Analyzer(cut.Shape()).IsValid():
        raise AssertionError("plate through-hole failed")
    return cut.Shape()


def assembly_root(handle, *, first_z=0., color=(.8, .8, .8)):
    shared_leaf = GeometryLeaf("plate", handle, translated(1., 2.),
                               label="plate", appearance={"color": color})
    slots = []
    for index in range(24):
        row, column = divmod(index, 6)
        slots.append(AssemblyGroup(
            f"slot-{index:02d}", (shared_leaf,),
            translated(column * 30., row * 20., first_z if index == 0 else 0.),
            label=f"occurrence {index + 1}"))
    return AssemblyGroup("assembly", tuple(slots), translated(3., 4., 5.))


def mesh_summary(shape):
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    BRepMesh_IncrementalMesh(shape, .15, False, .3, False)
    face_triangles = []
    faces = TopExp_Explorer(shape, TopAbs_FACE)
    while faces.More():
        triangulation = BRep_Tool.Triangulation_s(
            TopoDS.Face_s(faces.Current()), TopLoc_Location())
        face_triangles.append(triangulation.NbTriangles())
        faces.Next()
    return {"triangles": sum(face_triangles), "byFace": face_triangles}


def has_triangulation(shape, transform):
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    faces = TopExp_Explorer(shape, TopAbs_FACE)
    while faces.More():
        if BRep_Tool.Triangulation_s(
                TopoDS.Face_s(faces.Current()), TopLoc_Location()) is not None:
            return True
        faces.Next()
    return False


def transformed_bounds(shape, transform):
    """Exact native local bounds plus an independently applied root matrix."""
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box

    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, bounds, False, False)
    xmin, ymin, zmin, xmax, ymax, zmax = bounds.Get()
    points = []
    for x in (xmin, xmax):
        for y in (ymin, ymax):
            for z in (zmin, zmax):
                points.append(tuple(
                    transform[row * 4] * x + transform[row * 4 + 1] * y
                    + transform[row * 4 + 2] * z + transform[row * 4 + 3]
                    for row in range(3)))
    return (min(p[0] for p in points), min(p[1] for p in points),
            min(p[2] for p in points), max(p[0] for p in points),
            max(p[1] for p in points), max(p[2] for p in points))


class RevisionConsumerTests(unittest.TestCase):
    def test_real_plate_24_instances_reuse_one_mesh_across_scene_only_edits(self):
        document = Document("consumer-assembly", runtime={"occt": "test-runtime"})
        with document.begin("geometry") as tx:
            prototype = tx.capture(native_plate())
            tx.bind_root(assembly_root(prototype))
            first = tx.commit()

        mesh_calls = []
        first_consumer = RevisionConsumer(document, first.revision_id)
        first_occurrences = first_consumer.occurrences()
        self.assertEqual(24, len(first_occurrences))
        self.assertEqual(1, len({occ.prototype_id for occ in first_occurrences}))
        for occurrence in first_occurrences:
            mesh = first_consumer.derive(
                occurrence.path, "occt-mesh", {"linear": .15, "angular": .3},
                lambda shape: mesh_calls.append(get_ident()) or mesh_summary(shape))
            self.assertGreater(mesh["triangles"], 0)
            self.assertIsInstance(mesh, MappingProxyType)
            self.assertIsInstance(mesh["byFace"], tuple)
        self.assertEqual([get_ident()], mesh_calls)
        self.assertEqual((1, 23, 1),
                         (first_consumer.metrics.derivations_computed,
                          first_consumer.metrics.derivations_reused,
                          first_consumer.metrics.native_copies))
        self.assertFalse(first_consumer.query_value(
            first_occurrences[0].path, has_triangulation))

        with document.begin("placement edit") as tx:
            tx.bind_root(assembly_root(prototype, first_z=7.))
            second = tx.commit()
        document.collect(keep_revisions=0)
        self.assertEqual(first.revision_id, first_consumer.revision_id)
        second_consumer = RevisionConsumer(document, second.revision_id)
        with self.assertRaises(StaleOccurrencePath):
            second_consumer.query_value(first_occurrences[0].path, has_triangulation)
        second_occurrences = second_consumer.occurrences()
        self.assertEqual(first_occurrences[0].prototype_id,
                         second_occurrences[0].prototype_id)
        for occurrence in second_occurrences:
            second_consumer.derive(
                occurrence.path, "occt-mesh", {"angular": .3, "linear": .15},
                lambda shape: mesh_calls.append(get_ident()) or mesh_summary(shape))
        self.assertEqual(1, len(mesh_calls))
        self.assertEqual((0, 24, 0),
                         (second_consumer.metrics.derivations_computed,
                          second_consumer.metrics.derivations_reused,
                          second_consumer.metrics.native_copies))

        last = second_consumer.occurrence(("assembly", "slot-23", "plate"))
        actual = second_consumer.query_value(last.path, transformed_bounds)
        expected = (154., 66., 5., 174., 78., 7.)
        for observed, wanted in zip(actual, expected):
            self.assertAlmostEqual(wanted, observed, places=6)
        moved = second_consumer.occurrence(("assembly", "slot-00", "plate"))
        moved_bounds = second_consumer.query_value(moved.path, transformed_bounds)
        self.assertAlmostEqual(12., moved_bounds[2], places=6)

        first_consumer.close()
        document.collect(keep_revisions=0)
        with self.assertRaises(KeyError):
            RevisionConsumer(document, first.revision_id)

        with document.begin("material edit") as tx:
            tx.bind_root(assembly_root(prototype, first_z=7., color=(1., 0., 0.)))
            third = tx.commit()
        third_consumer = RevisionConsumer(document, third.revision_id)
        self.assertEqual(second_occurrences[0].prototype_id,
                         third_consumer.occurrences()[0].prototype_id)
        for occurrence in third_consumer.occurrences():
            third_consumer.derive(
                occurrence.path, "occt-mesh", {"linear": .15, "angular": .3},
                lambda shape: mesh_calls.append(get_ident()) or mesh_summary(shape))
        self.assertEqual(1, len(mesh_calls))
        self.assertEqual((0, 24, 0),
                         (third_consumer.metrics.derivations_computed,
                          third_consumer.metrics.derivations_reused,
                          third_consumer.metrics.native_copies))
        self.assertEqual(1, len(document._derivations))
        cache_key = next(iter(document._derivations))
        self.assertEqual(prototype.prototype_id, cache_key[0])
        self.assertEqual(normalize(document.runtime), cache_key[-1])
        self.assertEqual((1., 0., 0.),
                         third_consumer.occurrences()[0].appearance["color"])
        third_consumer.derive(
            third_consumer.occurrences()[0].path, "occt-mesh",
            {"linear": .2, "angular": .3},
            lambda shape: mesh_calls.append(get_ident()) or mesh_summary(shape))
        self.assertEqual(2, len(mesh_calls))
        self.assertEqual(2, len(document._derivations))
        second_consumer.close()
        third_consumer.close()

    def test_results_are_value_only_immutable_and_native_work_is_owner_thread(self):
        document = Document("consumer-values")
        with document.begin() as tx:
            prototype = tx.capture(native_plate())
            tx.bind_root(GeometryLeaf("plate", prototype, appearance={"color": [1., 0., 0.]}))
            revision = tx.commit()
        with RevisionConsumer(document, revision.revision_id) as consumer:
            occurrence = consumer.occurrences()[0]
            result = consumer.query_value(
                occurrence.path,
                lambda shape, transform: {"bounds": list(transformed_bounds(shape, transform))})
            self.assertIsInstance(result, MappingProxyType)
            self.assertIsInstance(result["bounds"], tuple)
            with self.assertRaises(TypeError):
                result["bounds"] = ()
            with self.assertRaises(FrozenInstanceError):
                occurrence.label = "changed"
            with self.assertRaises(TypeError):
                consumer.query_value(occurrence.path, lambda shape, transform: shape)

            failures = []
            thread = Thread(target=lambda: self._capture_failure(
                failures, lambda: consumer.query_value(occurrence.path, has_triangulation)))
            thread.start()
            thread.join()
            self.assertEqual(1, len(failures))
            self.assertIsInstance(failures[0], RuntimeError)
            self.assertIn("owning thread", str(failures[0]))

    @staticmethod
    def _capture_failure(failures, callback):
        try:
            callback()
        except BaseException as exc:
            failures.append(exc)

    def test_cancellation_and_admission_fail_without_callback_or_reservation_leak(self):
        admission = ResourceAdmission(derived_bytes=0)
        document = Document("consumer-admission", admission=admission)
        with document.begin() as tx:
            prototype = tx.capture(native_plate())
            tx.bind_root(GeometryLeaf("plate", prototype))
            revision = tx.commit()
        cancellation = Event()
        consumer = RevisionConsumer(document, revision.revision_id,
                                    cancellation=cancellation)
        occurrence = consumer.occurrences()[0]
        callbacks = []
        with self.assertRaises(AdmissionDenied):
            consumer.derive(
                occurrence.path, "mesh", {}, lambda shape: callbacks.append(shape) or (),
                resources=ResourceRequest(kind="mesh", derived_bytes=1))
        self.assertEqual([], callbacks)
        self.assertEqual((0, 0, 0), admission.used)
        self.assertEqual(1, consumer.metrics.admission_denied)
        cancellation.set()
        with self.assertRaises(Cancelled):
            consumer.query_value(occurrence.path, has_triangulation)
        self.assertEqual(1, consumer.metrics.cancelled)
        consumer.close()

    def test_root_is_sole_scene_authority_and_malformed_duplicate_paths_fail(self):
        document = Document("consumer-root-only")
        with document.begin() as tx:
            tx.capture(native_plate())
            revision = tx.commit()
        with self.assertRaisesRegex(ValueError, "authoritative returned root"):
            RevisionConsumer(document, revision.revision_id)

        malformed = Document("consumer-ambiguous")
        with malformed.begin() as tx:
            prototype = tx.capture(native_plate())
            leaf = GeometryLeaf("plate", prototype)
            root = AssemblyGroup("assembly", (leaf,))
            tx.bind_root(root)
            revision = tx.commit()
        object.__setattr__(root, "children", (leaf, leaf))
        with self.assertRaises(AmbiguousOccurrencePath):
            RevisionConsumer(malformed, revision.revision_id)


if __name__ == "__main__":
    unittest.main()
