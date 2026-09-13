"""Bounded native remeshing, numerical acceptance and producer identity."""
from dataclasses import asdict
import json
import math
from pathlib import Path
import struct
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from cadgen._document import Document, GeometryLeaf, Mutation, NativeResult, OperatorSpec
from cadgen._document import meshing
from cadgen._document.consumers import RevisionConsumer
from cadgen._document.identities import normalize
from cadgen._document.meshing import MeshOptions, _mesh_private, mesh_for_occurrence
from cadgen._document.native import copy_shape
from cadgen._document.inspection import _map
from cadgen._document.resources import Cancelled
from tests.python.packages.cadgen.document.test_meshing import decoded, assert_closed_oriented


def curved():
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeSphere
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    shape = BRepPrimAPI_MakeCylinder(6., 30.).Shape()
    for z in (0., 30.):
        operation = BRepAlgoAPI_Fuse(shape, BRepPrimAPI_MakeSphere(gp_Pnt(0., 0., z), 6.).Shape())
        shape = operation.Shape()
    return BRepAlgoAPI_Cut(shape, BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(-8., 0., 15.), gp_Dir(1., 0., 0.)), 2., 16.).Shape()).Shape()


def source_document(shape):
    document = Document("retry-source")
    with document.begin() as transaction:
        handle = transaction.evaluate(OperatorSpec("retry-fixture", mutation=Mutation.READ_ONLY),
                                      (), (), lambda *_: NativeResult(shape))
        transaction.bind_root(GeometryLeaf("part", handle))
        revision = transaction.commit()
    return document, revision


def observed_mesh(shape, options=MeshOptions()):
    from OCP.BRepMesh import BRepMesh_IncrementalMesh

    calls = []
    def mesh(native, parameters):
        calls.append((int(parameters.MeshAlgo), parameters.Deflection, parameters.Angle))
        return BRepMesh_IncrementalMesh(native, parameters)
    with patch("OCP.BRepMesh.BRepMesh_IncrementalMesh", side_effect=mesh):
        result = _mesh_private(copy_shape(shape), options)
    return result, calls


class NativeMeshRetryTests(unittest.TestCase):
    def assert_sphere_quality(self, packet, radius=10., center=(0., 0., 0.), sign=1):
        header, values, points = decoded(packet)
        assert_closed_oriented(self, header, values, points)
        delta = math.dist(header["bounds"]["min"], header["bounds"]["max"]) * header["options"]["relative_chord"]
        reliable_area = (math.dist(header["bounds"]["min"], header["bounds"]["max"]) * 2 ** -20) ** 2
        maximum_angle = maximum_error = 0.
        for offset in range(0, len(values["indices"]), 3):
            a, b, c = [points[i] for i in values["indices"][offset:offset + 3]]
            u, v = ([b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)])
            cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
            centroid = tuple((a[i] + b[i] + c[i]) / 3 - center[i] for i in range(3))
            length = math.hypot(*cross)
            dot = sign * sum(cross[i] * centroid[i] for i in range(3))
            self.assertGreater(dot, 0.)
            if length > reliable_area:
                maximum_angle = max(maximum_angle, math.acos(min(1., dot / (length * math.hypot(*centroid)))))
            samples = [centroid] + [tuple((x[i] + y[i]) * .5 - center[i] for i in range(3))
                                    for x, y in ((a, b), (b, c), (c, a))]
            maximum_error = max(maximum_error, *(abs(math.hypot(*p) - radius) for p in samples))
        self.assertLessEqual(maximum_angle, header["options"]["angular"])
        self.assertLessEqual(maximum_error, delta)
        return header

    def test_sphere_passes_original_strict_targets_at_three_detail_levels(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere

        for factor in (1., .5, .25):
            with self.subTest(factor=factor):
                options = MeshOptions(.0015 * factor, .35 * math.sqrt(factor))
                packet, calls = observed_mesh(BRepPrimAPI_MakeSphere(10.).Shape(), options)
                self.assertEqual([0, 1], [row[0] for row in calls])
                self.assertAlmostEqual(calls[0][1] * .5, calls[1][1])
                self.assertAlmostEqual(calls[0][2] * math.sqrt(.5), calls[1][2])
                header = self.assert_sphere_quality(packet)
                self.assertEqual(asdict(options), header["options"])
                self.assertEqual({"seam", "degenerate"}, {row[-1] for row in header["edges"]})

    def test_rotated_translated_and_reversed_spheres_keep_orientation(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

        rotation = gp_Trsf(); rotation.SetRotation(gp_Ax1(gp_Pnt(), gp_Dir(1., 2., 3.)), .47)
        translation = gp_Trsf(); translation.SetTranslation(gp_Vec(1000., -2000., 500.))
        transform = translation.Multiplied(rotation)
        for reverse in (False, True):
            shape = BRepPrimAPI_MakeSphere(10.).Shape().Moved(TopLoc_Location(transform))
            if reverse:
                shape = shape.Reversed()
            packet, _ = observed_mesh(shape)
            self.assert_sphere_quality(packet, center=(1000., -2000., 500.), sign=-1 if reverse else 1)

    def test_passing_curved_default_is_not_refined_and_finer_request_is_bounded(self):
        shape = curved()
        coarse, calls = observed_mesh(shape)
        self.assertEqual(1, len(calls))
        options = MeshOptions(.00075, .35 * math.sqrt(.5))
        fine, calls = observed_mesh(shape, options)
        self.assertEqual([0, 1, 1, 1], [row[0] for row in calls])
        coarse_header, coarse_values, _ = decoded(coarse)
        header, values, points = decoded(fine)
        assert_closed_oriented(self, header, values, points)
        self.assertGreater(len(values["indices"]), len(coarse_values["indices"]))
        self.assertEqual(len(coarse_header["faces"]), len(header["faces"]))
        self.assertEqual([row[-1] for row in coarse_header["edges"]], [row[-1] for row in header["edges"]])

    def test_source_triangulation_and_topology_are_unchanged_after_retry(self):
        from OCP.BRep import BRep_Tool
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS

        native = BRepPrimAPI_MakeSphere(10.).Shape()
        BRepMesh_IncrementalMesh(native, .05, False, .35, False)
        face = TopoDS.Face_s(_map(native, "face").FindKey(1))
        triangulation = BRep_Tool.Triangulation_s(face, TopLoc_Location())
        before = tuple(triangulation.Triangle(i).Get() for i in range(1, triangulation.NbTriangles() + 1))
        packet, calls = observed_mesh(native)
        self.assertEqual(2, len(calls))
        self.assertIs(triangulation, BRep_Tool.Triangulation_s(face, TopLoc_Location()))
        self.assertEqual(before, tuple(triangulation.Triangle(i).Get() for i in range(1, triangulation.NbTriangles() + 1)))
        self.assert_sphere_quality(packet)

    def test_retry_preserves_explicit_copy_face_and_edge_order(self):
        from OCP.BRep import BRep_Builder
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere, BRepPrimAPI_MakeBox
        from OCP.TopoDS import TopoDS_Compound
        from OCP.gp import gp_Pnt

        shape, builder = TopoDS_Compound(), BRep_Builder()
        builder.MakeCompound(shape)
        builder.Add(shape, BRepPrimAPI_MakeSphere(10.).Shape())
        builder.Add(shape, BRepPrimAPI_MakeBox(gp_Pnt(20., 0., 0.), 2., 3., 4.).Shape())
        private = copy_shape(shape)
        faces, edges = _map(private, "face"), _map(private, "edge")
        ordered = {"face": tuple(faces.FindKey(i) for i in range(faces.Extent(), 0, -1)),
                   "edge": tuple(edges.FindKey(i) for i in range(edges.Extent(), 0, -1))}
        header, values, points = decoded(_mesh_private(private, MeshOptions(), topology_order=ordered))
        self.assertEqual(7, len(header["faces"]))
        for ordinal, first, count, _, _ in header["faces"]:
            xs = [p[0] for p in points[first:first + count]]
            self.assertTrue(max(xs) <= 10.001 if ordinal == 6 else min(xs) >= 19.999)
        self.assertEqual(["degenerate", "seam", "degenerate"], [row[-1] for row in header["edges"][-3:]])

    def test_exhaustion_never_caches_a_bad_result(self):
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
        from OCP.IMeshTools import IMeshTools_MeshAlgoType

        document, revision = source_document(BRepPrimAPI_MakeSphere(10.).Shape())
        calls = []
        def persistently_bad(native, parameters):
            calls.append(parameters.Deflection)
            parameters.MeshAlgo = IMeshTools_MeshAlgoType.IMeshTools_MeshAlgoType_Watson
            parameters.Deflection = parameters.DeflectionInterior = math.sqrt(1200.) * .0015
            parameters.Angle = parameters.AngleInterior = .35
            return BRepMesh_IncrementalMesh(native, parameters)
        with RevisionConsumer(document, revision.revision_id) as consumer:
            with patch("OCP.BRepMesh.BRepMesh_IncrementalMesh", side_effect=persistently_bad):
                with self.assertRaisesRegex(RuntimeError, "normal target after four passes"):
                    mesh_for_occurrence(consumer, consumer.occurrences()[0].path)
            self.assertEqual(4, len(calls))
            self.assertEqual(0, consumer.metrics.derivations_computed)
        self.assertEqual({}, document._derivations)

    def test_cancellation_between_passes_stops_before_another_native_mesh(self):
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
        from OCP.BRepTools import BRepTools

        count = 0
        def checkpoint():
            if count == 2:
                raise Cancelled("between native passes")
        original_clean = BRepTools.Clean_s
        def clean(native):
            nonlocal count
            count += 1
            original_clean(native)
        with patch("OCP.BRepTools.BRepTools.Clean_s", side_effect=clean), \
             patch("OCP.BRepMesh.BRepMesh_IncrementalMesh", wraps=BRepMesh_IncrementalMesh) as run:
            with self.assertRaises(Cancelled):
                _mesh_private(BRepPrimAPI_MakeSphere(10.).Shape(), MeshOptions(), checkpoint)
        self.assertEqual(1, run.call_count)

    def test_retry_checks_packet_capacity_again(self):
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere

        calls = 0
        def mesh(native, parameters):
            nonlocal calls
            calls += 1
            if calls == 2:
                meshing.MAX_PACKET_BYTES = 100
            return BRepMesh_IncrementalMesh(native, parameters)
        with patch.object(meshing, "MAX_PACKET_BYTES", meshing.MAX_PACKET_BYTES), \
             patch("OCP.BRepMesh.BRepMesh_IncrementalMesh", side_effect=mesh):
            with self.assertRaisesRegex(ValueError, "transfer limit"):
                _mesh_private(BRepPrimAPI_MakeSphere(10.).Shape(), MeshOptions())
        self.assertEqual(2, calls)

    def test_invalid_native_normals_and_positions_are_never_admitted(self):
        from OCP.BRep import BRep_Tool
        from OCP.BRepLib import BRepLib_ToolTriangulatedShape
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.gp import gp_Pnt, gp_Vec

        original = BRep_Tool.Triangulation_s
        compute = BRepLib_ToolTriangulatedShape.ComputeNormals_s
        for defect in ("nonfinite-normal", "nonunit-normal", "nonfinite-position"):
            with self.subTest(defect=defect):
                class Invalid:
                    def __init__(self, wrapped): self.wrapped = wrapped
                    def __getattr__(self, name): return getattr(self.wrapped, name)
                    def Normal(self, index):
                        if defect == "nonfinite-normal": return gp_Vec(float("nan"), 0., 1.)
                        if defect == "nonunit-normal": return gp_Vec(0., 0., .5)
                        return self.wrapped.Normal(index)
                    def Node(self, index):
                        return gp_Pnt(float("nan"), 0., 0.) if defect == "nonfinite-position" else self.wrapped.Node(index)
                def triangulation(face, location):
                    wrapped = original(face, location)
                    compute(face, wrapped)
                    return Invalid(wrapped)
                with patch("OCP.BRep.BRep_Tool.Triangulation_s", side_effect=triangulation), \
                     patch("OCP.BRepLib.BRepLib_ToolTriangulatedShape.ComputeNormals_s"):
                    with self.assertRaisesRegex(RuntimeError, "nonfinite coordinates or invalid normals"):
                        _mesh_private(BRepPrimAPI_MakeBox(1., 2., 3.).Shape(), MeshOptions())

    def test_tiny_reversed_facets_do_not_get_a_winding_exemption(self):
        from OCP.BRep import BRep_Tool
        from OCP.BRepLib import BRepLib_ToolTriangulatedShape
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.Poly import Poly_Triangle
        from OCP.gp import gp_Pnt

        original = BRep_Tool.Triangulation_s
        compute = BRepLib_ToolTriangulatedShape.ComputeNormals_s
        class ReversedTiny:
            def __init__(self, wrapped): self.wrapped = wrapped
            def __getattr__(self, name): return getattr(self.wrapped, name)
            def Node(self, index):
                point = self.wrapped.Node(index)
                return gp_Pnt(point.X(), point.Y() * 1e-7, point.Z() * 1e-7)
            def Triangle(self, index):
                a, b, c = self.wrapped.Triangle(index).Get()
                return Poly_Triangle(c, b, a)
        def triangulation(face, location):
            wrapped = original(face, location)
            compute(face, wrapped)
            return ReversedTiny(wrapped)
        with patch("OCP.BRep.BRep_Tool.Triangulation_s", side_effect=triangulation), \
             patch("OCP.BRepLib.BRepLib_ToolTriangulatedShape.ComputeNormals_s"):
            with self.assertRaisesRegex(RuntimeError, "normal target after four passes"):
                _mesh_private(BRepPrimAPI_MakeBox(gp_Pnt(-1., -1., -1.), 2., 2., 2.).Shape(), MeshOptions())

    def test_old_producer_kind_is_not_reused_even_with_same_codec(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

        document, revision = source_document(BRepPrimAPI_MakeBox(1., 2., 3.).Shape())
        with RevisionConsumer(document, revision.revision_id) as consumer:
            occurrence = consumer.occurrences()[0]
            old = (occurrence.prototype_id, "consumer-v2", "native-mesh-2", ("face", "edge"),
                   normalize(asdict(MeshOptions())), normalize(document.runtime))
            with self.assertRaises(TypeError):
                document._save_native_mesh_derivation(old, b"old Watson")
            document._derivations[old] = b"old Watson"
            packet = mesh_for_occurrence(consumer, occurrence.path)
            self.assertEqual(2, decoded(packet)[0]["version"])
            self.assertEqual(1, consumer.metrics.derivations_computed)
            self.assertEqual(packet, mesh_for_occurrence(consumer, occurrence.path))
            self.assertEqual(1, consumer.metrics.derivations_reused)
        self.assertTrue(any(key[2] == meshing.MESH_DERIVATION_KIND for key in document._derivations))

    def test_old_checkpoint_producer_is_a_native_only_recovery(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from cadgen._document import checkpoint
        from cadgen._document.storage import Catalog

        document, revision = source_document(BRepPrimAPI_MakeBox(1., 2., 3.).Shape())
        with RevisionConsumer(document, revision.revision_id) as consumer:
            mesh_for_occurrence(consumer, consumer.occurrences()[0].path)
        with tempfile.TemporaryDirectory() as folder, Catalog(Path(folder), engine_version=checkpoint.checkpoint_engine_version()) as catalog:
            codec = checkpoint.CheckpointCodec(catalog, runtime=document.runtime)
            staged = codec.stage(document, revision.revision_id)
            self.assertTrue(codec.commit(staged, expected_head=None))
            with catalog.lease(staged.revision_id) as lease:
                saved = catalog.read(lease)
            payloads = dict(saved.payloads)
            packet = payloads[checkpoint._MESH_ROLE]
            length, = struct.unpack_from("<I", packet, 8)
            index = json.loads(packet[12:12 + length])
            index["producer"]["semantics"] = "cadgen-native-mesh-v2.consumer-v2.copier-order-v1"
            encoded = json.dumps(index, separators=(",", ":")).encode()
            payloads[checkpoint._MESH_ROLE] = packet[:8] + struct.pack("<I", len(encoded)) + encoded + b" " * ((-len(encoded)) % 4) + packet[12 + length + (-length) % 4:]
            changed = catalog.stage(document.document_id, saved.metadata, payloads)
            self.assertTrue(catalog.checkpoint(changed, expected_head=staged.revision_id))
            recovered = codec.recover(document.document_id, changed.revision_id)
            self.assertEqual({}, recovered.document._derivations)
            self.assertEqual(revision.revision_id, recovered.revision.revision_id)
            with patch.object(meshing, "MESH_DERIVATION_KIND", "old-producer"):
                self.assertFalse(checkpoint._mesh_producer_is_current())


class NativeMeshDependencyTests(unittest.TestCase):
    def run_child(self, code):
        result = subprocess.run([sys.executable, "-B", "-c", code],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_producer_proof_import_stays_kernel_free(self):
        self.run_child("""
import sys
from cadgen._document import checkpoint
assert checkpoint._mesh_producer_is_current()
assert not any(name == 'OCP' or name.startswith('OCP.') for name in sys.modules)
""")

    def test_late_first_import_rejects_substituted_math(self):
        for name in ("cos", "sqrt", "hypot", "isfinite", "dist"):
            with self.subTest(name=name):
                self.run_child(f"""
import math, sys
setattr(math, {name!r}, lambda *args: -1.)
try:
    from cadgen._document import checkpoint
except RuntimeError as error:
    assert 'authentic built-in math' in str(error), error
else:
    raise AssertionError('substituted math became the canonical producer')
assert 'cadgen._document.checkpoint' not in sys.modules
""")

    def test_frontend_freezes_proof_before_source_without_a_checkpoint_catalog(self):
        self.run_child("""
import sys
from cadgen._document import Document
from cadgen._document.frontend import FrontendSession
assert 'cadgen._document.checkpoint' not in sys.modules
with Document('no-checkpoint-catalog').begin() as transaction:
    with FrontendSession(transaction):
        assert 'cadgen._document.checkpoint' in sys.modules
        from cadgen._document import checkpoint
        assert checkpoint._mesh_producer_is_current()
""")

    def test_public_math_replacement_cannot_bypass_the_sphere_retry(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
        from cadgen._document import checkpoint

        shape = BRepPrimAPI_MakeSphere(10.).Shape()
        expected, _ = observed_mesh(shape)
        with patch.object(math, "cos", return_value=-1.) as authored:
            actual, calls = observed_mesh(shape)
            self.assertTrue(checkpoint._mesh_producer_is_current())
        self.assertEqual(expected, actual)
        self.assertEqual([0, 1], [row[0] for row in calls])
        authored.assert_not_called()

    def test_enum_alias_redirection_does_not_change_canonical_output(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
        from cadgen._document import checkpoint

        shape = BRepPrimAPI_MakeSphere(10.).Shape()
        expected, _ = observed_mesh(shape)
        with patch("OCP.IMeshTools.IMeshTools_MeshAlgoType") as redirected:
            actual, calls = observed_mesh(shape)
            self.assertTrue(checkpoint._mesh_producer_is_current())
            self.assertEqual([], redirected.mock_calls)
        self.assertEqual(expected, actual)
        self.assertEqual([0, 1], [row[0] for row in calls])

    def test_changed_engine_math_alias_rejects_warm_reuse_and_checkpoint(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from cadgen._document import checkpoint

        document, revision = source_document(BRepPrimAPI_MakeBox(1., 2., 3.).Shape())
        with RevisionConsumer(document, revision.revision_id) as consumer:
            path = consumer.occurrences()[0].path
            mesh_for_occurrence(consumer, path)
            with patch.object(meshing, "_math_cos", return_value=-1.) as authored:
                self.assertFalse(checkpoint._mesh_producer_is_current())
                with self.assertRaisesRegex(RuntimeError, "math inputs changed"):
                    mesh_for_occurrence(consumer, path)
                authored.assert_not_called()
            self.assertEqual(0, consumer.metrics.derivations_reused)

    def test_changed_guard_is_rejected_before_attestation_can_call_it(self):
        from cadgen._document import checkpoint

        with patch.object(meshing, "_math_inputs_are_current") as authored:
            self.assertFalse(checkpoint._mesh_producer_is_current())
            authored.assert_not_called()

    def test_native_enum_python_method_replacements_are_rejected_without_calling(self):
        from OCP.IMeshTools import IMeshTools_Parameters

        parameters = IMeshTools_Parameters()
        enum_type = type(parameters.MeshAlgo)
        for name in ("__new__", "__init__", "__int__"):
            with self.subTest(name=name), patch.object(enum_type, name) as authored:
                with self.assertRaisesRegex(RuntimeError, "enum (constructor|methods) changed"):
                    meshing._native_algorithms(parameters)
                authored.assert_not_called()

    def test_late_math_attribute_hook_is_not_called_during_capture(self):
        self.run_child("""
import array, dataclasses, io, json, math, struct, sys
from cadgen._document import resources
assert 'cadgen._document.meshing' not in sys.modules
calls = []
del math.cos
def substituted(name):
    calls.append(name)
    return lambda *args: -1.
math.__getattr__ = substituted
try:
    from cadgen._document import meshing
except RuntimeError as error:
    assert 'authentic built-in math' in str(error), error
else:
    raise AssertionError('missing math function became canonical')
assert not calls, calls
""")
