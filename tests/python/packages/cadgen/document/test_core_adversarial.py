"""Independent direct-native regressions for allocation and lifecycle boundaries."""
from __future__ import annotations

import unittest

from cadgen._document import (
    AdmissionDenied, Document, Mutation, NativeResult, OperatorSpec,
    ResourceRequest, RevisionState,
)


def box(tx, size=(10., 8., 2.)):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    return tx.evaluate(OperatorSpec("adversarial.box", mutation=Mutation.READ_ONLY),
                       size, (), lambda inputs, arena:
                       NativeResult(BRepPrimAPI_MakeBox(*size).Shape()))


def first_vertex(shape):
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    return TopoDS.Vertex_s(TopExp_Explorer(shape, TopAbs_VERTEX).Current())


def vertex_x(shape):
    from OCP.BRep import BRep_Tool
    return BRep_Tool.Pnt_s(first_vertex(shape)).X()


def move_vertex(shape, x):
    from OCP.BRep import BRep_Builder
    from OCP.gp import gp_Pnt
    BRep_Builder().UpdateVertex(first_vertex(shape), gp_Pnt(x, 0, 0), .01)


class AllocationReview(unittest.TestCase):
    def test_private_operator_keeps_independent_equal_inputs_independent(self):
        document = Document("independent-private-inputs")
        with document.begin() as tx:
            first, second = box(tx), box(tx)
            self.assertEqual(first.prototype_id, second.prototype_id)
            self.assertNotEqual(first.allocation_id, second.allocation_id)
            before = tx.query(second, vertex_x)

            def mutate_first(inputs, arena):
                move_vertex(inputs[0], before + 50.)
                self.assertEqual(before, vertex_x(inputs[1]),
                                 "private input copying merged independent allocations")
                return NativeResult(inputs[0])

            tx.evaluate(OperatorSpec("adversarial.mutate-first"), (),
                        (first, second), mutate_first)
            self.assertEqual(before, tx.query(first, vertex_x))
            self.assertEqual(before, tx.query(second, vertex_x))

    def test_private_operator_preserves_two_references_to_one_allocation(self):
        document = Document("same-private-input")
        with document.begin() as tx:
            part = box(tx)
            before = tx.query(part, vertex_x)

            def mutate_first(inputs, arena):
                move_vertex(inputs[0], before + 50.)
                self.assertTrue(inputs[0].IsSame(inputs[1]))
                self.assertEqual(before + 50., vertex_x(inputs[1]))
                return NativeResult(inputs[0])

            tx.evaluate(OperatorSpec("adversarial.mutate-one-alias"), (),
                        (part, part), mutate_first)
            self.assertEqual(before, tx.query(part, vertex_x))

    def test_private_operator_identity_distinguishes_input_alias_partition(self):
        document = Document("private-input-alias-key")
        with document.begin() as tx:
            first, second = box(tx), box(tx)
            spec = OperatorSpec("adversarial.mutate-first-return-second")
            def mutate_first_return_second(inputs, arena):
                move_vertex(inputs[0], 50.)
                return NativeResult(inputs[1])
            same = tx.evaluate(spec, (), (first, first), mutate_first_return_second)
            independent = tx.evaluate(spec, (), (first, second), mutate_first_return_second)
            self.assertEqual(50., tx.query(same, vertex_x))
            self.assertNotEqual(same.evaluation_id, independent.evaluation_id,
                                "native mutation outcomes depend on input aliases")
            self.assertEqual(0., tx.query(independent, vertex_x))

    def test_cached_moved_selection_keeps_its_revision_allocation_after_gc(self):
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Trsf, gp_Vec
        document = Document("cached-move-selection")
        translation = gp_Trsf()
        translation.SetTranslation(gp_Vec(15., 0., 0.))
        location = TopLoc_Location(translation)
        previous = None
        for iteration in range(3):
            with document.begin(str(iteration)) as tx:
                root = box(tx)
                moved = tx.evaluate(OperatorSpec("adversarial.move", mutation=Mutation.READ_ONLY),
                                    15., (root,), lambda inputs, arena:
                                    NativeResult(inputs[0].Moved(location)))
                selected = tx.evaluate(OperatorSpec("adversarial.face", mutation=Mutation.READ_ONLY),
                                       (), (moved,), lambda inputs, arena:
                                       NativeResult(TopExp_Explorer(inputs[0], TopAbs_FACE).Current()))
                if previous is not None:
                    self.assertEqual(previous.prototype_id, selected.prototype_id)
                    self.assertNotEqual(previous.allocation_id, selected.allocation_id)
                    self.assertEqual((0, 3), (tx.stats.computed, tx.stats.reused))
                private_root = tx.escape_arena.native(root)
                private_moved = tx.escape_arena.native(moved)
                private_face = tx.escape_arena.native(selected)
                self.assertTrue(private_root.IsPartner(private_moved))
                self.assertTrue(private_face.IsSame(
                    TopExp_Explorer(private_moved, TopAbs_FACE).Current()))
                self.assertTrue(BRepCheck_Analyzer(private_moved).IsValid())
                tx.commit()
            document.collect(keep_revisions=0)
            previous = selected
        self.assertEqual(3, document.prototype_count)
        self.assertEqual(3, len(document._allocations))


class LifecycleReview(unittest.TestCase):
    def test_outstanding_exports_and_live_pin_independently_keep_old_geometry(self):
        document = Document("pin-and-obligation")
        with document.begin(required_exports=("old.step",)) as tx:
            old_geometry = box(tx)
            old = tx.commit()
        with document.begin() as tx:
            box(tx, (3., 4., 5.))
            tx.commit()
        document.collect(keep_revisions=0)
        self.assertEqual(2, document.prototype_count)
        pin = document.pin(old.revision_id)
        document.complete_exports(old.revision_id, ("old.step",))
        self.assertEqual(RevisionState.EXPORTS_COMPLETE, document.state(old.revision_id))
        document.collect(keep_revisions=0)
        self.assertEqual(old_geometry.prototype_id, document._get(old_geometry).handle.prototype_id)
        pin.release()
        pin.release()
        document.collect(keep_revisions=0)
        self.assertEqual(1, document.prototype_count)
        with self.assertRaises(KeyError):
            document.pin(old.revision_id)
        with self.assertRaises(ValueError):
            document._get(old_geometry)

    def test_export_failure_leaves_obligation_and_releases_reservation(self):
        document = Document("failed-export")
        with document.begin(required_exports=("part.step",)) as tx:
            box(tx)
            revision = tx.commit()
        def fail_writer():
            raise OSError("simulated export failure")
        with document.pin() as pin:
            with self.assertRaisesRegex(OSError, "simulated"):
                document.publish_export(pin, "part.step", fail_writer)
            self.assertEqual((0, 0, 0), document.admission.used)
            self.assertEqual(RevisionState.GEOMETRY_READY, document.state(revision.revision_id))
            self.assertEqual(set(), document._completed_exports[revision.revision_id])
            self.assertEqual("saved", document.publish_export(pin, "part.step", lambda: "saved"))
        self.assertEqual(RevisionState.EXPORTS_COMPLETE, document.state(revision.revision_id))

    def test_nested_admission_fails_immediately_and_leaves_no_result_or_reservation(self):
        document = Document("reentrant-native")
        with document.begin() as tx:
            root = box(tx)
            def nested(inputs, arena):
                tx.query(root, vertex_x)
                return NativeResult(inputs[0])
            with self.assertRaises(AdmissionDenied):
                tx.evaluate(OperatorSpec("adversarial.reentrant", resources=ResourceRequest()),
                            (), (root,), nested)
            self.assertEqual((0, 0, 0), document.admission.used)
            self.assertEqual(1, document.prototype_count)
            self.assertEqual(0., tx.query(root, vertex_x))


if __name__ == "__main__":
    unittest.main()
