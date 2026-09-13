"""Ordinary selected-edge list modifiers preserve stock validation and aliases."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import build123d as bd

from cadgen._document import Document
from cadgen._document.frontend import FrontendSession, _state


def _facts(shape):
    bounds = shape.bounding_box()
    return (type(shape).__name__, shape.label, shape.material,
            round(shape.volume, 8), len(shape.faces()), len(shape.edges()),
            tuple(round(value, 7) for value in (*bounds.min, *bounds.max)))


class ModifierTests(unittest.TestCase):
    def setUp(self):
        from cadgen._internal import op_memo
        installed = op_memo._installed
        if installed:
            op_memo.uninstall()
        self.addCleanup(op_memo.install if installed else lambda: None)

    def test_stock_selected_list_modifiers_reuse_without_native_copies(self):
        for operation in ("fillet", "chamfer"):
            for container in (list, tuple, bd.ShapeList):
                def model(size=.2):
                    parent = bd.Box(4, 5, 6)
                    parent.label = "authored parent"
                    edges = container(parent.edges())
                    return getattr(bd, operation)(edges, size)
                expected = _facts(model())
                document = Document(f"selected-{operation}-{container.__name__}")
                for turn in range(2):
                    with self.subTest(operation=operation, container=container, turn=turn):
                        with document.begin() as tx:
                            with FrontendSession(tx) as frontend:
                                result = model()
                                self.assertEqual(expected, _facts(result))
                                self.assertFalse(_state(result).private)
                                self.assertFalse(tx.escape_arena.active)
                                self.assertEqual(0, tx.stats.native_copies)
                                if turn:
                                    self.assertEqual(0, tx.stats.computed)
                                    self.assertGreater(tx.stats.reused, 0)
                            tx.commit()

    def test_radius_edit_reuses_parent_and_selected_edges(self):
        document = Document("modifier-size-edit")
        for size in (.2, .3):
            with document.begin() as tx:
                with FrontendSession(tx):
                    parent = bd.Box(4, 5, 6)
                    result = bd.fillet(list(parent.edges()), size)
                    self.assertTrue(result.is_valid)
                    self.assertFalse(_state(parent).private)
                    self.assertEqual(0, tx.stats.native_copies)
                    if size == .3:
                        self.assertEqual(1, tx.stats.computed)
                        self.assertGreaterEqual(tx.stats.reused, 13)
                tx.commit()

    def test_located_circular_list_chamfer_matches_stock(self):
        def model():
            parent = bd.Cylinder(4, 6).moved(bd.Pos(7, 8, 9) * bd.Rot(15, 23, 37))
            edges = [edge for edge in parent.edges() if edge.geom_type is bd.GeomType.CIRCLE]
            return parent, bd.chamfer(edges, .4)
        expected_parent, expected = model()
        with Document("located-list-chamfer").begin() as tx:
            with FrontendSession(tx):
                parent, actual = model()
                self.assertEqual(_facts(expected), _facts(actual))
                self.assertEqual(_facts(expected_parent), _facts(parent))
                self.assertEqual(0, tx.stats.native_copies)
                self.assertFalse(tx.escape_arena.active)

    def test_modifier_kernel_failure_matches_stock_and_does_not_escape_source(self):
        for operation in ("fillet", "chamfer"):
            plain = bd.Box(4, 5, 6)
            with self.assertRaises(ValueError) as expected:
                getattr(bd, operation)(list(plain.edges()), 100)
            with Document("modifier-error-" + operation).begin() as tx:
                with FrontendSession(tx):
                    parent = bd.Box(4, 5, 6)
                    with self.assertRaises(type(expected.exception)) as actual:
                        getattr(bd, operation)(list(parent.edges()), 100)
                    self.assertEqual(str(expected.exception), str(actual.exception))
                    self.assertEqual(120., parent.volume)
                    self.assertFalse(tx.escape_arena.active)

    def test_equal_independent_parent_and_forged_topology_parent_are_not_admitted(self):
        for operation in ("fillet", "chamfer"):
            with Document("modifier-foreign-" + operation).begin() as tx:
                with FrontendSession(tx) as frontend:
                    parent, foreign = bd.Box(4, 5, 6), bd.Box(4, 5, 6)
                    edges = list(foreign.edges())
                    for edge in edges:
                        edge.topo_parent = parent
                    self.assertIsNone(frontend._modifiers.attempt(operation, edges, .2))
                    self.assertFalse(tx.escape_arena.active)
                    self.assertTrue(all(not _state(edge).private for edge in edges))

    def test_moved_edge_or_changed_topology_parent_keeps_ordinary_path(self):
        with Document("modifier-moved-edge").begin() as tx:
            with FrontendSession(tx) as frontend:
                parent = bd.Box(4, 5, 6)
                edge = parent.edges()[0].moved(bd.Pos(1, 0, 0))
                edge.topo_parent = parent
                self.assertIsNone(frontend._modifiers.attempt("fillet", [edge], .2))

    def test_validation_callback_executes_privately_on_every_replay(self):
        import build123d.operations_generic as generic
        original = generic.validate_inputs
        observations = []
        document = Document("modifier-validation-provider")
        for turn in range(2):
            with document.begin() as tx:
                with FrontendSession(tx):
                    parent = bd.Box(4, 5, 6)
                    edges = list(parent.edges())
                    def validate(context, operation, values):
                        observations.append((turn, operation, _state(parent).private))
                        return original(context, operation, values)
                    with patch.object(generic, "validate_inputs", validate):
                        result = bd.chamfer(edges, .2)
                    self.assertTrue(result.is_valid)
                tx.commit()
        self.assertEqual([(0, "chamfer", True), (1, "chamfer", True)], observations)

    def test_custom_list_iteration_matches_stock_function(self):
        for operation in ("fillet", "chamfer"):
            observations = []
            class Edges(list):
                def __iter__(self):
                    observations.append("iter")
                    return list.__iter__(self)
            plain = bd.Box(4, 5, 6)
            expected = _facts(getattr(bd, operation)(Edges(plain.edges()), .2))
            stock_observations = list(observations)
            observations.clear()
            with Document("modifier-custom-" + operation).begin() as tx:
                with FrontendSession(tx):
                    parent = bd.Box(4, 5, 6)
                    edges = list(parent.edges())
                    result = getattr(bd, operation)(Edges(edges), .2)
                    self.assertEqual(expected, _facts(result))
                    self.assertTrue(tx.escape_arena.active)
            self.assertEqual(stock_observations, observations)

    def test_empty_and_mixed_inputs_preserve_stock_validation(self):
        for operation in ("fillet", "chamfer"):
            for kind in ("empty", "mixed"):
                plain = bd.Box(4, 5, 6)
                values = [] if kind == "empty" else [plain.edges()[0], plain.vertices()[0]]
                with self.assertRaises((ValueError, IndexError)) as expected:
                    getattr(bd, operation)(values, .2)
                with Document(f"modifier-invalid-{operation}-{kind}").begin() as tx:
                    with FrontendSession(tx):
                        parent = bd.Box(4, 5, 6)
                        values = [] if kind == "empty" else [parent.edges()[0], parent.vertices()[0]]
                        with self.assertRaises(type(expected.exception)) as actual:
                            getattr(bd, operation)(values, .2)
                        self.assertEqual(str(expected.exception), str(actual.exception))

    def test_context_modification_remains_stock_builder_execution(self):
        def model():
            with bd.BuildPart() as part:
                bd.Box(4, 5, 6)
                bd.chamfer(part.edges(), .2)
            return part.part
        expected = _facts(model())
        with Document("modifier-builder").begin() as tx:
            with FrontendSession(tx) as frontend:
                actual = model()
                self.assertEqual(expected, _facts(frontend.materialize(actual)))

    def test_preentry_public_replacement_is_not_bypassed(self):
        for operation in ("fillet", "chamfer"):
            original = getattr(bd, operation)
            observed = []
            def author(objects, size, **kwargs):
                observed.append(FrontendSession.current()._compute_depth)
                return original(objects, size, **kwargs)
            with patch.object(bd, operation, author):
                with Document("modifier-public-" + operation).begin() as tx:
                    with FrontendSession(tx):
                        parent = bd.Box(4, 5, 6)
                        result = getattr(bd, operation)(list(parent.edges()), .2)
                        self.assertTrue(result.is_valid)
            self.assertEqual([0], observed)

    def test_direct_selection_preserves_preentry_fillet_alias_and_provider_drift(self):
        import build123d.operations_generic as generic
        for replacement in ("public", "validation"):
            observed = []
            original = bd.fillet if replacement == "public" else generic.validate_inputs
            if replacement == "public":
                def author(objects, size):
                    observed.append((type(objects), _state(parent).private,
                                     FrontendSession.current()._compute_depth))
                    return original(objects, size)
                target, name = bd, "fillet"
            else:
                def author(context, operation, objects):
                    observed.append((type(objects), _state(parent).private,
                                     FrontendSession.current()._compute_depth))
                    return original(context, operation, objects)
                target, name = generic, "validate_inputs"
            with patch.object(target, name, author):
                with Document("modifier-direct-alias-" + replacement).begin() as tx:
                    with FrontendSession(tx):
                        parent = bd.Box(4, 5, 6)
                        result = bd.fillet(parent.edges(), .2)
                        self.assertTrue(result.is_valid)
            self.assertEqual([(bd.ShapeList, True, 0)], observed)

    def test_changed_list_and_native_builder_methods_run_after_private_transition(self):
        from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
        for provider in ("list", "native"):
            with Document("modifier-hidden-" + provider).begin() as tx:
                with FrontendSession(tx) as frontend:
                    parent = bd.Box(4, 5, 6)
                    edges = list(parent.edges())
                    observed = []
                    if provider == "list":
                        original = bd.ShapeList.append
                        def append(values, item):
                            observed.append((_state(parent).private, frontend._compute_depth))
                            return original(values, item)
                        context = patch.object(bd.ShapeList, "append", append)
                    else:
                        original = BRepFilletAPI_MakeFillet.Add
                        def add(builder, *args):
                            observed.append((_state(parent).private, frontend._compute_depth))
                            return original(builder, *args)
                        context = patch.object(BRepFilletAPI_MakeFillet, "Add", add)
                    with context:
                        result = bd.fillet(edges, .2)
                    self.assertTrue(result.is_valid)
                    self.assertTrue(observed)
                    self.assertTrue(all(private and depth == 0 for private, depth in observed))

    def test_source_result_native_aliases_are_private_and_retained_source_is_unchanged(self):
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.gp import gp_Pnt
        with Document("modifier-result-alias").begin() as tx:
            with FrontendSession(tx) as frontend:
                parent = bd.Box(4, 5, 6)
                result = bd.fillet([parent.edges()[0]], .2)
                retained_parent = tx.document._get(_state(parent).handle).shape
                retained = frontend._wrap_native(retained_parent)
                before = tuple(tuple(vertex) for vertex in retained.vertices())
                self.assertEqual(0, tx.stats.native_copies)
                result = frontend._escape_shape(result)
                source = frontend._escape_shape(parent)
                shared = next((left.wrapped for left in source.vertices()
                               if any(left.wrapped.IsSame(right.wrapped) for right in result.vertices())), None)
                self.assertIsNotNone(shared)
                BRep_Builder().UpdateVertex(shared, gp_Pnt(99., 17., 23.), .01)
                self.assertEqual(99., BRep_Tool.Pnt_s(shared).X())
                self.assertTrue(any(vertex.X == 99 for vertex in source.vertices()))
                self.assertEqual(before, tuple(tuple(vertex) for vertex in retained.vertices()))

    def test_lazy_proxy_never_retains_a_closed_frontend_callable(self):
        import cadgen.build123d as proxy
        for operation in ("fillet", "chamfer"):
            prior = vars(proxy).pop(operation, None)
            try:
                document = Document("modifier-lazy-proxy-" + operation)
                for _turn in range(2):
                    with document.begin() as tx:
                        with FrontendSession(tx):
                            parent = bd.Box(4, 5, 6)
                            result = getattr(proxy, operation)(list(parent.edges()), .2)
                            self.assertTrue(result.is_valid)
                        self.assertNotIn(operation, vars(proxy))
                        tx.commit()
                parent = bd.Box(4, 5, 6)
                self.assertTrue(getattr(proxy, operation)(list(parent.edges()), .2).is_valid)
            finally:
                vars(proxy).pop(operation, None)
                if prior is not None:
                    setattr(proxy, operation, prior)

    def test_authored_proxy_alias_remains_ordinary(self):
        import cadgen.build123d as proxy
        for operation in ("fillet", "chamfer"):
            original = getattr(bd, operation)
            observed = []
            def author(objects, size):
                observed.append(FrontendSession.current()._compute_depth)
                return original(objects, size)
            with patch.object(proxy, operation, author, create=True):
                with Document("modifier-proxy-alias-" + operation).begin() as tx:
                    with FrontendSession(tx):
                        self.assertIs(author, getattr(proxy, operation))
                        parent = bd.Box(4, 5, 6)
                        result = getattr(proxy, operation)(list(parent.edges()), .2)
                        self.assertTrue(result.is_valid)
            self.assertEqual([0], observed)


if __name__ == "__main__":
    unittest.main()
