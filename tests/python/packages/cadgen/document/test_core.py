"""Bounded P1 contracts: identities, ownership, revisions, and admission."""
from __future__ import annotations

from threading import Event
import unittest
from unittest.mock import patch

from cadgen._document import (AdmissionDenied, Cancelled, Document, EvaluationKey,
                             ExportConflict, Mutation, NativeResult, OperatorSpec,
                             ResourceAdmission, ResourceRequest, RevisionState,
                             SupersededRevision, history_from_builder)


BOX = OperatorSpec("test.box", "1", Mutation.READ_ONLY)
IDENTITY = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


def box(tx, size=(10., 8., 2.)):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    return tx.evaluate(BOX, size, (),
                       lambda inputs, arena: NativeResult(BRepPrimAPI_MakeBox(*size).Shape()))


def volume(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


class TypedIdentityTests(unittest.TestCase):
    def test_types_versions_inputs_and_runtime_are_part_of_identity(self):
        def key(value, **kw):
            return EvaluationKey.create("box", "1", value, **kw).identity
        self.assertNotEqual(key(True), key(1))
        self.assertNotEqual(key(1), key(1.))
        self.assertNotEqual(key([1]), key((1,)))
        self.assertNotEqual(key(0.), key(-0.))
        self.assertEqual(key({"a": 1, "b": 2}), key({"b": 2, "a": 1}))
        self.assertNotEqual(key(1, runtime={"occt": "a"}), key(1, runtime={"occt": "b"}))
        self.assertNotEqual(key(1), EvaluationKey.create("box", "2", 1).identity)
        self.assertNotEqual(key(1), key(1, inputs=(key(2),)))
        with self.assertRaises(TypeError):
            key(object())
        with self.assertRaises(ValueError):
            key(float("nan"))


class ResourceTests(unittest.TestCase):
    def test_admission_failure_cancellation_and_exception_release(self):
        admission = ResourceAdmission(native_bytes=10)
        with admission.admit(ResourceRequest(native_bytes=8)):
            with self.assertRaises(AdmissionDenied):
                with admission.admit(ResourceRequest(cpu_slots=0, native_bytes=3)):
                    pass
        self.assertEqual(admission.used, (0, 0, 0))
        with self.assertRaises(RuntimeError):
            with admission.admit(ResourceRequest()):
                raise RuntimeError("failed kernel")
        self.assertEqual(admission.used, (0, 0, 0))
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            with admission.admit(ResourceRequest(), cancellation=cancel):
                pass


class NativeDocumentTests(unittest.TestCase):
    def test_unchanged_operations_use_resident_native_without_copy_or_brep(self):
        doc = Document("plate")
        with doc.begin("first") as first:
            a = box(first)
            first.commit()
        # Guard both common native serialization doors, and ownership copies.
        # No geometry hash or native codec is needed by unchanged evaluation.
        with patch("OCP.BRepTools.BRepTools.Write_s", side_effect=AssertionError("BREP write")), \
             patch("OCP.BRepTools.BRepTools.Read_s", side_effect=AssertionError("BREP read")), \
             patch("OCP.BinTools.BinTools.Write_s", side_effect=AssertionError("BREP write")), \
             patch("OCP.BinTools.BinTools.Read_s", side_effect=AssertionError("BREP read")), \
             patch("cadgen._document.core.copy_shape", side_effect=AssertionError("native copy")), \
             patch("cadgen._document.core.copy_many", side_effect=AssertionError("native copy")):
            with doc.begin("replayed Python") as second:
                b = box(second)
                self.assertEqual(a.prototype_id, b.prototype_id)
                self.assertNotEqual(a.allocation_id, b.allocation_id)
                self.assertEqual((second.stats.computed, second.stats.reused), (0, 1))
                self.assertAlmostEqual(second.query(b, volume), 160.)
                second.commit()

    def test_placement_revision_reuses_one_prototype_and_one_mesh(self):
        from cadgen._document.roots import AssemblyGroup, GeometryLeaf

        doc = Document("assembly")
        calls = []
        for revision, offset in enumerate((0., 2.)):
            with doc.begin(str(revision)) as tx:
                part = box(tx)
                tx.derive(part, "test-mesh-v1", {"tolerance": .1},
                          lambda native: calls.append(volume(native)) or b"mesh")
                occurrences = []
                for index in range(24):
                    matrix = list(IDENTITY)
                    matrix[3] = index * 12 + offset
                    occurrences.append(GeometryLeaf(f"part-{index}", part, matrix))
                tx.bind_root(AssemblyGroup("assembly", occurrences))
                tx.commit()
                if revision:
                    self.assertEqual(tx.stats.computed, 0)
                    self.assertEqual(tx.stats.derived_computed, 0)
                    self.assertEqual(tx.stats.derived_reused, 1)
        self.assertEqual(len(calls), 1)
        self.assertAlmostEqual(calls[0], 160.)
        self.assertEqual(len(doc.head.root.children), 24)

    def test_independent_equal_allocations_remain_distinct_after_escape(self):
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Pnt
        doc = Document("allocation")
        with doc.begin() as tx:
            a, b = box(tx), box(tx)
            self.assertEqual(a.prototype_id, b.prototype_id)
            a_native = tx.escape_arena.native(a)
            b_native = tx.escape_arena.native(b)
            self.assertFalse(a_native.IsSame(b_native))
            self.assertTrue(a_native.IsSame(tx.escape_arena.native(a)))
            av = TopoDS.Vertex_s(TopExp_Explorer(a_native, TopAbs_VERTEX).Current())
            bv = TopoDS.Vertex_s(TopExp_Explorer(b_native, TopAbs_VERTEX).Current())
            old = BRep_Tool.Pnt_s(bv).X()
            BRep_Builder().UpdateVertex(av, gp_Pnt(old + 5., 0., 0.), .01)
            self.assertEqual(BRep_Tool.Pnt_s(bv).X(), old)
            tx.commit()

    def test_root_child_aliases_share_mutation_but_later_revision_is_pristine(self):
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.TopAbs import TopAbs_FACE, TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Pnt
        doc = Document("alias")
        select = OperatorSpec("test.first-face", "1", Mutation.READ_ONLY)
        with doc.begin() as tx:
            root = box(tx)
            face = tx.evaluate(select, (), (root,), lambda shapes, arena:
                               NativeResult(TopExp_Explorer(shapes[0], TopAbs_FACE).Current()))
            private_root = tx.escape_arena.native(root)
            private_face = tx.escape_arena.native(face)
            root_face = TopExp_Explorer(private_root, TopAbs_FACE).Current()
            self.assertTrue(root_face.IsSame(private_face))
            vertex = TopoDS.Vertex_s(TopExp_Explorer(private_face, TopAbs_VERTEX).Current())
            original = BRep_Tool.Pnt_s(vertex).X()
            BRep_Builder().UpdateVertex(vertex, gp_Pnt(original + 5., 0., 0.), .01)
            root_vertex = TopoDS.Vertex_s(TopExp_Explorer(root_face, TopAbs_VERTEX).Current())
            self.assertEqual(BRep_Tool.Pnt_s(root_vertex).X(), original + 5.)
            # Same managed input after escape must see the private mutation and
            # receive a volatile evaluation, never hit its previous pristine key.
            selected_again = tx.evaluate(select, (), (root,), lambda shapes, arena:
                                        NativeResult(TopExp_Explorer(shapes[0], TopAbs_FACE).Current()))
            self.assertNotEqual(selected_again.evaluation_id, face.evaluation_id)
            tx.commit()
        with doc.begin() as tx:
            clean = box(tx)
            native = tx.escape_arena.native(clean)
            vertex = TopoDS.Vertex_s(TopExp_Explorer(native, TopAbs_VERTEX).Current())
            self.assertEqual(BRep_Tool.Pnt_s(vertex).X(), original)

    def test_private_default_mutation_and_opaque_capture_are_isolated(self):
        from OCP.BRep import BRep_Builder
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Pnt
        doc = Document("private")
        with doc.begin() as tx:
            original = box(tx)
            def mutate(shapes, arena):
                v = TopoDS.Vertex_s(TopExp_Explorer(shapes[0], TopAbs_VERTEX).Current())
                BRep_Builder().UpdateVertex(v, gp_Pnt(50, 0, 0), .01)
                return NativeResult(shapes[0])
            tx.evaluate(OperatorSpec("mutating-test"), (), (original,), mutate)
            self.assertAlmostEqual(tx.query(original, volume), 160.)
            with self.assertRaises(TypeError):
                tx.query(original, lambda shape: {"nested": [shape]})
            tx.commit()

    def test_rigid_native_placement_preserves_partner_aliases(self):
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Trsf, gp_Vec
        doc = Document("native-move")
        transformation = gp_Trsf()
        transformation.SetTranslation(gp_Vec(15, 0, 0))
        location = TopLoc_Location(transformation)
        with doc.begin() as tx:
            original = box(tx)
            moved = tx.evaluate(OperatorSpec("move", "1", Mutation.READ_ONLY),
                                (15., 0., 0.), (original,), lambda shapes, arena:
                                NativeResult(shapes[0].Moved(location)))
            selected = tx.evaluate(OperatorSpec("moved-face", "1", Mutation.READ_ONLY),
                                   (), (moved,), lambda shapes, arena:
                                   NativeResult(TopExp_Explorer(shapes[0], TopAbs_FACE).Current()))
            first, second = tx.escape_arena.native(original), tx.escape_arena.native(moved)
            self.assertFalse(first.IsSame(second))
            self.assertTrue(first.IsPartner(second))
            self.assertTrue(tx.escape_arena.native(selected).IsSame(
                TopExp_Explorer(second, TopAbs_FACE).Current()))
            tx.commit()

    def test_pins_failure_rollback_supersession_and_export_obligations(self):
        doc = Document("revisions")
        older = doc.begin("old", required_exports=("part.step",))
        old = box(older, (1., 2., 3.))
        newer = doc.begin("new", required_exports=("part.step",))
        box(newer, (2., 2., 3.))
        newest = newer.commit()
        self.assertEqual(doc.state(newest.revision_id), RevisionState.GEOMETRY_READY)
        with self.assertRaises(SupersededRevision) as raised:
            older.commit()
        self.assertEqual(doc.head, newest)
        stale = raised.exception.revision
        with doc.pin(stale.revision_id) as pin:
            with self.assertRaises(ExportConflict):
                doc.publish_export(pin, "part.step", lambda: self.fail("older save executed"))
            doc.collect(keep_revisions=0)
            self.assertEqual(doc._get(old).handle.prototype_id, old.prototype_id)
        with doc.pin(newest.revision_id) as pin:
            doc.publish_export(pin, "part.step", lambda: "saved")
        self.assertEqual(doc.state(newest.revision_id), RevisionState.EXPORTS_COMPLETE)
        doc.fail(stale.revision_id)
        doc.collect(keep_revisions=0)
        with self.assertRaises(KeyError):
            doc.pin(stale.revision_id)
        with self.assertRaises(RuntimeError):
            with doc.begin("failed") as tx:
                box(tx, (9., 9., 9.))
                raise RuntimeError("source error")
        self.assertEqual(doc.head, newest)

    def test_boolean_history_retains_modified_generated_deleted_evidence(self):
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
        from OCP.TopTools import TopTools_ListOfShape
        plate = BRepPrimAPI_MakeBox(10, 8, 2).Shape()
        tool = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(5, 4, -1), gp_Dir(0, 0, 1)), 1, 4).Shape()
        arguments, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
        arguments.Append(plate)
        tools.Append(tool)
        operation = BRepAlgoAPI_Cut()
        operation.SetArguments(arguments)
        operation.SetTools(tools)
        operation.SetNonDestructive(True)
        operation.Build()
        self.assertTrue(operation.IsDone())
        history = history_from_builder(operation, (plate, tool))
        self.assertTrue(history.complete, history.reason)
        self.assertTrue(history.modified)
        self.assertTrue(history.generated)
        self.assertTrue(history.deleted)
        self.assertTrue(history.unchanged)
        self.assertTrue(all(ref.input_index in (0, 1) for ref in history.deleted))

    def test_local_hole_edit_skips_plate_and_mesh_never_mutates_prototype(self):
        from OCP.BRep import BRep_Tool
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopTools import TopTools_ListOfShape
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
        doc = Document("plate-holes-fillet")
        counts = {"plate": 0, "hole": 0, "cut": 0, "fillet": 0}

        def mesh(shape):
            BRepMesh_IncrementalMesh(shape, .1, False, .2, False)
            triangles = 0
            exp = TopExp_Explorer(shape, TopAbs_FACE)
            while exp.More():
                surface = BRep_Tool.Triangulation_s(TopoDS.Face_s(exp.Current()), TopLoc_Location())
                triangles += surface.NbTriangles()
                exp.Next()
            return triangles

        def cut(shapes, arena):
            counts["cut"] += 1
            args, cutters = TopTools_ListOfShape(), TopTools_ListOfShape()
            args.Append(shapes[0]); cutters.Append(shapes[1])
            operation = BRepAlgoAPI_Cut()
            operation.SetArguments(args); operation.SetTools(cutters)
            operation.SetNonDestructive(True)
            operation.Build()
            return NativeResult(operation.Shape(), history_from_builder(operation, shapes))

        def fillet(shapes, arena):
            counts["fillet"] += 1
            operation = BRepFilletAPI_MakeFillet(shapes[0])
            edge = TopoDS.Edge_s(TopExp_Explorer(shapes[0], TopAbs_EDGE).Current())
            operation.Add(.2, edge)
            operation.Build()
            self.assertTrue(operation.IsDone())
            return NativeResult(operation.Shape(), history_from_builder(operation, shapes))

        for radius in (1., 1.2):
            with doc.begin(str(radius)) as tx:
                plate = box(tx)
                counts["plate"] += tx.stats.computed
                def hole(shapes, arena):
                    counts["hole"] += 1
                    return NativeResult(BRepPrimAPI_MakeCylinder(
                        gp_Ax2(gp_Pnt(5, 4, -1), gp_Dir(0, 0, 1)), radius, 4).Shape())
                cutter = tx.evaluate(OperatorSpec("hole", "1", Mutation.READ_ONLY), radius, (), hole)
                holed = tx.evaluate(OperatorSpec("cut", "1", Mutation.READ_ONLY), (), (plate, cutter), cut)
                final = tx.evaluate(OperatorSpec("fillet"), .2, (holed,), fillet)
                triangles = tx.derive(final, "occt-mesh-v1", (.1, .2), mesh)
                self.assertGreater(triangles, 0)
                self.assertTrue(tx.query(final, lambda shape: BRep_Tool.Triangulation_s(
                    TopoDS.Face_s(TopExp_Explorer(shape, TopAbs_FACE).Current()), TopLoc_Location()) is None))
                self.assertTrue(doc.history(final).modified)
                tx.commit()
        self.assertEqual(counts, {"plate": 1, "hole": 2, "cut": 2, "fillet": 2})

    def test_ocaf_transaction_and_naming_api_probe_with_explicit_cleanup(self):
        # Comparison probe only. No second production document engine is kept.
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDataStd import TDataStd_Integer
        from OCP.TDocStd import TDocStd_Document
        from OCP.TNaming import TNaming_Builder
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        document = TDocStd_Document(TCollection_ExtendedString("BinOcaf"))
        document.SetUndoLimit(10)
        document.NewCommand()
        attribute = TDataStd_Integer.Set_s(document.Main(), 1)
        self.assertTrue(document.CommitCommand())
        document.NewCommand()
        attribute.Set(2)
        document.AbortCommand()
        self.assertEqual(attribute.Get(), 1)
        document.NewCommand()
        builder = TNaming_Builder(document.Main().FindChild(1))
        builder.Generated(BRepPrimAPI_MakeBox(2, 3, 4).Shape())
        self.assertTrue(document.CommitCommand())
        del builder, attribute
        document.ClearUndos()
        document.ClearRedos()
        document.Main().ForgetAllAttributes(True)

    def test_read_only_holed_plate_fillet_preserves_pcurves_and_shared_topology(self):
        import build123d as bd
        from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Trsf, gp_Vec
        from cadgen._document.native import topology_map
        plain = bd.Box(30, 20, 6)
        for x in (-8, 8):
            plain = plain - bd.Pos(x, 0, 0) * bd.Cylinder(1.5, 10)
        expected = bd.fillet(plain.edges().filter_by(bd.Axis.Z), 1.)
        document = Document("fillet-pcurve-family")
        with document.begin() as tx:
            source = tx.capture(plain.wrapped)
            def fillet(shapes, arena):
                builder = BRepFilletAPI_MakeFillet(shapes[0])
                for edge in bd.Part(shapes[0]).edges().filter_by(bd.Axis.Z):
                    builder.Add(1., edge.wrapped)
                return NativeResult(builder.Shape(), history_from_builder(builder, shapes))
            result = tx.evaluate(OperatorSpec("fillet-holed-plate", "1", Mutation.READ_ONLY),
                                 1., (source,), fillet)
            self.assertTrue(tx.query(result, lambda shape: bd.Part(shape).is_valid))
            transform = gp_Trsf()
            transform.SetTranslation(gp_Vec(0, 0, 5))
            location = TopLoc_Location(transform)
            placed = tx.evaluate(OperatorSpec("placed-fillet", "1", Mutation.READ_ONLY),
                                 5., (result,), lambda shapes, arena:
                                 NativeResult(shapes[0].Moved(location)))
            private_result = tx.escape_arena.native(result)
            private_source = tx.escape_arena.native(source)
            private_placed = tx.escape_arena.native(placed)
            actual = bd.Part(private_result)
            self.assertTrue(actual.is_valid)
            self.assertAlmostEqual(actual.volume, expected.volume, places=8)
            self.assertTrue(private_placed.IsPartner(private_result))
            self.assertTrue(bd.Part(private_placed).is_valid)
            self.assertAlmostEqual(bd.Part(private_placed).volume, expected.volume, places=8)
            result_map, source_map = topology_map(private_result), topology_map(private_source)
            self.assertGreater(sum(source_map.Contains(result_map.FindKey(index))
                                   for index in range(1, result_map.Extent() + 1)), 0)
            tx.commit()

    def test_private_root_and_face_alias_provenance_is_stable_across_replay(self):
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.TopAbs import TopAbs_FACE, TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Pnt
        document = Document("private-root-face-alias-key")
        def first_vertex(shape):
            return TopoDS.Vertex_s(TopExp_Explorer(shape, TopAbs_VERTEX).Current())
        def x(shape):
            return BRep_Tool.Pnt_s(first_vertex(shape)).X()
        evaluations = []
        for revision in range(2):
            with document.begin(str(revision)) as tx:
                root_a, root_b = box(tx), box(tx)
                select = OperatorSpec("alias-key-face", "1", Mutation.READ_ONLY)
                def face(shapes, arena):
                    return NativeResult(TopExp_Explorer(shapes[0], TopAbs_FACE).Current())
                face_a = tx.evaluate(select, (), (root_a,), face)
                face_b = tx.evaluate(select, (), (root_b,), face)
                mutate = OperatorSpec("alias-key-mutating-face")
                def change_root_return_face(shapes, arena):
                    BRep_Builder().UpdateVertex(first_vertex(shapes[0]), gp_Pnt(50., 0., 0.), .01)
                    return NativeResult(shapes[1])
                same = tx.evaluate(mutate, (), (root_a, face_a), change_root_return_face)
                distinct = tx.evaluate(mutate, (), (root_a, face_b), change_root_return_face)
                self.assertNotEqual(same.evaluation_id, distinct.evaluation_id)
                self.assertEqual(tx.query(same, x), 50.)
                self.assertEqual(tx.query(distinct, x), 0.)
                if revision:
                    self.assertEqual(tx.stats.computed, 0)
                    self.assertEqual(evaluations, [same.evaluation_id, distinct.evaluation_id])
                evaluations = [same.evaluation_id, distinct.evaluation_id]
                tx.commit()


if __name__ == "__main__":
    unittest.main()
