"""Efficient native history traversal retains exact correspondence evidence."""
import unittest
from unittest.mock import patch

from cadgen._document.native import _history_targets, history_from_builder


class NativeHistoryTests(unittest.TestCase):
    def test_history_lists_keep_order_duplicates_and_borrowed_contents(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.TopTools import TopTools_ListOfShape

        first = BRepPrimAPI_MakeBox(1, 2, 3).Shape()
        second = BRepPrimAPI_MakeBox(2, 3, 4).Shape()
        for expected in ((), (first,), (first, second, first)):
            with self.subTest(count=len(expected)):
                values = TopTools_ListOfShape()
                for shape in expected:
                    values.Append(shape)
                with patch.object(TopTools_ListOfShape, "__iter__",
                                  side_effect=AssertionError("expensive native list iterator")):
                    actual = tuple(_history_targets(values))
                self.assertEqual(len(actual), len(expected))
                self.assertTrue(all(a.IsSame(b) for a, b in zip(actual, expected)))
                # Builder-owned history remains available for subsequent reads.
                self.assertEqual(values.Extent(), len(expected))
                retained = tuple(values)
                self.assertTrue(all(a.IsSame(b) for a, b in zip(retained, expected)))

    def test_boolean_and_fillet_history_match_binding_iterator_exactly(self):
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.TopTools import TopTools_ListOfShape
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

        base = BRepPrimAPI_MakeBox(10, 8, 2).Shape()
        tool = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(5, 4, -1), gp_Dir(0, 0, 1)), 1, 4).Shape()
        args, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
        args.Append(base)
        tools.Append(tool)
        boolean = BRepAlgoAPI_Cut()
        boolean.SetArguments(args)
        boolean.SetTools(tools)
        boolean.SetNonDestructive(True)
        boolean.Build()
        fillet = BRepFilletAPI_MakeFillet(base)
        fillet.Add(.2, TopoDS.Edge_s(TopExp_Explorer(base, TopAbs_EDGE).Current()))
        fillet.Build()
        for builder, inputs in ((boolean, (base, tool)), (fillet, (base,))):
            with self.subTest(builder=type(builder).__name__):
                self.assertTrue(builder.IsDone())
                with patch("cadgen._document.native._history_targets", side_effect=iter):
                    reference = history_from_builder(builder, inputs)
                with patch.object(TopTools_ListOfShape, "__iter__",
                                  side_effect=AssertionError("expensive native list iterator")):
                    actual = history_from_builder(builder, inputs)
                self.assertEqual(actual, reference)
                self.assertTrue(actual.complete, actual.reason)
                self.assertTrue(actual.modified)
                self.assertTrue(actual.unchanged)


if __name__ == "__main__":
    unittest.main()
