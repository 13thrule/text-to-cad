"""Behavior proof for the bounded graph-aware build123d frontend."""
from __future__ import annotations

import copy
import inspect
import unittest

from cadgen import build123d as bd
from cadgen._document import Document
from cadgen._document.frontend import FrontendSession


def _plate(radius_left: float = 1.5, radius_right: float = 1.5):
    part = bd.Box(30, 20, 6)
    for x, radius in ((-8, radius_left), (8, radius_right)):
        part = part - bd.Pos(x, 0, 0) * bd.Cylinder(radius, 10)
    return bd.fillet(part.edges().filter_by(bd.Axis.Z), 1.0)


class FrontendTest(unittest.TestCase):
    def setUp(self):
        # The document engine deliberately refuses coexistence with the old
        # global memo/equality interception stack.  Preserve a wider test
        # runner's prior state around these isolated frontend checks.
        from cadgen._internal import op_memo
        self._memo_was_installed = op_memo._installed
        if self._memo_was_installed:
            op_memo.uninstall()
        self.addCleanup(op_memo.install if self._memo_was_installed else lambda: None)

    def _run_plate(self, document, left=1.5, right=1.5, side_effects=None):
        with document.begin(f"{left}:{right}") as transaction:
            with FrontendSession(transaction) as frontend:
                if side_effects is not None:
                    side_effects.append((left, right))
                part = _plate(left, right)
                volume = part.volume
                edge_count = len(part.edges())
                native = frontend.materialize(part)
            revision = transaction.commit()
        self.assertAlmostEqual(volume, native.volume, places=8)
        self.assertEqual(edge_count, len(native.edges()))
        return transaction, revision, native

    def test_plate_holes_fillet_reuses_ops_but_executes_python(self):
        document = Document("frontend-plate")
        side_effects = []
        first, _, original = self._run_plate(document, side_effects=side_effects)
        repeated, _, same = self._run_plate(document, side_effects=side_effects)
        edited, _, changed = self._run_plate(document, right=2.0, side_effects=side_effects)

        self.assertGreater(first.stats.computed, 0)
        self.assertEqual(0, repeated.stats.computed)
        self.assertGreater(repeated.stats.reused, 0)
        self.assertGreater(edited.stats.computed, 0)
        self.assertGreater(edited.stats.reused, 0)  # base and left-hole branch
        self.assertAlmostEqual(original.volume, same.volume, places=8)
        self.assertLess(changed.volume, original.volume)
        self.assertEqual([(1.5, 1.5), (1.5, 1.5), (1.5, 2.0)], side_effects)

    def test_fillet_escape_preserves_proven_source_result_aliases(self):
        document = Document("frontend-fillet-aliases")
        with document.begin("fillet") as transaction:
            with FrontendSession(transaction) as frontend:
                source = bd.Box(30, 20, 6)
                for x in (-8, 8):
                    source = source - bd.Pos(x, 0, 0) * bd.Cylinder(1.5, 10)
                source_volume = source.volume
                result = bd.fillet(source.edges().filter_by(bd.Axis.Z), 1.0)
                result_volume = result.volume
                native = frontend.materialize(result)
                self.assertTrue(native.is_valid)
                self.assertAlmostEqual(source_volume, source.volume, places=8)
                shared = 0
                for kind in ("faces", "edges", "vertices"):
                    left = getattr(source, kind)()
                    right = getattr(native, kind)()
                    shared += sum(a.wrapped.IsSame(b.wrapped) for a in left for b in right)
                self.assertGreater(shared, 0)
            transaction.commit()
        self.assertAlmostEqual(result_volume, native.volume, places=8)

    def _run_assembly(self, document, shift):
        from cadgen._document.returned import bind_returned_shape

        with document.begin(str(shift)) as transaction:
            with FrontendSession(transaction) as frontend:
                prototype = _plate()
                # Common author validation remains a scalar query; it must not
                # force the prototype private before occurrence placement.
                self.assertTrue(prototype.is_valid)
                children = []
                for index in range(24):
                    child = bd.Pos((index % 6) * 40, (index // 6) * 30 + shift, 0) * prototype
                    child.label = f"plate-{index}"
                    children.append(child)
                assembly = bd.Compound(children=children, label="plate-array")
                bind_returned_shape(frontend, assembly)
                native = frontend.materialize(assembly)
            revision = transaction.commit()
        bounds = native.bounding_box()
        self.assertEqual(tuple(f"plate-{index}" for index in range(24)),
                         tuple(child.label for child in native.children))
        for node in (native, *native.children):
            self.assertFalse(hasattr(node, "_cadgen_document_state"))
        copy.deepcopy(native)  # no session lock remains on exported wrappers
        return transaction, revision, native, tuple(bounds.min), tuple(bounds.max)

    def test_24_occurrence_placement_edit_recomputes_no_geometry(self):
        document = Document("frontend-assembly")
        first, first_revision, original, original_min, original_max = self._run_assembly(document, 0)
        moved, moved_revision, shifted, shifted_min, shifted_max = self._run_assembly(document, 5)

        self.assertEqual(24, len(first_revision.root.children))
        self.assertEqual(24, len(moved_revision.root.children))
        self.assertEqual(0, moved.stats.computed)
        self.assertGreater(moved.stats.reused, 0)
        self.assertEqual(24, len(original.solids()))
        self.assertEqual(24, len(shifted.solids()))
        self.assertAlmostEqual(original.volume, shifted.volume, places=7)
        self.assertAlmostEqual(5, shifted_min[1] - original_min[1], places=8)
        self.assertAlmostEqual(5, shifted_max[1] - original_max[1], places=8)

    def test_native_escape_preserves_aliases_distinct_calls_and_later_revision(self):
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.gp import gp_Pnt

        document = Document("frontend-escape")
        with document.begin("first") as transaction:
            with FrontendSession(transaction) as frontend:
                first = bd.Box(4, 5, 6)
                alias = first
                independent = bd.Box(4, 5, 6)
                held_vertex = first.vertices()[0]  # explicit private escape
                original_x = held_vertex.X
                independent_x = independent.vertices()[0].X
                self.assertFalse(first.wrapped.IsSame(independent.wrapped))
                BRep_Builder().UpdateVertex(held_vertex.wrapped, gp_Pnt(99, 0, 0), 0.01)
                self.assertEqual(99, BRep_Tool.Pnt_s(alias.vertices()[0].wrapped).X())
                self.assertEqual(independent_x, independent.vertices()[0].X)
                frontend.materialize(first)
            transaction.commit()

        with document.begin("second") as transaction:
            with FrontendSession(transaction) as frontend:
                clean = bd.Box(4, 5, 6)
                clean_vertex_x = clean.vertices()[0].X
                frontend.materialize(clean)
            transaction.commit()
        self.assertEqual(original_x, clean_vertex_x)

    def test_callable_query_executes_each_revision_in_private_region(self):
        document = Document("frontend-callback")
        observations = []
        for revision in ("one", "two"):
            with document.begin(revision) as transaction:
                with FrontendSession(transaction) as frontend:
                    part = bd.Box(4, 5, 6)
                    def observe(edge):
                        observations.append(round(edge.length, 6))
                        return edge.length > 0
                    selected = part.edges().filter_by(observe)
                    self.assertEqual(12, len(selected))
                    frontend.materialize(part)
                transaction.commit()
        self.assertEqual(24, len(observations))

    def test_build_context_executes_ordinary_python_and_is_opaque_captured(self):
        document = Document("frontend-opaque-builder")
        observations = []
        volumes = []
        computed = []
        for source in ("first", "second"):
            with document.begin(source) as transaction:
                with FrontendSession(transaction) as frontend:
                    observations.append(source)
                    with bd.BuildPart() as part:
                        with bd.BuildSketch():
                            bd.Rectangle(10, 8)
                            with bd.Locations((-3, 0), (3, 0)):
                                bd.Circle(1, mode=bd.Mode.SUBTRACT)
                        bd.extrude(amount=2)
                    native = frontend.materialize(part.part)
                transaction.commit()
            self.assertTrue(native.is_valid)
            volumes.append(native.volume)
            computed.append(transaction.stats.computed)

        self.assertEqual(["first", "second"], observations)
        self.assertAlmostEqual(volumes[0], volumes[1], places=8)
        # Opaque regions are deliberately volatile rather than inferred pure.
        self.assertGreater(computed[0], 0)
        self.assertGreater(computed[1], 0)

    def test_unsupported_sphere_transform_executes_privately(self):
        placement = bd.Rot(15, 35, 70)
        plain = placement * bd.Sphere(2.0)
        document = Document("frontend-opaque-sphere")
        computed = []
        for source in ("first", "second"):
            with document.begin(source) as transaction:
                with FrontendSession(transaction) as frontend:
                    native = frontend.materialize(placement * bd.Sphere(2.0))
                transaction.commit()
            computed.append(transaction.stats.computed)
            self.assertTrue(native.is_valid)
            self.assertAlmostEqual(plain.volume, native.volume, places=8)
            actual, expected = native.bounding_box(), plain.bounding_box()
            for left, right in zip((*actual.min, *actual.max),
                                   (*expected.min, *expected.max)):
                self.assertAlmostEqual(left, right, places=8)
        self.assertGreater(computed[0], 0)
        self.assertGreater(computed[1], 0)

    def test_materialized_boolean_result_keeps_part_compound_contract(self):
        document = Document("frontend-part-wrapper")
        with document.begin("four-holes") as transaction:
            with FrontendSession(transaction) as frontend:
                result = bd.Box(
                    80, 50, 6,
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                )
                result = bd.fillet(result.edges().filter_by(bd.Axis.Z), 4)
                for x in (-28, 28):
                    for y in (-13, 13):
                        cutter = bd.Pos(x, y, -1) * bd.Cylinder(
                            3, 8,
                            align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                        )
                        result = result - cutter
                expected_volume = result.volume
                native = frontend.materialize(result)
            transaction.commit()

        from OCP.TopAbs import TopAbs_COMPOUND
        self.assertEqual(TopAbs_COMPOUND, native.wrapped.ShapeType())
        self.assertEqual(1, len(native.solids()))
        self.assertTrue(native.is_valid)
        self.assertAlmostEqual(expected_volume, native.volume, places=8)

    def test_moved_composition_and_located_copy_match_plain_build123d(self):
        location_a = bd.Pos(5, 2, 0) * bd.Rot(0, 0, 35)
        location_b = bd.Pos(-1, 4, 3) * bd.Rot(10, 0, 0)
        plain_base = bd.Box(3, 5, 7)
        plain_moved = plain_base.moved(location_a).moved(location_b)
        plain_located = plain_base.located(location_a)

        document = Document("frontend-placement-semantics")
        with document.begin("placement") as transaction:
            with FrontendSession(transaction) as frontend:
                base = bd.Box(3, 5, 7)
                moved = base.moved(location_a).moved(location_b)
                located = base.located(location_a)
                moved = frontend.materialize(moved)
                located = frontend.materialize(located)
            transaction.commit()
        for actual, expected in ((moved, plain_moved), (located, plain_located)):
            actual_box, expected_box = actual.bounding_box(), expected.bounding_box()
            for left, right in zip((*actual_box.min, *actual_box.max),
                                   (*expected_box.min, *expected_box.max)):
                self.assertAlmostEqual(left, right, places=8)
        self.assertTrue(plain_base.wrapped.IsPartner(plain_moved.wrapped))
        self.assertFalse(plain_base.wrapped.IsPartner(plain_located.wrapped))

    def test_partial_install_failure_restores_process_globals(self):
        original_add = inspect.getattr_static(bd.Shape, "__add__")

        class BrokenFrontend(FrontendSession):
            def _install(self):
                self._patch(self._bd.Shape, "__add__", lambda shape, other: None)
                raise RuntimeError("install failed")

        document = Document("frontend-install-failure")
        with document.begin("failure") as transaction:
            with self.assertRaisesRegex(RuntimeError, "install failed"):
                with BrokenFrontend(transaction):
                    pass
        self.assertIs(original_add, inspect.getattr_static(bd.Shape, "__add__"))
        self.assertIsNone(FrontendSession.current())

    def test_rejects_the_old_global_memo_interception(self):
        from cadgen._internal import op_memo
        document = Document("frontend-old-memo")
        op_memo.install()
        try:
            with document.begin("mixed") as transaction:
                with self.assertRaisesRegex(RuntimeError, "retired op memo"):
                    with FrontendSession(transaction):
                        pass
        finally:
            op_memo.uninstall()


if __name__ == "__main__":
    unittest.main()
