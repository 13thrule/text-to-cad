"""Closed primitives remain independent of earlier opaque family execution."""
from __future__ import annotations

from functools import wraps
import inspect
import math
import unittest
from unittest.mock import patch

from cadgen import build123d as bd
from cadgen._document import Document, Mutation, NativeResult, OperatorSpec
from cadgen._document.frontend import FrontendSession, _state
from cadgen._document.roots import GeometryLeaf


def first_vertex(native):
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    return TopoDS.Vertex_s(TopExp_Explorer(native, TopAbs_VERTEX).Current())


def vertex_x(native):
    from OCP.BRep import BRep_Tool
    return BRep_Tool.Pnt_s(first_vertex(native)).X()


def set_vertex_x(native, value):
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.gp import gp_Pnt
    vertex = first_vertex(native)
    before = BRep_Tool.Pnt_s(vertex)
    BRep_Builder().UpdateVertex(vertex, gp_Pnt(value, before.Y(), before.Z()), .01)


class EscapeIndependenceTests(unittest.TestCase):
    def setUp(self):
        from cadgen._internal import op_memo
        installed = op_memo._installed
        if installed:
            op_memo.uninstall()
        self.addCleanup(op_memo.install if installed else lambda: None)

    def test_closed_contract_is_explicit_and_excludes_geometry_inputs(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        self.assertFalse(OperatorSpec("ordinary").closed_constructor)
        with self.assertRaises(ValueError):
            OperatorSpec("not-read-only", closed_constructor=True)
        with self.assertRaises(TypeError):
            OperatorSpec("not-a-bool", closed_constructor=1)
        closed = OperatorSpec("closed", mutation=Mutation.READ_ONLY, closed_constructor=True)
        with Document("closed-contract").begin() as tx:
            constructor = lambda inputs, arena: NativeResult(BRepPrimAPI_MakeBox(2., 3., 4.).Shape())
            handle = tx.evaluate(closed, (), (), constructor)
            with self.assertRaisesRegex(ValueError, "cannot consume geometry handles"):
                tx.evaluate(closed, (), (handle,), constructor)
            conservative = tx.evaluate(OperatorSpec("closed", mutation=Mutation.READ_ONLY),
                                       (), (), constructor)
            self.assertNotEqual(handle.evaluation_id, conservative.evaluation_id)

    def test_default_zero_input_native_callback_replays_and_preserves_aliases(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        document = Document("opaque-native-global")
        calls = []
        for turn in range(2):
            external = BRepPrimAPI_MakeBox(2., 3., 4.).Shape()
            with document.begin() as tx:
                seed = tx.capture(external)
                tx.escape_arena.native(seed)
                def authored(inputs, arena):
                    calls.append(vertex_x(external))
                    return NativeResult(external)
                first = tx.evaluate(OperatorSpec("authored-native"), (), (), authored)
                retained = vertex_x(document._get(first).shape)
                set_vertex_x(external, 20. + turn)
                second = tx.evaluate(OperatorSpec("authored-native"), (), (), authored)
                self.assertNotEqual(first.evaluation_id, second.evaluation_id)
                self.assertEqual(retained, vertex_x(document._get(first).shape))
                self.assertEqual(20. + turn, tx.query(first, vertex_x))
                self.assertEqual(20. + turn, tx.query(second, vertex_x))
                self.assertEqual(0, tx.stats.reused)
                tx.commit()
        self.assertEqual([0., 20., 0., 21.], calls)

    def test_published_opaque_child_does_not_poison_later_box_and_cylinder(self):
        document = Document("child-then-primitives")
        prior = None
        for turn in range(3):
            with document.begin() as tx:
                with FrontendSession(tx) as frontend:
                    child = bd.Box(2, 3, 4)
                    native_child = child.wrapped
                    child_handle = frontend._geometry_handle(child)
                    tx.publish_result("child", GeometryLeaf("child", child_handle),
                                      source_identity=f"ordinary replay {turn}",
                                      required_exports=(), unrepresented_metadata=())
                    before = tx.stats.native_copies
                    box = bd.Box(30, 20, 6)
                    cylinder = bd.Cylinder(2, 10)
                    handles = (_state(box).handle, _state(cylinder).handle)
                    self.assertTrue(tx.escape_arena.active)
                    # A closed result does not get adopted from a mutable
                    # callback or copied until its own native access is needed.
                    self.assertEqual(before, tx.stats.native_copies)
                    if prior is not None:
                        self.assertEqual(tuple(h.evaluation_id for h in prior),
                                         tuple(h.evaluation_id for h in handles))
                        self.assertTrue(all(a.allocation_id != b.allocation_id
                                            for a, b in zip(prior, handles)))
                        self.assertGreaterEqual(tx.stats.reused, 3)
                    prior = handles
                    set_vertex_x(native_child, 80. + turn)
                    self.assertEqual(80. + turn, vertex_x(child.wrapped))
                    self.assertAlmostEqual(3600., box.volume)
                    self.assertAlmostEqual(40. * math.pi, cylinder.volume)
                    result = box - cylinder
                    self.assertAlmostEqual(3600. - 24. * math.pi, result.volume, places=7)
                tx.commit()

    def test_selector_callback_runs_each_time_before_independent_primitives(self):
        calls = []
        document = Document("callback-then-primitives")
        for turn in range(2):
            with document.begin() as tx:
                with FrontendSession(tx):
                    observer = bd.Box(2, 3, 4)
                    observer.faces().filter_by(lambda face: calls.append(face.area) or True)
                    before = tx.stats.reused
                    box, cylinder = bd.Box(5, 6, 7), bd.Cylinder(2, 3)
                    self.assertEqual(2 if turn else 0, tx.stats.reused - before)
                    self.assertAlmostEqual(210., box.volume)
                    self.assertAlmostEqual(12. * math.pi, cylinder.volume)
                tx.commit()
        self.assertEqual(12, len(calls))
        self.assertEqual(sorted(calls[:6]), sorted(calls[6:]))

    def test_closed_hits_after_escape_never_share_mutable_native_allocations(self):
        document = Document("independent-after-escape")
        for _ in range(2):
            with document.begin() as tx:
                with FrontendSession(tx):
                    observer = bd.Box(2, 3, 4)
                    observer.wrapped
                    first, second = bd.Box(4, 5, 6), bd.Box(4, 5, 6)
                    a, b = _state(first).handle, _state(second).handle
                    self.assertEqual(a.prototype_id, b.prototype_id)
                    self.assertNotEqual(a.allocation_id, b.allocation_id)
                    first_native, second_native = first.wrapped, second.wrapped
                    self.assertFalse(first_native.IsSame(second_native))
                    original = vertex_x(second_native)
                    set_vertex_x(first_native, 99.)
                    self.assertEqual(99., vertex_x(first.wrapped))
                    self.assertEqual(original, vertex_x(second_native))
                    self.assertEqual(original, vertex_x(document._get(a).shape))
                tx.commit()

    def test_input_dependent_operators_remain_volatile_and_observe_mutation(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        document = Document("dependent-stays-volatile")
        closed = OperatorSpec("closed-box", mutation=Mutation.READ_ONLY, closed_constructor=True)
        select = OperatorSpec("dependent-face", mutation=Mutation.READ_ONLY)
        with document.begin() as tx:
            shape = tx.evaluate(closed, (), (), lambda inputs, arena:
                                NativeResult(BRepPrimAPI_MakeBox(2., 3., 4.).Shape()))
            def face(inputs, arena):
                return NativeResult(TopExp_Explorer(inputs[0], TopAbs_FACE).Current())
            first = tx.evaluate(select, (), (shape,), face)
            escaped = tx.escape_arena.native(shape)
            set_vertex_x(escaped, 50.)
            second = tx.evaluate(select, (), (shape,), face)
            self.assertNotEqual(first.evaluation_id, second.evaluation_id)
            self.assertEqual(50., tx.query(second, vertex_x))
            self.assertEqual(0., vertex_x(document._get(shape).shape))

    def test_authored_make_box_before_or_during_session_runs_once_per_call(self):
        descriptor = inspect.getattr_static(bd.Solid, "make_box")
        for timing in ("before", "during"):
            document = Document(f"authored-provider-{timing}")
            calls = []
            for turn in range(2):
                @wraps(descriptor.__func__)
                def authored(cls, length, width, height):
                    calls.append(turn)
                    return descriptor.__func__(cls, length + turn, width, height)
                provider = patch.object(bd.Solid, "make_box", classmethod(authored))
                if timing == "before":
                    provider.start()
                try:
                    with document.begin() as tx:
                        with FrontendSession(tx):
                            observer = bd.Cylinder(1, 2)
                            observer.wrapped
                            if timing == "during":
                                provider.start()
                            try:
                                result = bd.Box(2, 3, 4)
                                self.assertAlmostEqual((2 + turn) * 12., result.volume)
                            finally:
                                if timing == "during":
                                    provider.stop()
                        tx.commit()
                finally:
                    if timing == "before":
                        provider.stop()
            self.assertEqual([0, 1], calls)

    def test_replaced_native_factory_observes_escaped_global_every_time(self):
        descriptor = inspect.getattr_static(bd.Solid, "make_box")
        namespace = descriptor.__func__.__globals__
        stock = namespace["BRepPrimAPI_MakeBox"]
        for timing in ("before", "during"):
            document = Document(f"native-global-{timing}")
            calls = []
            for turn in range(2):
                # This provider returns geometry derived from a raw native
                # global, which is absent from Box's declared dimensions.
                external = stock(2., 3., 4.).Shape()
                set_vertex_x(external, 5. + turn)
                def authored(axes, length, width, height):
                    calls.append(vertex_x(external))
                    return stock(axes, vertex_x(external), width, height)
                replacement = patch.dict(namespace, {"BRepPrimAPI_MakeBox": authored})
                if timing == "before":
                    replacement.start()
                try:
                    with document.begin() as tx:
                        with FrontendSession(tx):
                            observer = bd.Cylinder(1, 2)
                            observer.wrapped
                            if timing == "during":
                                replacement.start()
                            try:
                                result = bd.Box(2, 3, 4)
                                self.assertAlmostEqual((5. + turn) * 12., result.volume)
                            finally:
                                if timing == "during":
                                    replacement.stop()
                        tx.commit()
                finally:
                    if timing == "before":
                        replacement.stop()
            self.assertEqual([5., 6.], calls)

    def test_algebraic_validation_hook_replays_in_normal_escape_context(self):
        from build123d import objects_part
        stock = objects_part.validate_inputs
        calls = []
        document = Document("algebraic-validation")
        for turn in range(2):
            with document.begin() as tx:
                with FrontendSession(tx):
                    observer = bd.Box(2, 3, 4)
                    def authored(context, value):
                        calls.append(observer._wrapped is not None)
                        return stock(context, value)
                    with patch.object(objects_part, "validate_inputs", authored):
                        result = bd.Box(6, 7, 8)
                    self.assertAlmostEqual(336., result.volume)
                tx.commit()
        self.assertEqual([True, True], calls)

    def test_native_provider_method_hook_is_not_a_closed_constructor(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        stock = inspect.getattr_static(BRepPrimAPI_MakeBox, "Shape")
        calls = []
        document = Document("native-method-hook")
        def authored(builder):
            calls.append("Shape")
            return stock(builder)
        with patch.object(BRepPrimAPI_MakeBox, "Shape", authored):
            for _ in range(2):
                with document.begin() as tx:
                    with FrontendSession(tx):
                        observer = bd.Cylinder(1, 2)
                        observer.wrapped
                        result = bd.Box(2, 3, 4)
                        self.assertAlmostEqual(24., result.volume)
                    tx.commit()
        self.assertEqual(["Shape", "Shape"], calls)

    def test_builder_native_primitives_reuse_after_unrelated_escape(self):
        document = Document("builder-after-escape")
        calls = []
        for turn in range(2):
            with document.begin() as tx:
                with FrontendSession(tx):
                    observer = bd.Box(2, 3, 4)
                    observer.wrapped
                    with bd.BuildPart() as part:
                        validate = part.validate_inputs
                        def authored(*args, **kwargs):
                            calls.append(observer._wrapped is not None)
                            return validate(*args, **kwargs)
                        part.validate_inputs = authored
                        before = tx.stats.reused
                        bd.Box(10, 8, 4)
                        bd.Cylinder(2, 6, mode=bd.Mode.SUBTRACT)
                        self.assertEqual(2 if turn else 0, tx.stats.reused - before)
                    self.assertAlmostEqual(320. - 16. * math.pi, part.part.volume, places=7)
                tx.commit()
        self.assertEqual([True] * 4, calls)

    def test_factory_default_placement_is_an_actual_construction_input(self):
        descriptor = inspect.getattr_static(bd.Solid, "make_box")
        document = Document("factory-default-plane")
        for plane in (bd.Plane.XY, bd.Plane.XZ, bd.Plane.XY):
            with patch.object(descriptor.__func__, "__defaults__", (plane,)):
                expected = bd.Box(2, 3, 4).bounding_box().size
                with document.begin() as tx:
                    with FrontendSession(tx):
                        observer = bd.Cylinder(1, 2)
                        observer.wrapped
                        result = bd.Box(2, 3, 4)
                        self.assertEqual(tuple(expected), tuple(result.bounding_box().size))
                    tx.commit()


if __name__ == "__main__":
    unittest.main()
