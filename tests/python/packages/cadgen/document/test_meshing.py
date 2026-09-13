"""Native quality, isolation and packed transport checks on real geometry."""
import json
import math
import struct
import unittest
from unittest.mock import patch

from cadgen._document import Document, GeometryLeaf, AssemblyGroup, IDENTITY_TRANSFORM
from cadgen._document.core import OperatorSpec, Mutation
from cadgen._document.consumers import RevisionConsumer
from cadgen._document.meshing import MeshOptions, _mesh_private, mesh_for_occurrence, unpack_mesh
from cadgen._document.native import NativeResult


def decoded(packet):
    header, views = unpack_mesh(packet)
    values = {name: [v for v, in struct.iter_unpack("<I" if name == "indices" else "<f", data)]
              for name, data in views.items()}
    points = [tuple(values["positions"][i + axis] + header["origin"][axis] for axis in range(3))
              for i in range(0, len(values["positions"]), 3)]
    return header, values, points


def replace_header(packet, change):
    size, = struct.unpack_from("<I", packet, 8)
    body = packet[12 + size + (-size) % 4:]
    header = json.loads(packet[12:12 + size])
    change(header)
    encoded = json.dumps(header, separators=(",", ":")).encode()
    return packet[:8] + struct.pack("<I", len(encoded)) + encoded + b" " * ((-len(encoded)) % 4) + body


def assert_closed_oriented(test, header, values, points):
    diagonal = math.dist(header["bounds"]["min"], header["bounds"]["max"])
    epsilon = max(diagonal * 2 ** -20, 1e-9)
    welded = {}
    for offset in range(0, len(values["indices"]), 3):
        ids = values["indices"][offset:offset + 3]
        a, b, c = (points[index] for index in ids)
        u = tuple(b[axis] - a[axis] for axis in range(3))
        v = tuple(c[axis] - a[axis] for axis in range(3))
        cross = (u[1] * v[2] - u[2] * v[1],
                 u[2] * v[0] - u[0] * v[2],
                 u[0] * v[1] - u[1] * v[0])
        test.assertGreater(sum(value * value for value in cross), 0)
        normal = tuple(sum(values["normals"][index * 3 + axis] for index in ids)
                       for axis in range(3))
        test.assertGreater(sum(cross[axis] * normal[axis] for axis in range(3)), 0)
        keys = [tuple(round(value / epsilon) for value in point) for point in (a, b, c)]
        for first, second in ((keys[0], keys[1]), (keys[1], keys[2]), (keys[2], keys[0])):
            edge = (first, second) if first < second else (second, first)
            row = welded.setdefault(edge, [0, 0])
            row[0] += 1
            row[1] += 1 if first < second else -1
    test.assertTrue(welded)
    test.assertTrue(all(row == [2, 0] for row in welded.values()))


class MeshingTests(unittest.TestCase):
    def test_copy_reordering_preserves_source_face_and_edge_references(self):
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.TopoDS import TopoDS_Compound, TopoDS_Iterator
        from OCP.gp import gp_Pnt
        from cadgen._document.inspection import _bounds, _map

        builder = BRep_Builder()
        native = TopoDS_Compound(); builder.MakeCompound(native)
        builder.Add(native, BRepPrimAPI_MakeBox(2., 3., 4.).Shape())
        builder.Add(native, BRepPrimAPI_MakeBox(gp_Pnt(10., 0., 0.), 5., 6., 7.).Shape())
        document = Document("mesh-copy-order")
        with document.begin() as transaction:
            handle = transaction.evaluate(OperatorSpec("two-boxes", mutation=Mutation.READ_ONLY),
                                          (), (), lambda *_: NativeResult(native))
            transaction.bind_root(GeometryLeaf("part", handle))
            revision = transaction.commit()

        permutations = []
        def reordered(*args):
            copier = BRepBuilderAPI_Copy(*args)
            iterator = TopoDS_Iterator(copier.Shape()); children = []
            while iterator.More():
                children.append(iterator.Value()); iterator.Next()
            private = TopoDS_Compound(); builder.MakeCompound(private)
            for child in reversed(children):
                builder.Add(private, child)
            faces = _map(private, "face")
            original = _map(args[0], "face")
            permutations.append(tuple(faces.FindIndex(copier.ModifiedShape(original.FindKey(i))) - 1
                                      for i in range(1, original.Extent() + 1)))
            class Copy:
                def Shape(self): return private
                def ModifiedShape(self, shape): return copier.ModifiedShape(shape)
            return Copy()

        with RevisionConsumer(document, revision.revision_id) as consumer:
            path = consumer.occurrences()[0].path
            def source_bounds(shape, _):
                result = {}
                for kind in ("face", "edge"):
                    mapping = _map(shape, kind)
                    result[kind] = [_bounds(mapping.FindKey(i)) for i in range(1, mapping.Extent() + 1)]
                return result
            expected = consumer.query_value(path, source_bounds)
            with patch("OCP.BRepBuilderAPI.BRepBuilderAPI_Copy", side_effect=reordered):
                header, values, points = decoded(mesh_for_occurrence(consumer, path))
            edge_points = [tuple(values["edgePositions"][i + axis] + header["origin"][axis]
                                 for axis in range(3))
                           for i in range(0, len(values["edgePositions"]), 3)]
            self.assertEqual([tuple(range(6, 12)) + tuple(range(6))], permutations)
            for kind, ranges, coordinates in (("face", header["faces"], points),
                                               ("edge", header["edges"], edge_points)):
                self.assertEqual(len(expected[kind]), len(ranges))
                for row in ranges:
                    ordinal, first, count = row[:3]
                    samples = coordinates[first:first + count]
                    actual = (tuple(min(point[axis] for point in samples) for axis in range(3)),
                              tuple(max(point[axis] for point in samples) for axis in range(3)))
                    for bounds, wanted in zip(actual, (expected[kind][ordinal]["min"],
                                                       expected[kind][ordinal]["max"])):
                        for value, target in zip(bounds, wanted):
                            self.assertAlmostEqual(value, target, places=5)
            self.assertEqual(1, consumer.metrics.native_copies)
            with patch("OCP.BRepBuilderAPI.BRepBuilderAPI_Copy", side_effect=AssertionError("warm mesh copied")):
                self.assertEqual(header, decoded(mesh_for_occurrence(consumer, path))[0])

    def test_ambiguous_copy_correspondence_never_publishes_mesh(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
        from cadgen._document.inspection import _map

        document = Document("ambiguous-mesh-copy")
        with document.begin() as transaction:
            handle = transaction.evaluate(OperatorSpec("box", mutation=Mutation.READ_ONLY),
                                          (), (), lambda *_: NativeResult(BRepPrimAPI_MakeBox(2., 3., 4.).Shape()))
            transaction.bind_root(GeometryLeaf("part", handle))
            revision = transaction.commit()
        def merged(*args):
            copier = BRepBuilderAPI_Copy(*args)
            first = _map(copier.Shape(), "face").FindKey(1)
            class Copy:
                def Shape(self): return copier.Shape()
                def ModifiedShape(self, shape): return first
            return Copy()
        with RevisionConsumer(document, revision.revision_id) as consumer:
            with patch("OCP.BRepBuilderAPI.BRepBuilderAPI_Copy", side_effect=merged):
                with self.assertRaisesRegex(ValueError, "complete topology correspondence"):
                    mesh_for_occurrence(consumer, consumer.occurrences()[0].path)
            self.assertEqual(0, consumer.metrics.derivations_computed)
            self.assertEqual({}, document._derivations)

    def test_reordered_shared_reversed_members_keep_source_orientation(self):
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.TopoDS import TopoDS_Compound, TopoDS_Iterator
        from cadgen._document.native import copy_shape

        builder = BRep_Builder()
        native = TopoDS_Compound(); builder.MakeCompound(native)
        box = BRepPrimAPI_MakeBox(2., 3., 4.).Shape()
        builder.Add(native, box); builder.Add(native, box.Reversed())
        expected_header, expected, _ = decoded(_mesh_private(copy_shape(native), MeshOptions()))
        document = Document("mesh-reversed-member-copy")
        with document.begin() as transaction:
            handle = transaction.evaluate(OperatorSpec("shared-reversed-box", mutation=Mutation.READ_ONLY),
                                          (), (), lambda *_: NativeResult(native))
            transaction.bind_root(GeometryLeaf("part", handle))
            revision = transaction.commit()
        def reordered(*args):
            copier = BRepBuilderAPI_Copy(*args)
            iterator = TopoDS_Iterator(copier.Shape()); children = []
            while iterator.More():
                children.append(iterator.Value()); iterator.Next()
            private = TopoDS_Compound(); builder.MakeCompound(private)
            for child in reversed(children):
                builder.Add(private, child)
            class Copy:
                def Shape(self): return private
                def ModifiedShape(self, shape): return copier.ModifiedShape(shape)
            return Copy()
        with RevisionConsumer(document, revision.revision_id) as consumer:
            with patch("OCP.BRepBuilderAPI.BRepBuilderAPI_Copy", side_effect=reordered):
                header, actual, _ = decoded(mesh_for_occurrence(consumer, consumer.occurrences()[0].path))
        self.assertEqual(expected_header["faces"], header["faces"])
        self.assertEqual(expected["normals"], actual["normals"])
        self.assertEqual(expected["indices"], actual["indices"])

    def test_box_has_all_faces_outward_normals_and_separate_sharp_edges(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

        header, values, points = decoded(_mesh_private(BRepPrimAPI_MakeBox(10., 20., 30.).Shape(), MeshOptions()))
        self.assertEqual(6, len(header["faces"]))
        self.assertEqual(12, len(header["edges"]))
        self.assertEqual({"sharp"}, {row[-1] for row in header["edges"]})
        self.assertEqual(36, len(values["indices"]))
        center = (5., 10., 15.)
        for index, point in enumerate(points):
            normal = values["normals"][index * 3:index * 3 + 3]
            self.assertAlmostEqual(1, math.sqrt(sum(v * v for v in normal)), places=6)
            self.assertGreater(sum((point[a] - center[a]) * normal[a] for a in range(3)), 0)
        for offset in range(0, len(values["indices"]), 3):
            a, b, c = (points[v] for v in values["indices"][offset:offset + 3])
            u, v = ([b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)])
            cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            self.assertGreater(sum(cross[i] * (a[i] - center[i]) for i in range(3)), 0)

    def test_cylinder_sphere_torus_cover_seams_poles_and_quality(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeSphere, BRepPrimAPI_MakeTorus

        for name, factory, distance in (
            ("cylinder", lambda: BRepPrimAPI_MakeCylinder(10., 20.).Shape(), None),
            ("sphere", lambda: BRepPrimAPI_MakeSphere(10.).Shape(), lambda p: abs(math.sqrt(sum(v*v for v in p)) - 10)),
            ("torus", lambda: BRepPrimAPI_MakeTorus(10., 3.).Shape(), lambda p: abs(math.hypot(math.hypot(p[0], p[1]) - 10, p[2]) - 3))):
            with self.subTest(name=name):
                coarse, _, _ = decoded(_mesh_private(factory(), MeshOptions(.004, .5)))
                fine, values, points = decoded(_mesh_private(factory(), MeshOptions(.0003, .15)))
                self.assertGreater(fine["buffers"]["indices"]["count"], coarse["buffers"]["indices"]["count"])
                self.assertIn("seam", {row[-1] for row in fine["edges"]})
                if distance:
                    self.assertLess(max(map(distance, points)), 2e-5)
                    max_error = 0
                    for i in range(0, len(values["indices"]), 3):
                        vertices = [points[k] for k in values["indices"][i:i+3]]
                        centroid = [sum(p[a] for p in vertices) / 3 for a in range(3)]
                        max_error = max(max_error, distance(centroid))
                    # This is a sampled analytic-surface error, not proof of a
                    # global Hausdorff bound. Keep the evidence named honestly.
                    self.assertLess(max_error, fine["linearDeflection"] * 1.5)
                for i in range(0, len(values["normals"]), 3):
                    self.assertAlmostEqual(1, math.sqrt(sum(v*v for v in values["normals"][i:i+3])), places=5)
                assert_closed_oriented(self, fine, values, points)
                if name == "sphere":
                    self.assertGreater(fine["discardedZeroAreaTriangles"], 0)

    def test_prototype_derived_once_across_24_occurrences_and_placement_edits(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
        from OCP.BRep import BRep_Tool
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS

        document = Document("meshing")
        meshes = []
        for shift in (0., 5.):
            with document.begin() as tx:
                handle = tx.evaluate(OperatorSpec("cylinder", mutation=Mutation.READ_ONLY), (10., 20.), (),
                                     lambda *_: NativeResult(BRepPrimAPI_MakeCylinder(10., 20.).Shape()))
                leaves = []
                for index in range(24):
                    transform = list(IDENTITY_TRANSFORM)
                    transform[3] = index * 25 + shift
                    leaves.append(GeometryLeaf(str(index), handle, tuple(transform), appearance={"color": (shift / 10, .2, .4)}))
                tx.bind_root(AssemblyGroup("root", tuple(leaves)))
                revision = tx.commit()
            with RevisionConsumer(document, revision.revision_id) as consumer:
                for occurrence in consumer.occurrences():
                    meshes.append(mesh_for_occurrence(consumer, occurrence.path))
                self.assertEqual(int(shift == 0), consumer.metrics.derivations_computed)
                self.assertEqual(23 if shift == 0 else 24, consumer.metrics.derivations_reused)
                def has_mesh(shape, _):
                    face = TopoDS.Face_s(TopExp_Explorer(shape, TopAbs_FACE).Current())
                    return BRep_Tool.Triangulation_s(face, TopLoc_Location()) is not None
                self.assertFalse(consumer.query_value(consumer.occurrences()[0].path, has_mesh))
        self.assertTrue(all(payload is meshes[0] for payload in meshes))

    def test_large_origin_retains_small_feature_precision_and_optional_edges(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.gp import gp_Pnt

        header, _, points = decoded(_mesh_private(BRepPrimAPI_MakeBox(gp_Pnt(1e9, 1e9, 1e9), .01, .02, .03).Shape(), MeshOptions(edges=False)))
        self.assertEqual([], header["edges"])
        self.assertEqual(0, header["buffers"]["edgePositions"]["count"])
        for axis, size in enumerate((.01, .02, .03)):
            self.assertAlmostEqual(size, max(p[axis] for p in points) - min(p[axis] for p in points), places=6)

    def test_corrupt_or_incomplete_transfer_rejected_before_exposing_views(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

        packet = _mesh_private(BRepPrimAPI_MakeBox(1., 2., 3.).Shape(), MeshOptions())
        mutations = [
            lambda h: h.update(version=99),
            lambda h: h.update(discardedZeroAreaTriangles=-1),
            lambda h: h.update(linearDeflection=float("nan")),
            lambda h: h["options"].update(angular=True),
            lambda h: h["options"].update(edges=1),
            lambda h: h["buffers"]["normals"].update(offset=0),
            lambda h: h["faces"].pop(),
            lambda h: h["edges"][0].__setitem__(3, "unknown"),
            lambda h: h["origin"].__setitem__(0, float("nan")),
        ]
        for mutate in mutations:
            with self.assertRaises(ValueError):
                unpack_mesh(replace_header(packet, mutate))
        for corrupt in (b"", packet[:-1], packet + b"x", b"unsupported" + packet[11:]):
            with self.assertRaises(ValueError):
                unpack_mesh(corrupt)
        header, views = unpack_mesh(packet)
        self.assertTrue(all(view.readonly for view in views.values()))

    def test_options_reject_unbounded_or_invalid_quality(self):
        for kwargs in ({"angular": 0}, {"angular": float("nan")}, {"relative_chord": True},
                       {"relative_chord": 2}, {"edges": 1}):
            with self.assertRaises((ValueError, TypeError)):
                MeshOptions(**kwargs)

    def test_reversed_and_mirrored_locations_preserve_winding_normal_agreement(self):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf

        mirror = gp_Trsf()
        mirror.SetMirror(gp_Ax2(gp_Pnt(), gp_Dir(1, 0, 0)))
        for reverse in (False, True):
            for placement in ("identity", "mirrored-location", "mirrored-geometry"):
                with self.subTest(reverse=reverse, placement=placement):
                    shape = BRepPrimAPI_MakeBox(10., 20., 30.).Shape()
                    if placement == "mirrored-location":
                        shape = shape.Moved(TopLoc_Location(mirror), False)
                    elif placement == "mirrored-geometry":
                        shape = BRepBuilderAPI_Transform(shape, mirror, True).Shape()
                    if reverse:
                        shape = shape.Reversed()
                    _, values, points = decoded(_mesh_private(shape, MeshOptions()))
                    center = (-5. if placement != "identity" else 5., 10., 15.)
                    for offset in range(0, len(values["indices"]), 3):
                        ids = values["indices"][offset:offset + 3]
                        a, b, c = (points[i] for i in ids)
                        u, v = ([b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)])
                        cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
                        for index in ids:
                            normal = values["normals"][index * 3:index * 3 + 3]
                            self.assertGreater(sum(cross[i]*normal[i] for i in range(3)), 0)
                            self.assertGreater(sum((a[i]-center[i])*normal[i] for i in range(3))
                                               * (-1 if reverse else 1), 0)

    def test_free_boundary_and_nonmanifold_edges_are_distinguished(self):
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
        from OCP.TopoDS import TopoDS_Compound
        from OCP.gp import gp_Pnt

        a, b = gp_Pnt(0, 0, 0), gp_Pnt(10, 0, 0)
        common = BRepBuilderAPI_MakeEdge(a, b).Edge()
        compound, builder = TopoDS_Compound(), BRep_Builder()
        builder.MakeCompound(compound)
        for c in (gp_Pnt(0, 5, 0), gp_Pnt(0, 0, 5), gp_Pnt(0, -5, 0)):
            wire = BRepBuilderAPI_MakeWire(common, BRepBuilderAPI_MakeEdge(b, c).Edge(),
                                           BRepBuilderAPI_MakeEdge(c, a).Edge()).Wire()
            builder.Add(compound, BRepBuilderAPI_MakeFace(wire).Face())
        builder.Add(compound, BRepBuilderAPI_MakeEdge(gp_Pnt(20, 0, 0), gp_Pnt(21, 0, 0)).Edge())
        header, _, _ = decoded(_mesh_private(compound, MeshOptions()))
        kinds = [row[-1] for row in header["edges"]]
        self.assertEqual(1, kinds.count("nonmanifold"))
        self.assertEqual(1, kinds.count("free"))
        self.assertEqual(6, kinds.count("boundary"))

    def test_trimmed_cut_fillets_sample_exact_face_error_without_mutating_prototype(self):
        from OCP.BRep import BRep_Tool
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        from OCP.TopExp import TopExp, TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopTools import TopTools_IndexedMapOfShape
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

        box = BRepPrimAPI_MakeBox(20., 15., 10.).Shape()
        fillet = BRepFilletAPI_MakeFillet(box)
        explorer = TopExp_Explorer(box, TopAbs_EDGE)
        while explorer.More():
            fillet.Add(1., TopoDS.Edge_s(explorer.Current()))
            explorer.Next()
        fillet.Build()
        self.assertTrue(fillet.IsDone())
        # A side-opening cut trims planar, cylindrical and rounded faces.
        tool = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(2, 7, -2), gp_Dir(0, 0, 1)), 4., 14.).Shape()
        cut = BRepAlgoAPI_Cut(fillet.Shape(), tool)
        self.assertTrue(cut.IsDone())
        shape = cut.Shape()
        faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
        self.assertGreater(faces.Extent(), 20)
        document = Document("trimmed-quality")
        with document.begin() as tx:
            handle = tx.evaluate(OperatorSpec("trimmed-fixture", mutation=Mutation.READ_ONLY), (), (),
                                 lambda *_: NativeResult(shape))
            tx.bind_root(GeometryLeaf("root", handle))
            revision = tx.commit()
        def triangulations(native, _):
            native_faces = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(native, TopAbs_FACE, native_faces)
            return tuple(BRep_Tool.Triangulation_s(TopoDS.Face_s(native_faces.FindKey(i)), TopLoc_Location()) is None
                         for i in range(1, native_faces.Extent() + 1))
        errors, counts = [], []
        with RevisionConsumer(document, revision.revision_id) as consumer:
            path = consumer.occurrences()[0].path
            before = consumer.query_value(path, triangulations)
            self.assertTrue(all(before))
            # Hold angular tolerance fixed to exercise the linear control.
            for options in (MeshOptions(.004, .5, False), MeshOptions(.0001, .5, False)):
                header, values, points = decoded(mesh_for_occurrence(consumer, path, options))
                assert_closed_oriented(self, header, values, points)
                error = 0.
                for ordinal, _, _, start, count in header["faces"]:
                    face = TopoDS.Face_s(faces.FindKey(ordinal + 1))
                    for offset in range(start, start + count, max(1, (count // 3) // 8) * 3):
                        triangle = [points[i] for i in values["indices"][offset:offset + 3]]
                        centroid = [sum(p[a] for p in triangle) / 3 for a in range(3)]
                        distance = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(*centroid)).Vertex(), face)
                        self.assertTrue(distance.IsDone())
                        error = max(error, distance.Value())
                # Sampled distances to each actual trimmed native face. This
                # checks this fixture; it does not assert a global error bound.
                self.assertLess(error, header["linearDeflection"])
                errors.append(error)
                counts.append(len(values["indices"]))
            self.assertEqual(before, consumer.query_value(path, triangulations))
        self.assertLess(errors[1], errors[0] / 2)
        self.assertGreater(counts[1], counts[0])

    def test_cancel_during_vertex_loop_does_not_cache_partial_data(self):
        from array import array
        from unittest.mock import patch
        from threading import Event
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
        from cadgen._document.resources import Cancelled

        document = Document("cancel-mesh")
        with document.begin() as tx:
            handle = tx.evaluate(OperatorSpec("sphere", mutation=Mutation.READ_ONLY), (), (),
                                 lambda *_: NativeResult(BRepPrimAPI_MakeSphere(10.).Shape()))
            tx.bind_root(GeometryLeaf("root", handle))
            revision = tx.commit()
        cancellation = Event()
        lengths = []
        class CancelDuringAppend(array):
            def extend(self, values):
                super().extend(values)
                lengths.append(len(self))
                if len(self) >= 3000:
                    cancellation.set()
        with RevisionConsumer(document, revision.revision_id, cancellation=cancellation) as consumer:
            path = consumer.occurrences()[0].path
            with patch("cadgen._document.meshing.array", CancelDuringAppend), \
                 patch("cadgen._document.meshing._pack", side_effect=AssertionError("cancelled arrays reached packing")):
                with self.assertRaises(Cancelled):
                    mesh_for_occurrence(consumer, path, MeshOptions(.0001, .1))
            self.assertLessEqual(max(lengths), 3072)
            self.assertEqual(1, consumer.metrics.cancelled)
            self.assertEqual(0, consumer.metrics.derivations_computed)
        with RevisionConsumer(document, revision.revision_id) as consumer:
            mesh_for_occurrence(consumer, consumer.occurrences()[0].path, MeshOptions(.0001, .1))
            self.assertEqual(1, consumer.metrics.derivations_computed)

    def test_output_limit_is_checked_before_filling_a_face(self):
        from array import array
        from unittest.mock import patch
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

        class NoAppend(array):
            def extend(self, values):
                raise AssertionError("oversized face allocated before limit check")
        with patch("cadgen._document.meshing.array", NoAppend), \
             patch("cadgen._document.meshing.MAX_PACKET_BYTES", 64):
            with self.assertRaisesRegex(ValueError, "transfer limit"):
                _mesh_private(BRepPrimAPI_MakeBox(1., 2., 3.).Shape(), MeshOptions())

    def test_huge_ranges_and_invalid_point_counts_reject_without_iteration(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

        packet = _mesh_private(BRepPrimAPI_MakeBox(1., 2., 3.).Shape(), MeshOptions())
        for change in (
            lambda h: h["faces"][0].__setitem__(4, 9_000_000_000_000_000),
            lambda h: h["faces"][0].__setitem__(2, 9_000_000_000_000_000),
            lambda h: h["faces"][0].__setitem__(4, 0),
            lambda h: h["edges"][0].__setitem__(3, "degenerate"),
            lambda h: h["edges"][0].__setitem__(2, 1),
        ):
            with self.assertRaises(ValueError):
                unpack_mesh(replace_header(packet, change))

    def test_existing_prototype_triangulation_survives_finer_derivation(self):
        from OCP.BRep import BRep_Tool
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS

        shape = BRepPrimAPI_MakeSphere(10.).Shape()
        _mesh_private(shape, MeshOptions(.01, .6))
        document = Document("premeshed-prototype")
        with document.begin() as tx:
            handle = tx.evaluate(OperatorSpec("premeshed", mutation=Mutation.READ_ONLY), (), (),
                                 lambda *_: NativeResult(shape))
            tx.bind_root(GeometryLeaf("root", handle))
            revision = tx.commit()
        def state(native, _):
            face = TopoDS.Face_s(TopExp_Explorer(native, TopAbs_FACE).Current())
            mesh = BRep_Tool.Triangulation_s(face, TopLoc_Location())
            return (mesh.NbTriangles(), mesh.Deflection(),
                    tuple(mesh.Node(i).Coord() for i in range(1, mesh.NbNodes() + 1)),
                    tuple(mesh.Normal(i).Coord() for i in range(1, mesh.NbNodes() + 1)))
        with RevisionConsumer(document, revision.revision_id) as consumer:
            path = consumer.occurrences()[0].path
            before = consumer.query_value(path, state)
            header, _ = unpack_mesh(mesh_for_occurrence(consumer, path, MeshOptions(.0001, .1)))
            self.assertGreater(header["buffers"]["indices"]["count"] // 3, before[0])
            self.assertEqual(before, consumer.query_value(path, state))
