"""Independent child snapshots inside one open native family execution."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from cadgen._document import (Document, ExportConflict, Mutation, NativeResult,
                             OperatorSpec, RevisionState, SupersededRevision)
from cadgen._document.frontend import FrontendSession
from cadgen._document.returned import bind_returned_shape
from cadgen._document.roots import GeometryLeaf


BOX = OperatorSpec("test.family.box", "1", Mutation.READ_ONLY)


def box(tx, length=4.):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    return tx.evaluate(BOX, (length,), (), lambda inputs, arena:
                       NativeResult(BRepPrimAPI_MakeBox(length, 3., 2.).Shape()))


def volume(native):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    values = GProp_GProps()
    BRepGProp.VolumeProperties_s(native, values)
    return values.Mass()


def publish(tx, handle, *, entry="child", path="child.step", source="captured child bytes"):
    return tx.publish_result(entry, GeometryLeaf("root", handle, label=entry),
                             source_identity=source, required_exports=(path,),
                             unrepresented_metadata=())


class FamilyRevisionTests(unittest.TestCase):
    def test_child_survives_parent_abort_without_retaining_parent_temporaries(self):
        document = Document("family")
        with document.begin("previous successful parent") as previous:
            previous.bind_root(GeometryLeaf("parent", box(previous, 10.)))
            prior = previous.commit()
        tx = document.begin("parent that fails", required_exports=("parent.step",))
        temporary = box(tx, 9.)
        child = box(tx)
        revision = publish(tx, child)
        with document.pin(revision.revision_id) as pin:
            self.assertFalse(tx._closed)
            self.assertIsNone(tx._root)
            self.assertIs(document.head, prior)
            self.assertIs(document.entry_head("child"), revision)
            tx.abort()
            document.collect(keep_revisions=0)
            self.assertIs(pin.revision, revision)
            self.assertAlmostEqual(document.publish_export(pin, "child.step", lambda:
                                                          volume(document._get(child).shape)), 24.)
            self.assertEqual(document.state(revision.revision_id), RevisionState.EXPORTS_COMPLETE)
            self.assertIs(document.head, prior)
            with self.assertRaises(ValueError):
                document._get(temporary)

    def test_same_child_twice_has_independent_results_and_ordered_outputs(self):
        document = Document("family")
        written = []
        with document.begin("parent") as tx:
            first_handle = box(tx)
            first = publish(tx, first_handle, source="child first invocation")
            with document.pin(first.revision_id) as first_pin:
                document.publish_export(first_pin, "child.step", lambda: written.append(24.))
                second_handle = box(tx, 7.)
                second = publish(tx, second_handle, source="child second invocation")
                with document.pin(second.revision_id) as second_pin:
                    document.publish_export(second_pin, "child.step", lambda: written.append(42.))
                self.assertIs(document.entry_head("child"), second)
                self.assertNotEqual(first.revision_id, second.revision_id)
                self.assertEqual(first.source_identity, "child first invocation")
                self.assertAlmostEqual(volume(document._get(first_pin.revision.root.geometry).shape), 24.)
                with self.assertRaises(ExportConflict):
                    document.publish_export(first_pin, "child.step", lambda: self.fail("stale output write"))
                self.assertFalse(tx._closed)
                self.assertAlmostEqual(tx.query(second_handle, volume), 42.)
        self.assertEqual(written, [24., 42.])

    def test_publication_preserves_managed_wrappers_and_parent_root_candidate(self):
        import build123d as bd
        document = Document("family")
        with document.begin("parent") as tx:
            with FrontendSession(tx) as frontend:
                shape = bd.Box(4., 3., 2.)
                authored_root = bind_returned_shape(frontend, shape)
                with patch("cadgen._document.core.copy_shape", side_effect=AssertionError("copy on root publication")), \
                     patch("OCP.BRepTools.BRepTools.Write_s", side_effect=AssertionError("BREP encode")), \
                     patch("OCP.BRepTools.BRepTools.Read_s", side_effect=AssertionError("BREP decode")):
                    child = tx.publish_result("child", authored_root, source_identity="compiled child",
                                              required_exports=("child.step",), unrepresented_metadata=())
                self.assertIs(tx._root, authored_root)
                self.assertTrue(frontend.active)
                self.assertAlmostEqual(shape.volume, 24.)
                moved = bd.Pos(12., 0., 0.) * shape
                parent_root = bind_returned_shape(frontend, moved)
                self.assertNotEqual(parent_root.transform, child.root.transform)
            parent = tx.commit()
        self.assertIs(document.head, parent)
        self.assertIs(document.entry_head("child"), child)
        self.assertEqual(parent.root.transform[3], 12.)
        self.assertEqual(child.root.transform[3], 0.)

    def test_publication_preserves_private_native_aliases_and_freezes_child_snapshot(self):
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.TopAbs import TopAbs_FACE, TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Pnt
        def vertex(native):
            return TopoDS.Vertex_s(TopExp_Explorer(native, TopAbs_VERTEX).Current())
        document = Document("family")
        tx = document.begin("parent")
        original = box(tx)
        face = tx.evaluate(OperatorSpec("test.family.first-face", "1", Mutation.READ_ONLY), (), (original,),
                           lambda inputs, arena: NativeResult(TopExp_Explorer(inputs[0], TopAbs_FACE).Current()))
        private_root = tx.escape_arena.native(original)
        private_face = tx.escape_arena.native(face)
        self.assertTrue(private_face.IsSame(TopExp_Explorer(private_root, TopAbs_FACE).Current()))
        original_point = BRep_Tool.Pnt_s(vertex(private_face)).Coord()
        snapshot = tx.capture(private_root)
        revision = publish(tx, snapshot)
        with document.pin(revision.revision_id) as pin:
            self.assertTrue(tx.escape_arena.native(original).IsSame(private_root))
            self.assertTrue(tx.escape_arena.native(face).IsSame(private_face))
            changed = (original_point[0] + 8., original_point[1], original_point[2])
            BRep_Builder().UpdateVertex(vertex(private_face), gp_Pnt(*changed), .01)
            self.assertEqual(BRep_Tool.Pnt_s(vertex(private_root)).Coord(), changed)
            saved_native = document._get(pin.revision.root.geometry).shape
            self.assertEqual(BRep_Tool.Pnt_s(vertex(saved_native)).Coord(), original_point)
            tx.abort()
            document.collect(keep_revisions=0)
            self.assertEqual(BRep_Tool.Pnt_s(vertex(document._get(snapshot).shape)).Coord(), original_point)

    def test_old_request_cannot_supersede_new_entry_with_a_later_snapshot_id(self):
        document = Document("family")
        older = document.begin("old parent", required_exports=("parent.step",))
        old_handle = box(older)
        newer = document.begin("new parent", required_exports=("parent.step",))
        new_handle = box(newer, 7.)
        accepted_child = publish(newer, new_handle)
        accepted_parent = newer.commit()
        with self.assertRaises(SupersededRevision) as rejected:
            publish(older, old_handle)
        stale_child = rejected.exception.revision
        self.assertGreater(stale_child.revision_id, accepted_child.revision_id)
        self.assertLess(stale_child._request_sequence, accepted_child._request_sequence)
        self.assertIs(document.entry_head("child"), accepted_child)
        self.assertFalse(older._closed)
        with document.pin(stale_child.revision_id) as pin:
            self.assertAlmostEqual(volume(document._get(pin.revision.root.geometry).shape), 24.)
            with self.assertRaises(ExportConflict):
                document.publish_export(pin, "child.step", lambda: self.fail("old child save"))
        with self.assertRaises(SupersededRevision):
            older.commit()
        self.assertIs(document.head, accepted_parent)

    def test_late_old_entry_cannot_lower_another_entries_output_claim(self):
        document = Document("family")
        older = document.begin("old request")
        old_handle = box(older)
        newer = document.begin("new request")
        accepted = publish(newer, box(newer, 7.), entry="new-entry", path="shared.step")
        newer.abort()
        older_result = publish(older, old_handle, entry="old-entry", path="shared.step")
        self.assertGreater(older_result.revision_id, accepted.revision_id)
        with document.pin(older_result.revision_id) as pin:
            with self.assertRaises(ExportConflict):
                document.publish_export(pin, "shared.step", lambda: self.fail("old entry save"))
        with document.pin(accepted.revision_id) as pin:
            self.assertEqual(document.publish_export(pin, "shared.step", lambda: "new bytes"), "new bytes")
        older.abort()

    def test_parent_output_follows_child_even_with_an_earlier_reserved_revision_id(self):
        document = Document("family")
        with document.begin("parent", required_exports=("shared.step",)) as tx:
            child = publish(tx, box(tx), path="shared.step")
            with document.pin(child.revision_id) as child_pin:
                document.publish_export(child_pin, "shared.step", lambda: "child bytes")
                tx.bind_root(GeometryLeaf("parent", box(tx, 9.)))
                parent = tx.commit()
                self.assertLess(parent.revision_id, child.revision_id)
                with document.pin(parent.revision_id) as parent_pin:
                    self.assertEqual(document.publish_export(parent_pin, "shared.step", lambda: "parent bytes"), "parent bytes")
                with self.assertRaises(ExportConflict):
                    document.publish_export(child_pin, "shared.step", lambda: self.fail("child overwrote parent"))

    def test_entry_heads_and_exact_pins_control_child_collection(self):
        document = Document("family")
        tx = document.begin("first parent")
        first_handle = box(tx)
        first = tx.publish_result("child", GeometryLeaf("child", first_handle), source_identity="first",
                                  required_exports=(), unrepresented_metadata=())
        pin = document.pin(first.revision_id)
        tx.abort()
        tx = document.begin("second parent")
        second = tx.publish_result("child", GeometryLeaf("child", box(tx, 7.)), source_identity="second",
                                   required_exports=(), unrepresented_metadata=())
        tx.abort()
        document.collect(keep_revisions=0)
        self.assertIs(document.entry_head("child"), second)
        with document.pin(first.revision_id) as selected:
            self.assertIs(selected.revision, first)
        # Release the remaining lease; the replaced child can now be collected.
        pin.release()
        document.collect(keep_revisions=0)
        with self.assertRaises(KeyError):
            document.pin(first.revision_id)
        with self.assertRaises(ValueError):
            document._get(first_handle)
        self.assertIsNone(document.head)
        self.assertIs(document.entry_head("child"), second)

    def test_invalid_child_binding_is_atomic_and_does_not_poison_parent(self):
        document = Document("family")
        with document.begin("parent") as tx:
            root = GeometryLeaf("parent", box(tx))
            tx.bind_root(root, unrepresented_metadata=())
            for changes in ({"entry_key": ""}, {"source_identity": None},
                            {"required_exports": ["child.step"]}, {"unrepresented_metadata": ["cad_material"]}):
                args = dict(entry_key="child", root=root, source_identity="compiled child",
                            required_exports=("child.step",), unrepresented_metadata=())
                args.update(changes)
                with self.assertRaises((TypeError, ValueError)):
                    tx.publish_result(**args)
                self.assertIs(tx._root, root)
                self.assertIsNone(document.entry_head("child"))
                self.assertEqual(len(document._revisions), 0)
            parent = tx.commit()
        self.assertIs(document.head, parent)


if __name__ == "__main__":
    unittest.main()
