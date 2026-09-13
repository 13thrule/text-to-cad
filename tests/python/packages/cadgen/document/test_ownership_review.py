"""Independent adversarial review of retained-document ownership contracts."""

from threading import Event
import unittest

from cadgen._document import Document, Mutation, NativeResult, OperatorSpec, ResourceAdmission, ResourceRequest


class ResourceDomainReview(unittest.TestCase):
    def test_capacity_and_reservation_are_nonnegative_integer_counts(self):
        for value in (True, 1.5, float("nan"), float("inf"), "1"):
            for field in ("cpu_slots", "native_bytes", "derived_bytes"):
                with self.subTest(value=value, field=field):
                    with self.assertRaises((TypeError, ValueError)):
                        ResourceRequest(**{field: value})
                    with self.assertRaises((TypeError, ValueError)):
                        ResourceAdmission(**{field: value})


class NativeOwnershipReview(unittest.TestCase):
    @staticmethod
    def _box(tx, size):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        return tx.evaluate(
            OperatorSpec("review.box", mutation=Mutation.READ_ONLY), size, (),
            lambda inputs, arena: NativeResult(BRepPrimAPI_MakeBox(*size).Shape()),
        )

    def test_cancelled_native_result_never_advances_head_or_holds_reservation(self):
        from cadgen._document import Cancelled
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        doc = Document("cancel")
        with doc.begin() as tx:
            self._box(tx, (1, 2, 3))
            old = tx.commit()
        with self.assertRaises(Cancelled):
            with doc.begin() as tx:
                def cancelled(inputs, arena):
                    result = BRepPrimAPI_MakeBox(4, 5, 6).Shape()
                    tx.cancellation.set()
                    return NativeResult(result)
                tx.evaluate(OperatorSpec("review.cancel"), (), (), cancelled)
        self.assertEqual(old, doc.head)
        self.assertEqual((0, 0, 0), doc.admission.used)
        doc.collect(keep_revisions=0)
        self.assertEqual(1, doc.prototype_count)

    def test_mesh_derivation_may_mutate_its_private_input_only(self):
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Pnt
        doc = Document("derived-isolation")

        def vertex(native):
            return TopoDS.Vertex_s(TopExp_Explorer(native, TopAbs_VERTEX).Current())

        with doc.begin() as tx:
            part = self._box(tx, (10, 8, 2))
            before = tx.query(part, lambda native: BRep_Tool.Pnt_s(vertex(native)).X())
            def mutate_private(native):
                BRep_Builder().UpdateVertex(vertex(native), gp_Pnt(100, 0, 0), .01)
                return {"vertices": [100, 0, 0]}
            derived = tx.derive(part, "review.mesh", (), mutate_private)
            self.assertEqual((100, 0, 0), derived["vertices"])
            with self.assertRaises(TypeError):
                derived["vertices"] = (0, 0, 0)
            self.assertEqual(before, tx.query(part, lambda native: BRep_Tool.Pnt_s(vertex(native)).X()))
            tx.commit()

    def test_distinct_equal_inputs_remain_distinct_through_cached_selection(self):
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        doc = Document("selection-allocations")
        spec = OperatorSpec("review.face", mutation=Mutation.READ_ONLY)
        with doc.begin() as tx:
            first = self._box(tx, (10, 8, 2))
            second = self._box(tx, (10, 8, 2))
            a = tx.evaluate(spec, (), (first,), lambda shapes, arena:
                            NativeResult(TopExp_Explorer(shapes[0], TopAbs_FACE).Current()))
            b = tx.evaluate(spec, (), (second,), lambda shapes, arena:
                            NativeResult(TopExp_Explorer(shapes[0], TopAbs_FACE).Current()))
            a_native, b_native = tx.escape_arena.native(a), tx.escape_arena.native(b)
            self.assertFalse(a_native.IsSame(b_native))
            self.assertTrue(a_native.IsSame(TopExp_Explorer(tx.escape_arena.native(first), TopAbs_FACE).Current()))
            self.assertTrue(b_native.IsSame(TopExp_Explorer(tx.escape_arena.native(second), TopAbs_FACE).Current()))


if __name__ == "__main__":
    unittest.main()
