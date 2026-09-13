"""Stock topology ordering, analytic values and private alias boundaries."""
from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

import build123d as bd

from cadgen._document import Document
from cadgen._document.frontend import FrontendSession, _state


def _bounds(shape):
    box = shape.bounding_box()
    return tuple(round(value, 7) for value in (*box.min, *box.max))


def _circle_facts(edges):
    facts = []
    for edge in edges:
        kind = edge.geom_type
        if kind is bd.GeomType.CIRCLE:
            facts.append((kind, edge.radius, tuple(edge.arc_center), tuple(edge.normal()),
                          _bounds(edge)))
        else:
            facts.append((kind, _bounds(edge)))
    return facts


class SelectionTests(unittest.TestCase):
    def setUp(self):
        from cadgen._internal import op_memo
        installed = op_memo._installed
        if installed:
            op_memo.uninstall()
        self.addCleanup(op_memo.install if installed else lambda: None)

    def test_rotated_circle_queries_and_order_reuse_without_escape(self):
        def model():
            return bd.Cylinder(2, 7).moved(bd.Pos(5, 8, 11) * bd.Rot(23, 41, 17))
        expected = _circle_facts(model().edges())
        document = Document("ordered-circle-queries")
        for turn in range(2):
            with document.begin() as tx:
                with FrontendSession(tx) as frontend:
                    part = model()
                    self.assertEqual(expected, _circle_facts(part.edges()))
                    self.assertFalse(_state(part).private)
                    self.assertFalse(tx.escape_arena.active)
                    self.assertEqual(0, tx.stats.native_copies)
                    if turn:
                        self.assertEqual(0, tx.stats.computed)
                        self.assertGreater(tx.stats.reused, 0)
                self.assertIsNone(frontend._selection._carrier)
                tx.commit()

    def test_stock_indices_slices_types_and_fresh_wrapper_identity(self):
        stock = bd.Box(2, 3, 4).edges()
        with Document("selection-index").begin() as tx:
            with FrontendSession(tx):
                part = bd.Box(2, 3, 4)
                selection = part.edges()
                for index in (0, -1, True, False, slice(None), slice(None, None, -1),
                              slice(1, -1, 2), slice(30), slice(8, 3)):
                    actual, expected = selection[index], stock[index]
                    if type(index) is slice:
                        self.assertIs(type(actual), bd.ShapeList)
                        self.assertEqual([_bounds(item) for item in expected],
                                         [_bounds(item) for item in actual])
                        self.assertTrue(all(item.topo_parent is part for item in actual))
                    else:
                        self.assertIs(type(actual), bd.Edge)
                        self.assertEqual(_bounds(expected), _bounds(actual))
                        self.assertIs(actual.topo_parent, part)
                self.assertIsNot(selection[0], selection[0])
                for index in (100, -100, slice(None, None, 0)):
                    with self.assertRaises((IndexError, ValueError)) as expected:
                        stock[index]
                    with self.assertRaises(type(expected.exception)) as actual:
                        selection[index]
                    self.assertEqual(str(expected.exception), str(actual.exception))
                self.assertEqual(0, tx.stats.native_copies)

    def test_stock_degenerate_exclusion_and_topology_parent(self):
        stock = bd.Sphere(3)
        expected = {kind: [_bounds(item) for item in getattr(stock, kind)()]
                    for kind in ("edges", "faces", "vertices", "solids")}
        with Document("degenerate-selection").begin() as tx:
            handle = tx.capture(stock.wrapped)
            with FrontendSession(tx) as frontend:
                owner = object.__new__(bd.Solid)
                frontend._init_empty(owner, "sphere", handle)
                for kind in expected:
                    members = list(getattr(owner, kind)())
                    self.assertEqual(expected[kind], [_bounds(item) for item in members])
                    self.assertTrue(all(item.topo_parent is owner for item in members))
                edge = owner.edges()[0]
                self.assertTrue(all(vertex.topo_parent is owner for vertex in edge.vertices()))
                self.assertFalse(tx.escape_arena.active)

    def test_ellipse_vectors_are_fresh_values_and_metadata_matches_stock(self):
        stock = bd.Edge.make_ellipse(7, 3)
        expected = (tuple(stock.arc_center), tuple(stock.normal()))
        with Document("ellipse-values").begin() as tx:
            handle = tx.capture(stock.wrapped)
            with FrontendSession(tx) as frontend:
                owner = object.__new__(bd.Edge)
                frontend._init_empty(owner, "ellipse", handle)
                edge = owner.edges()[0]
                self.assertEqual(bd.GeomType.ELLIPSE, edge.geom_type)
                center = edge.arc_center
                center.X = 123
                self.assertEqual(expected, (tuple(edge.arc_center), tuple(edge.normal())))
                self.assertFalse(tx.escape_arena.active)
                raw = object.__getattribute__(edge, "__dict__")
                self.assertNotIn("material", raw)
                self.assertNotIn("joints", raw)
                with self.assertRaises(ValueError) as expected_error:
                    stock.radius
                with self.assertRaises(ValueError) as actual_error:
                    edge.radius
                self.assertEqual(str(expected_error.exception), str(actual_error.exception))

    def test_lazy_query_auditor_rejects_mutation_after_warm_entry(self):
        document = Document("lazy-selection-audit")
        with document.begin() as tx:
            with FrontendSession(tx) as frontend:
                bd.Cylinder(2, 3).edges()[0].radius
                self.assertTrue(frontend._selection.providers_match())
            tx.commit()
        with document.begin() as tx:
            with FrontendSession(tx) as frontend:
                self.assertIsNotNone(frontend._selection.stock)
                self.assertTrue(frontend._selection.query_providers_match("radius"))
                part = bd.Cylinder(2, 3)
                original = bd.Edge.geom_adaptor
                observed = []
                def adaptor(edge):
                    observed.append(_state(part).private)
                    return original(edge)
                with patch.object(bd.Edge, "geom_adaptor", adaptor):
                    self.assertEqual(2, part.edges()[0].radius)
                self.assertTrue(observed)
                self.assertTrue(all(observed))

    def test_scalar_query_rejects_preentry_adaptor_alias_replacement(self):
        from build123d.topology import one_d

        document = Document("selection-preentry-alias-proof")
        with document.begin() as tx:
            with FrontendSession(tx):
                edge = bd.Cylinder(2, 3).edges()[0]
                self.assertEqual(2, edge.radius)
                retained = tx.document._get(_state(edge).handle).shape
            tx.commit()

        original = one_d.BRepAdaptor_Curve
        observed = []
        current = [None]
        class AuthoredCurve:
            def __new__(cls, native):
                frontend = current[0]
                observed.append(
                    (_state(edge).private, frontend._compute_depth,
                     native.IsSame(retained)))
                return original(native)

        with patch.object(one_d, "BRepAdaptor_Curve", AuthoredCurve):
            with document.begin() as tx:
                with FrontendSession(tx) as frontend:
                    current[0] = frontend
                    self.assertFalse(
                        frontend._selection.query_providers_match("radius"))
                    self.assertEqual(2, edge.radius)
                tx.commit()
        self.assertEqual([(True, 0, False)], observed)

    def test_scalar_query_uses_its_live_proof_without_full_builder_revalidation(self):
        with Document("narrow-selection-proof").begin() as tx:
            with FrontendSession(tx) as frontend:
                edge = bd.Cylinder(2, 3).edges()[0]
                stock = frontend._selection.stock
                self.assertIsNotNone(stock)
                with patch.object(
                        stock, "providers_match",
                        side_effect=AssertionError("scalar query used the full builder proof")):
                    self.assertEqual(2, edge.radius)
                self.assertFalse(_state(edge).private)
                self.assertFalse(tx.escape_arena.active)

    def test_scalar_query_rechecks_original_function_body_on_every_call(self):
        with Document("selection-function-body-proof").begin() as tx:
            with FrontendSession(tx) as frontend:
                edge = bd.Cylinder(2, 3).edges()[0]
                self.assertEqual(2, edge.radius)
                function = frontend._selection.original["radius"].fget
                namespace = function.__globals__
                observed = []
                namespace["_cadgen_test_observed"] = observed
                namespace["_cadgen_test_state"] = _state
                def changed(shape):
                    _cadgen_test_observed.append(
                        (_cadgen_test_state(shape).private, shape.wrapped is not None))
                    return 31
                code = function.__code__
                try:
                    function.__code__ = changed.__code__
                    self.assertEqual(31, edge.radius)
                finally:
                    function.__code__ = code
                    namespace.pop("_cadgen_test_observed", None)
                    namespace.pop("_cadgen_test_state", None)
                self.assertEqual([(True, True)], observed)

    def test_scalar_query_avoids_part_cast_and_rejects_concrete_wrapped_shadow(self):
        with Document("selection-minimal-edge-view").begin() as tx:
            with FrontendSession(tx) as frontend:
                edge = bd.Cylinder(2, 3).edges()[0]
                retained = tx.document._get(_state(edge).handle).shape
                cast_calls = []
                def cast(native):
                    cast_calls.append(native)
                    return bd.Edge(native)
                with patch.object(bd.Part, "cast", staticmethod(cast)):
                    self.assertEqual(2, edge.radius)
                self.assertEqual([], cast_calls)
                self.assertFalse(_state(edge).private)

                wrapped = inspect.getattr_static(bd.Edge, "wrapped")
                observed = []
                def authored(shape):
                    native = wrapped.fget(shape)
                    observed.append(
                        (_state(shape).private, frontend._compute_depth,
                         native.IsSame(retained)))
                    return native
                with patch.object(
                        bd.Edge, "wrapped", property(authored, wrapped.fset)):
                    self.assertEqual(2, edge.radius)
                self.assertEqual([(True, 0, False)], observed)

    def test_scalar_query_rejects_native_attribute_dispatch_replacement(self):
        from OCP.BRepAdaptor import BRepAdaptor_Curve

        with Document("selection-native-dispatch-proof").begin() as tx:
            with FrontendSession(tx) as frontend:
                edge = bd.Cylinder(2, 3).edges()[0]
                retained = tx.document._get(_state(edge).handle).shape
                self.assertEqual(2, edge.radius)
                getattribute = inspect.getattr_static(
                    BRepAdaptor_Curve, "__getattribute__")
                observed = []
                def authored(adaptor, name):
                    if name == "GetType":
                        native = getattribute(adaptor, "Edge")()
                        observed.append(
                            (_state(edge).private, frontend._compute_depth,
                             native.IsSame(retained)))
                    return getattribute(adaptor, name)
                with patch.object(BRepAdaptor_Curve, "__getattribute__", authored):
                    self.assertEqual(2, edge.radius)
                self.assertEqual([(True, 0, False)], observed)

    def test_scalar_query_downcasts_a_generic_captured_edge_without_escape(self):
        stock = bd.Edge.make_circle(3)
        with Document("selection-generic-edge-root").begin() as tx:
            handle = tx.capture(stock.wrapped)
            with FrontendSession(tx) as frontend:
                edge = object.__new__(bd.Edge)
                frontend._init_empty(edge, "generic-edge", handle)
                self.assertEqual(3, edge.radius)
                self.assertEqual(tuple(stock.arc_center), tuple(edge.arc_center))
                self.assertFalse(_state(edge).private)
                self.assertFalse(tx.escape_arena.active)

    def test_query_value_constructor_descriptor_and_subclass_escape(self):
        for kind in ("descriptor", "subclass"):
            with Document("query-value-" + kind).begin() as tx:
                with FrontendSession(tx):
                    edge = bd.Cylinder(2, 3).edges()[0]
                    observed = []
                    if kind == "descriptor":
                        def assign(vector, value):
                            observed.append(_state(edge).private)
                            object.__getattribute__(vector, "__dict__")["_index"] = value
                        with patch.object(bd.Vector, "vector_index", property(fset=assign), create=True):
                            edge.arc_center
                    else:
                        class CustomEdge(bd.Edge):
                            def normal(self):
                                observed.append(_state(self).private)
                                return super().normal()
                        edge.__class__ = CustomEdge
                        edge.normal()
                    self.assertEqual([True], observed)

    def test_projection_scans_one_carrier_and_cache_clears_at_escape(self):
        with Document("selection-carrier").begin() as tx:
            with FrontendSession(tx) as frontend:
                part = bd.Box(2, 3, 4)
                with patch.object(frontend, "_native_call", wraps=frontend._native_call) as scan:
                    members = list(part.edges())
                    self.assertEqual(1, scan.call_count)
                self.assertEqual(12, len(members))
                members[0].wrapped
                self.assertIsNone(frontend._selection._carrier)

    def test_projected_vertex_mutation_updates_private_family_only(self):
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.gp import gp_Pnt
        from OCP.TopoDS import TopoDS
        from cadgen._document.native import topology_map

        document = Document("selection-mutation")
        for turn in range(2):
            with document.begin() as tx:
                with FrontendSession(tx) as frontend:
                    part = bd.Box(2, 3, 4)
                    independent = bd.Box(2, 3, 4)
                    edges = list(part.edges())
                    vertex = edges[0].vertices()[0]
                    retained = document._get(_state(vertex).handle).shape
                    before = BRep_Tool.Pnt_s(TopoDS.Vertex(retained)).X()
                    self.assertNotEqual(99., before)
                    if not turn:
                        raw = vertex.wrapped
                        BRep_Builder().UpdateVertex(raw, gp_Pnt(99., 2., 3.), .01)
                        private_parent = part.wrapped
                        private_edge = edges[0].wrapped
                        self.assertTrue(topology_map(private_parent).Contains(raw))
                        self.assertTrue(topology_map(private_edge).Contains(raw))
                        self.assertEqual(99., BRep_Tool.Pnt_s(raw).X())
                        self.assertEqual(before, BRep_Tool.Pnt_s(TopoDS.Vertex(retained)).X())
                        self.assertFalse(topology_map(independent.wrapped).Contains(raw))
                    frontend.materialize(part)
                tx.commit()

    def test_iterator_snapshot_survives_parent_replacement_and_edge_move(self):
        stock = bd.Box(2, 3, 4)
        expected = [_bounds(edge) for edge in stock.edges()]
        with Document("selection-snapshot").begin() as tx:
            with FrontendSession(tx):
                part = bd.Box(2, 3, 4)
                iterator = iter(part.edges())
                first = next(iterator)
                first.move(bd.Pos(10, 0, 0))
                self.assertEqual(expected, [_bounds(edge) for edge in part.edges()])
                part.wrapped = bd.Box(8, 9, 10).wrapped
                self.assertEqual(expected[1:], [_bounds(edge) for edge in iterator])
                self.assertIs(first.topo_parent, part)
                self.assertNotEqual(expected[0], _bounds(first))

    def test_radius_and_arc_center_exceptions_match_stock_without_escape(self):
        stock = bd.Box(2, 3, 4).edges()[0]
        with Document("selection-exceptions").begin() as tx:
            with FrontendSession(tx):
                edge = bd.Box(2, 3, 4).edges()[0]
                for name in ("radius", "arc_center"):
                    with self.assertRaises(ValueError) as expected:
                        getattr(stock, name)
                    with self.assertRaises(ValueError) as actual:
                        getattr(edge, name)
                    self.assertEqual(str(expected.exception), str(actual.exception))
                self.assertEqual(0, tx.stats.native_copies)
                self.assertEqual(tuple(stock.normal()), tuple(edge.normal()))
                self.assertTrue(_state(edge).private)

    def test_custom_index_and_filter_callbacks_execute_privately_each_replay(self):
        observations = []
        document = Document("selection-callbacks")
        for turn in range(2):
            with document.begin() as tx:
                with FrontendSession(tx):
                    part = bd.Box(2, 3, 4)
                    class Index:
                        def __index__(self):
                            observations.append((turn, "index", _state(part).private))
                            return -1
                    self.assertIs(type(part.edges()[Index()]), bd.Edge)
                    part.edges().filter_by(lambda edge: observations.append(
                        (turn, "filter", edge.wrapped is not None)) or True)
                tx.commit()
        self.assertEqual([(turn, "index", True) for turn in range(2)],
                         [item for item in observations if item[1] == "index"])
        self.assertEqual(24, sum(item[1] == "filter" for item in observations))

    def test_replaced_descriptor_and_instance_method_see_private_wrapper(self):
        for replacement in ("property", "instance"):
            with Document("selection-descriptor-" + replacement).begin() as tx:
                with FrontendSession(tx):
                    edge = bd.Cylinder(2, 3).edges()[0]
                    observed = []
                    def author(shape):
                        observed.append((_state(shape).private, shape.wrapped is not None))
                        return 17
                    if replacement == "property":
                        with patch.object(bd.Edge, "radius", property(author)):
                            self.assertEqual(17, edge.radius)
                    else:
                        edge.normal = lambda: author(edge)
                        self.assertEqual(17, edge.normal())
                    self.assertEqual([(True, True)], observed)

    def test_captured_method_rechecks_native_provider_and_mutable_lut(self):
        from OCP.gp import gp_Circ
        for replacement in ("native", "lut"):
            with Document("selection-provider-" + replacement).begin() as tx:
                with FrontendSession(tx):
                    edge = bd.Cylinder(2, 3).edges()[0]
                    method = edge.normal
                    if replacement == "native":
                        original = gp_Circ.Axis
                        observed = []
                        def axis(shape):
                            observed.append(_state(edge).private)
                            return original(shape)
                        with patch.object(gp_Circ, "Axis", axis):
                            method()
                        self.assertEqual([True], observed)
                    else:
                        table = bd.Shape.geom_LUT_EDGE
                        key = next(key for key, value in table.items() if value is bd.GeomType.CIRCLE)
                        old = table[key]
                        try:
                            table[key] = bd.GeomType.LINE
                            with self.assertRaises(ValueError):
                                edge.arc_center
                            self.assertTrue(_state(edge).private)
                        finally:
                            table[key] = old

    def test_custom_shapelist_iteration_runs_after_private_transition(self):
        with Document("selection-list-provider").begin() as tx:
            with FrontendSession(tx):
                part = bd.Box(2, 3, 4)
                observed = []
                original = bd.ShapeList.__iter__
                def iterate(values):
                    observed.append(_state(part).private)
                    return original(values)
                with patch.object(bd.ShapeList, "__iter__", iterate):
                    self.assertEqual(12, len(list(part.edges())))
                self.assertTrue(observed)
                self.assertTrue(all(observed))

    def test_preentry_query_descriptor_replacement_preserves_ordinary_access(self):
        for owner, name, replacement in ((bd.Edge, "arc_center", 17),
                                          (bd.topology.Mixin1D, "normal", property(lambda edge: 19))):
            with patch.object(owner, name, replacement):
                with Document("selection-preentry-" + name).begin() as tx:
                    with FrontendSession(tx) as frontend:
                        part = bd.Cylinder(2, 3)
                        edge = part.edges()[0]
                        self.assertFalse(frontend._selection.providers_match())
                        self.assertEqual(17 if name == "arc_center" else 19, getattr(edge, name))
                        self.assertTrue(_state(part).private)

    def test_enum_comparison_and_downcast_callbacks_cannot_borrow_retained_native(self):
        for name in ("enum", "downcast"):
            with Document("selection-hidden-provider-" + name).begin() as tx:
                with FrontendSession(tx) as frontend:
                    edge = bd.Cylinder(2, 3).edges()[0]
                    observed = []
                    if name == "enum":
                        original = bd.GeomType.__eq__
                        def equal(left, right):
                            observed.append((_state(edge).private, frontend._compute_depth))
                            return original(left, right)
                        with patch.object(bd.GeomType, "__eq__", equal):
                            edge.arc_center
                    else:
                        table = bd.Shape.downcast_LUT
                        from OCP.TopAbs import TopAbs_EDGE
                        original = table[TopAbs_EDGE]
                        retained = tx.document._get(_state(edge).handle).shape
                        def downcast(native):
                            observed.append((not native.IsPartner(retained), frontend._compute_depth))
                            return original(native)
                        try:
                            table[TopAbs_EDGE] = downcast
                            edge.arc_center
                        finally:
                            table[TopAbs_EDGE] = original
                    self.assertTrue(observed)
                    self.assertTrue(all(private and depth == 0 for private, depth in observed))


if __name__ == "__main__":
    unittest.main()
