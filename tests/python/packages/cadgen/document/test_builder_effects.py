"""Native effect bundles preserve stock builder state and share their history."""
from __future__ import annotations

import unittest
from pathlib import Path
from functools import wraps
from unittest.mock import patch

from cadgen import build123d as bd
from cadgen._document import Document, Mutation, NativeResult, OperatorSpec
from cadgen._document.builder_effects import StockBuilderEffects, UnsupportedBuilderEffect
from cadgen._document.frontend import _matrix
from cadgen._document.frontend import FrontendSession
from cadgen._document.native import topology_map


def primitive(tx, effects, kind, values):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    constructor = BRepPrimAPI_MakeBox if kind == "box" else BRepPrimAPI_MakeCylinder
    handle = tx.evaluate(
        OperatorSpec(f"test.effect.{kind}", mutation=Mutation.READ_ONLY, closed_constructor=True),
        values, (), lambda inputs, arena: NativeResult(constructor(*values).Shape()))
    offset = (-values[0] / 2, -values[1] / 2, -values[2] / 2) if kind == "box" else (0, 0, -values[1] / 2)
    return effects.aligned_input(tx, handle, _matrix(bd.Pos(*offset)))


def facts(shape):
    if shape is None:
        return None
    bounds = shape.bounding_box()
    return (round(shape.volume, 7), len(shape.solids()), len(shape.faces()),
            len(shape.edges()), len(shape.vertices()), bool(shape.is_valid),
            tuple(round(v, 7) for v in bounds.min), tuple(round(v, 7) for v in bounds.max))


def observations(builder):
    roots = [shape for shape in (builder.obj_before, *builder.to_combine, builder.part)
             if shape is not None]
    nodes = [[value.wrapped for kind in ("vertices", "edges", "faces", "solids")
              for value in getattr(shape, kind)()] for shape in roots]
    aliases = tuple(tuple(sum(a.IsSame(b) for a in left for b in right)
                          for right in nodes) for left in nodes)
    return (facts(builder.part), facts(builder.obj_before),
            tuple(facts(shape) for shape in builder.to_combine),
            tuple(len(builder.lasts[kind]) for kind in (bd.Vertex, bd.Edge, bd.Face, bd.Solid)),
            len(builder.edges(bd.Select.NEW)), aliases,
            tuple(builder.lasts[bd.Solid][i] is shape
                  for i, shape in enumerate(builder.to_combine)),
            tuple(len(getattr(builder, field)) for field in
                  ("pending_edges", "pending_faces", "pending_face_planes", "pending_planes")))


def as_builder(view):
    builder = object.__new__(bd.BuildPart)
    builder._part = view.result
    builder.obj_before = view.obj_before
    builder.to_combine = list(view.to_combine)
    builder.lasts = {kind: bd.ShapeList(row) for kind, row in
                     zip((bd.Vertex, bd.Edge, bd.Face, bd.Solid), view.lasts)}
    builder.pending_edges = []
    builder.pending_faces = []
    builder.pending_face_planes = []
    builder.pending_planes = []
    return builder


ACTION_ROWS = (("box", (10., 8., 4.), "ADD"),
               ("cylinder", (2., 8.), "SUBTRACT"),
               ("box", (2., 2., 6.), "ADD"),
               ("box", (3., 4., 5.), "REPLACE"))


class BuilderEffectsTest(unittest.TestCase):
    def setUp(self):
        from cadgen._internal import op_memo
        installed = op_memo._installed
        if installed:
            op_memo.uninstall()
        self.addCleanup(op_memo.install if installed else lambda: None)

    def baseline(self, rows=ACTION_ROWS):
        output = []
        with bd.BuildPart() as builder:
            for kind, values, mode in rows:
                (bd.Box if kind == "box" else bd.Cylinder)(*values, mode=getattr(bd.Mode, mode))
                output.append(observations(builder))
        return output

    def run_effects(self, document, rows=ACTION_ROWS):
        effects = StockBuilderEffects()
        bundles = []
        with document.begin() as tx:
            previous = None
            for kind, values, mode in rows:
                source = primitive(tx, effects, kind, values)
                previous = effects.evaluate(tx, previous, (source,), mode=getattr(bd.Mode, mode))
                bundles.append(previous)
            views = [effects.materialize(tx, bundle) for bundle in bundles]
            result = [observations(as_builder(view)) for view in views]
            tx.commit()
        return result, views, bundles, tx.stats

    def test_stock_add_subtract_replace_complete_effects_match_on_warm_hits(self):
        expected = self.baseline()
        document = Document("effects-parity")
        for turn in range(2):
            actual, views, bundles, stats = self.run_effects(document)
            self.assertEqual(expected, actual)
            if turn:
                self.assertEqual(0, stats.computed)
                self.assertEqual(12, stats.reused)
            # The subtracted tool remains present in LAST and to_combine even
            # though it is not a solid in the final Part.
            self.assertAlmostEqual(32. * 3.141592653589793, views[1].lasts[3][0].volume)
            self.assertIs(views[1].lasts[3][0], views[1].to_combine[0])
            self.assertEqual(1, len(views[-1].result.solids()))

    def test_local_tool_edit_reuses_prior_effect_and_changes_only_its_descendants(self):
        document = Document("effects-local-edit")
        first, _, original, _ = self.run_effects(document)
        edited_rows = (*ACTION_ROWS[:1], ("cylinder", (2.5, 8.), "SUBTRACT"), *ACTION_ROWS[2:])
        edited, _, changed, stats = self.run_effects(document, edited_rows)
        self.assertEqual(self.baseline(edited_rows), edited)
        self.assertEqual(original[0].handle.evaluation_id, changed[0].handle.evaluation_id)
        self.assertNotEqual(original[1].handle.evaluation_id, changed[1].handle.evaluation_id)
        self.assertLess(edited[1][0][0], first[1][0][0])
        self.assertGreater(stats.reused, 0)

    def test_native_escape_preserves_cross_effect_aliases_and_isolates_next_run(self):
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.gp import gp_Pnt
        document = Document("effects-aliases")
        expected, views, _, _ = self.run_effects(document, ACTION_ROWS[:2])
        earlier = views[0].result
        later_before = views[1].obj_before
        before_vertex = earlier.vertices()[0].wrapped
        partner = next(vertex.wrapped for vertex in later_before.vertices()
                       if vertex.wrapped.IsSame(before_vertex))
        point = BRep_Tool.Pnt_s(before_vertex)
        BRep_Builder().UpdateVertex(before_vertex, gp_Pnt(80., point.Y(), point.Z()), .01)
        self.assertEqual(80., BRep_Tool.Pnt_s(partner).X())
        actual, clean, _, stats = self.run_effects(document, ACTION_ROWS[:2])
        self.assertEqual(expected, actual)
        self.assertEqual(0, stats.computed)
        self.assertNotEqual(80., clean[0].result.vertices()[0].X)

    def test_parent_carriers_share_native_dag_edges_without_copying_history(self):
        from cadgen._document.builder_effects import _slots
        document = Document("effects-sharing")
        effects = StockBuilderEffects()
        sizes = []
        layouts = []
        with document.begin() as tx:
            previous = None
            for index in range(1, 13):
                shape = primitive(tx, effects, "box", (float(index), 3., 4.))
                current = effects.evaluate(tx, previous, (shape,), mode=bd.Mode.REPLACE)
                native = document._get(current.handle).shape
                if previous is not None:
                    self.assertTrue(_slots(native)[0].IsSame(document._get(previous.handle).shape))
                layouts.append(current.layout.slot_count)
                sizes.append(topology_map(native).Extent())
                previous = current
            # Native input instantiation copies one new primitive per step;
            # complete prior worlds are only referenced, never copied here.
            self.assertEqual(12, tx.stats.native_copies)
            self.assertEqual(0, tx.escape_arena.copy_batches)
            self.assertLessEqual(max(layouts[1:]) - min(layouts[1:]), 1)
            self.assertLess(sizes[-1], 2.2 * sizes[5])

    def test_provider_mutation_and_native_escape_are_explicit_admission_failures(self):
        effects = StockBuilderEffects()
        with Document("effects-admission").begin() as tx:
            source = primitive(tx, effects, "box", (2., 3., 4.))
            with patch.object(bd.Shape, "cut", lambda *args: None):
                with self.assertRaises(UnsupportedBuilderEffect):
                    effects.evaluate(tx, None, (source,), mode=bd.Mode.ADD)
            tx.escape_arena.native(source)
            with self.assertRaisesRegex(UnsupportedBuilderEffect, "after native escape"):
                effects.evaluate(tx, None, (source,), mode=bd.Mode.ADD)

    def test_independent_coincident_inputs_do_not_collapse(self):
        effects = StockBuilderEffects()
        with Document("effects-independent-inputs").begin() as tx:
            first = primitive(tx, effects, "box", (2., 3., 4.))
            second = primitive(tx, effects, "box", (2., 3., 4.))
            self.assertNotEqual(first.allocation_id, second.allocation_id)
            with self.assertRaisesRegex(UnsupportedBuilderEffect, "independent coincident"):
                effects.evaluate(tx, None, (first, second), mode=bd.Mode.ADD)

    def run_frontend(self, document, fixture):
        with document.begin() as tx:
            with FrontendSession(tx) as frontend:
                result, retained = fixture()
                counts = dict(frontend._fallback_counts)
                stats = (tx.stats.computed, tx.stats.reused, tx.stats.native_copies)
                actual = frontend.materialize(result)
                for value in retained:
                    if isinstance(value, bd.Shape):
                        frontend.materialize(value)
            tx.commit()
        return actual, retained, counts, stats

    def test_complete_frontend_build_reuses_all_effects_and_replays_source(self):
        calls = []
        def fixture(radius=2.):
            calls.append(radius)
            with bd.BuildPart() as builder:
                first = bd.Box(10., 8., 4.)
                before = builder.part
                tool = bd.Cylinder(radius, 8., mode=bd.Mode.SUBTRACT)
                original_tool = builder.to_combine[0]
                before_last = builder.part
                bd.Box(2., 2., 6.)
            return builder.part, (builder, first, before, tool, original_tool, before_last)
        expected, _ = fixture()
        expected_facts = facts(expected)
        document = Document("effects-frontend")
        for turn in range(2):
            actual, retained, counts, stats = self.run_frontend(document, fixture)
            self.assertEqual(expected_facts, facts(actual))
            self.assertEqual(3, counts.get("builder-effects-retained", 0))
            if turn:
                self.assertEqual(0, stats[0])
                self.assertGreater(stats[1], 3)
            builder, first, before, tool, original_tool, before_last = retained
            self.assertIs(before_last, builder.obj_before)
            self.assertTrue(tool.solids()[0].wrapped.IsSame(original_tool.wrapped))
            self.assertAlmostEqual(320., before.volume)
            self.assertAlmostEqual(320., first.volume)
        changed, _, counts, stats = self.run_frontend(document, lambda: fixture(2.5))
        self.assertLess(changed.volume, actual.volume)
        self.assertGreater(stats[0], 0)
        self.assertGreater(stats[1], 0)
        self.assertEqual([2., 2., 2., 2.5], calls)

    def test_stock_cone_insertion_matches_and_reuses_with_local_dimension_edits(self):
        calls = []
        def fixture(top_radius=2.):
            calls.append(top_radius)
            with bd.BuildPart() as builder:
                bd.Box(18., 18., 4., align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
                with bd.Locations(bd.Pos(3., -2., 2.8)):
                    cone = bd.Cone(
                        bottom_radius=1., top_radius=top_radius, height=1.4,
                        align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                        mode=bd.Mode.SUBTRACT,
                    )
            return builder.part, (cone,)

        expected, _ = fixture()
        expected_facts = facts(expected)
        document = Document("effects-cone-frontend")
        for turn in range(2):
            actual, retained, counts, stats = self.run_frontend(document, fixture)
            self.assertEqual(expected_facts, facts(actual))
            self.assertEqual(2, counts.get("builder-effects-retained", 0))
            self.assertEqual((1., 2., 1.4, 360),
                             (retained[0].bottom_radius, retained[0].top_radius,
                              retained[0].cone_height, retained[0].arc_size))
            if turn:
                self.assertEqual(0, stats[0])
                self.assertGreater(stats[1], 2)

        changed, _, counts, stats = self.run_frontend(document, lambda: fixture(2.5))
        self.assertNotEqual(facts(actual), facts(changed))
        self.assertGreater(stats[0], 0)
        self.assertGreater(stats[1], 0)
        self.assertEqual(2, counts.get("builder-effects-retained", 0))
        self.assertEqual([2., 2., 2., 2.5], calls)

    def test_cone_tip_and_invalid_equal_radii_follow_stock_constructor(self):
        expected = bd.Cone(2., 0., 3.)
        document = Document("effects-cone-tip")
        for turn in range(2):
            with document.begin() as tx:
                with FrontendSession(tx) as frontend:
                    actual = bd.Cone(2., 0., 3.)
                    stats = (tx.stats.computed, tx.stats.reused)
                    actual = frontend.materialize(actual)
                tx.commit()
            self.assertEqual(facts(expected), facts(actual))
            if turn:
                self.assertEqual(0, stats[0])
                self.assertGreater(stats[1], 0)

        try:
            bd.Cone(2., 2., 3.)
        except Exception as error:  # exact native exception is part of stock behavior
            expected_error = error
        else:
            self.fail("stock equal-radius cone unexpectedly succeeded")
        with document.begin() as tx:
            with FrontendSession(tx):
                with self.assertRaisesRegex(type(expected_error), "identic radii"):
                    bd.Cone(2., 2., 3.)

    def test_replaced_cone_kernel_executes_ordinarily_on_every_revision(self):
        import inspect
        original = inspect.getattr_static(bd.Solid, "make_cone")
        calls = []
        def replacement(cls, *args, **kwargs):
            calls.append((args, kwargs))
            return original.__func__(cls, *args, **kwargs)
        def fixture():
            with bd.BuildPart() as builder:
                bd.Cone(3., 1., 4.)
            return builder.part, ()

        with patch.object(bd.Solid, "make_cone", classmethod(replacement)):
            expected, _ = fixture()
            expected_facts = facts(expected)
            document = Document("effects-cone-provider")
            for _ in range(2):
                calls.clear()
                actual, _, counts, _ = self.run_frontend(document, fixture)
                self.assertEqual(expected_facts, facts(actual))
                self.assertEqual(1, len(calls))
                self.assertEqual(0, counts.get("builder-effects-retained", 0))

    def test_frontend_escape_revokes_builder_before_later_native_effects(self):
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.gp import gp_Pnt
        observations = []
        def fixture():
            with bd.BuildPart() as builder:
                first = bd.Box(10., 8., 4.)
                before = builder.part
                bd.Cylinder(2., 8., mode=bd.Mode.SUBTRACT)
                vertex = before.vertices()[0].wrapped
                point = BRep_Tool.Pnt_s(vertex)
                BRep_Builder().UpdateVertex(vertex, gp_Pnt(55., point.Y(), point.Z()), .01)
                self.assertTrue(any(abs(v.X - 55.) < .001 for v in builder.obj_before.vertices()))
                # Revoked state executes ordinarily even though the next
                # primitive itself remains a safe closed constructor.
                bd.Box(2., 3., 4., mode=bd.Mode.REPLACE)
                observations.append(first.length)
            return builder.part, ()
        document = Document("effects-revocation")
        for _ in range(2):
            result, _, counts, stats = self.run_frontend(document, fixture)
            self.assertAlmostEqual(24., result.volume)
            self.assertEqual(2, counts.get("builder-effects-retained", 0))
        self.assertEqual([10., 10.], observations)

    def test_custom_validation_and_empty_pending_callbacks_run_once_per_action(self):
        original_validate = bd.BuildPart.validate_inputs
        original_pending = bd.BuildPart._add_to_pending
        calls = []
        def validate(builder, *args, **kwargs):
            calls.append("validate")
            if builder.part is not None:
                builder.part.wrapped
            return original_validate(builder, *args, **kwargs)
        def pending(builder, *args, **kwargs):
            calls.append("pending")
            return original_pending(builder, *args, **kwargs)
        def fixture():
            with bd.BuildPart() as builder:
                bd.Box(10., 8., 4.)
                bd.Cylinder(2., 8., mode=bd.Mode.SUBTRACT)
            return builder.part, ()
        with patch.object(bd.BuildPart, "validate_inputs", validate), patch.object(
                bd.BuildPart, "_add_to_pending", pending):
            expected, _ = fixture()
            expected_calls = tuple(calls)
            document = Document("effects-callbacks")
            for _ in range(2):
                calls.clear()
                actual, _, counts, _ = self.run_frontend(document, fixture)
                self.assertEqual(facts(expected), facts(actual))
                self.assertEqual(expected_calls, tuple(calls))
                self.assertEqual(0, counts.get("builder-effects-retained", 0))

    def test_service_checkpoint_restart_reuses_complete_native_effect_results(self):
        from cadgen._document.checkpoint import CheckpointCodec, checkpoint_engine_version
        from cadgen._document.service import DocumentService
        from cadgen._document.storage import Catalog
        from tests.python.support.tmp_root import generated_cad_directory
        source = '''from pathlib import Path
from cadgen import step, build123d as bd
@step
def model():
    counter = Path(__file__).with_suffix('.runs')
    counter.write_text((counter.read_text() if counter.exists() else '') + 'run\\n')
    with bd.BuildPart() as builder:
        bd.Box(10, 8, 4)
        before = builder.part
        bd.Cylinder(2, 8, mode=bd.Mode.SUBTRACT)
        assert builder.obj_before is before
        assert builder.lasts[bd.Solid][0] is builder.to_combine[0]
        bd.Box(2, 2, 6)
    return builder.part
'''
        with generated_cad_directory(prefix="document-builder-restart-") as directory:
            root = Path(directory).resolve()
            path = root / "part.py"
            path.write_text(source, encoding="utf-8")
            catalog = Catalog(root / "catalog", engine_version=checkpoint_engine_version())
            self.addCleanup(catalog.close)
            codec = CheckpointCodec(catalog, runtime={"builder-effects-test": 1})
            first = DocumentService(checkpoint_codec=codec)
            built = first.generate(path)
            expected = facts(bd.import_step(path.with_suffix(".step")))
            self.assertEqual(3, first.last_attempt.fallback_counts.get("builder-effects-retained", 0))
            self.assertTrue(first.checkpoint(built.document).published)
            second = DocumentService(checkpoint_codec=codec)
            with patch("cadgen._internal.generation._generate_step_outputs",
                       side_effect=AssertionError("old pipeline")):
                result = second.generate(path)
            self.assertEqual(["recovered"], list(second.recovery.values()))
            self.assertNotEqual(result.document.owner_id, built.document.owner_id)
            self.assertEqual(0, second.last_attempt.stats.computed)
            self.assertEqual(3, second.last_attempt.fallback_counts.get("builder-effects-retained", 0))
            self.assertEqual(expected, facts(bd.import_step(path.with_suffix(".step"))))
            self.assertEqual("run\nrun\n", path.with_suffix(".runs").read_text())
            catalog.close()

    def test_layout_decoder_rejects_missing_bad_slots_and_parent_cycles(self):
        from cadgen._document.builder_effects import _decode_layout, _encode_layout, _pack, _slots
        document = Document("effects-layout-validation")
        _, _, bundles, _ = self.run_effects(document, ACTION_ROWS[:1])
        bundle = bundles[0]
        native = document._get(bundle.handle).shape
        layout = _encode_layout(bundle.layout)
        self.assertEqual(bundle.layout, _decode_layout(layout, native))
        for invalid in (None, (*layout[:-1], layout[-1] + 1)):
            with self.assertRaises(ValueError):
                _decode_layout(invalid, native)
        records = list(layout[5])
        records[0] = (*records[0][:-1], ("created", 0))
        with self.assertRaises(ValueError):
            _decode_layout((*layout[:5], tuple(records), *layout[6:]), native)
        records = list(layout[5])
        # Keep the result a Part but substitute a wrong topology kind in one
        # LAST wrapper. Roles/counts alone cannot attest that native slot.
        records[1] = (records[1][0], "Solid", *records[1][2:])
        with self.assertRaises(ValueError):
            _decode_layout((*layout[:5], tuple(records), *layout[6:]), native)
        from OCP.BRep import BRep_Builder
        corrupt = _pack(_slots(native))
        from cadgen._document.builder_effects import _children
        holder = _children(corrupt)[0]
        holder.Free(True)
        BRep_Builder().Add(holder, _slots(native)[-1])
        with self.assertRaises(ValueError):
            _decode_layout(layout, corrupt)

    def test_frontend_preserves_lasts_dictionary_and_custom_keys(self):
        def fixture():
            with bd.BuildPart() as builder:
                retained = builder.lasts
                marker = object()
                retained["authored"] = marker
                bd.Box(10., 8., 4.)
                self.assertIs(builder.lasts, retained)
                bd.Cylinder(2., 8., mode=bd.Mode.SUBTRACT)
                self.assertIs(builder.lasts, retained)
                self.assertIs(marker, retained["authored"])
            return builder.part, ()
        document = Document("effects-last-dictionary")
        for turn in range(2):
            _, _, counts, stats = self.run_frontend(document, fixture)
            self.assertEqual(2, counts.get("builder-effects-retained", 0))
            if turn:
                self.assertEqual(0, stats[0])

    def test_overridden_inherited_boolean_and_native_kernel_execute_on_every_run(self):
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        original_cut = bd.Part.cut
        original_build = BRepAlgoAPI_Cut.Build
        calls = []
        @wraps(original_cut)
        def cut(shape, *args, **kwargs):
            calls.append("cut")
            return original_cut(shape, *args, **kwargs)
        def build(operation, *args, **kwargs):
            calls.append("build")
            return original_build(operation, *args, **kwargs)
        def fixture():
            with bd.BuildPart() as builder:
                bd.Box(10., 8., 4.)
                bd.Cylinder(2., 8., mode=bd.Mode.SUBTRACT)
            return builder.part, ()
        for owner, name, replacement in ((bd.Part, "cut", cut), (BRepAlgoAPI_Cut, "Build", build)):
            document = Document("effects-provider-" + name)
            with patch.object(owner, name, replacement):
                for _ in range(2):
                    calls.clear()
                    result, _, counts, _ = self.run_frontend(document, fixture)
                    self.assertEqual([name.lower()], calls)
                    self.assertEqual(0, counts.get("builder-effects-retained", 0))
                    self.assertAlmostEqual(320. - 16. * 3.141592653589793, result.volume)

    def test_logging_callbacks_are_not_skipped_by_effect_hits(self):
        import logging
        from build123d import build_common
        calls = []
        class Handler(logging.Handler):
            def emit(self, record):
                if record.getMessage().startswith("Completed integrating"):
                    calls.append(record.getMessage())
        logger = build_common.logger
        previous = logger.level
        handler = Handler()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            document = Document("effects-logging")
            def fixture():
                with bd.BuildPart() as builder:
                    bd.Box(10., 8., 4.)
                return builder.part, ()
            for _ in range(2):
                calls.clear()
                _, _, counts, _ = self.run_frontend(document, fixture)
                self.assertEqual(1, len(calls))
                self.assertEqual(0, counts.get("builder-effects-retained", 0))
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous)

    def test_context_shapelist_and_skipclean_callbacks_match_ordinary_counts(self):
        import inspect
        calls = []
        active = []
        def observe(label):
            calls.append(label)
            if active:
                self.assertEqual(0, active[0]._compute_depth)
        def fixture():
            with bd.BuildPart() as builder:
                bd.Box(2., 3., 4.)
                bd.Cylinder(.5, 8., mode=bd.Mode.SUBTRACT)
            return builder.part, ()
        for owner, name in ((bd.Builder, "_get_context"), (bd.WorkplaneList, "_get_context"),
                            (bd.ShapeList, "__init__"), (bd.SkipClean, "clean")):
            descriptor = inspect.getattr_static(owner, name)
            if name == "clean":
                class Truthy:
                    def __bool__(self):
                        observe("bool")
                        return True
                replacement = Truthy()
            elif isinstance(descriptor, classmethod):
                def callback(cls, *args, _original=descriptor.__func__, **kwargs):
                    observe("context")
                    return _original(cls, *args, **kwargs)
                replacement = classmethod(callback)
            else:
                def callback(value, *args, _original=descriptor, **kwargs):
                    observe("constructor")
                    return _original(value, *args, **kwargs)
                replacement = callback
            with self.subTest(provider=(owner.__name__, name)), patch.object(owner, name, replacement):
                calls.clear()
                expected, _ = fixture()
                expected_calls = tuple(calls)
                expected_facts = facts(expected)
                document = Document("effects-hook-" + owner.__name__)
                for _ in range(2):
                    calls.clear()
                    with document.begin() as tx:
                        with FrontendSession(tx) as frontend:
                            active[:] = [frontend]
                            actual, _ = fixture()
                            active.clear()
                            self.assertEqual(expected_calls, tuple(calls))
                            self.assertEqual(0, frontend._fallback_counts.get("builder-effects-retained", 0))
                            result = frontend.materialize(actual)
                        tx.commit()
                    self.assertEqual(expected_facts, facts(result))

    def test_workplane_iteration_callback_and_native_escape_execute_ordinarily(self):
        calls = []
        active = []
        shape_to_escape = []
        class Planes(list):
            def __iter__(self):
                calls.append("planes")
                if active:
                    self.assert_depth()
                    shape_to_escape[0].wrapped
                return super().__iter__()
            def assert_depth(self):
                if active[0]._compute_depth:
                    raise AssertionError("authored iterable entered trusted native compute")
        def fixture():
            shape_to_escape[:] = [bd.Box(1., 1., 1.)]
            with bd.BuildPart() as builder:
                context = bd.WorkplaneList._get_context()
                context.workplanes = Planes(context.workplanes)
                bd.Box(2., 3., 4.)
            return builder.part
        expected = fixture()
        expected_calls = tuple(calls)
        document = Document("effects-workplane-iterator")
        for _ in range(2):
            calls.clear()
            with document.begin() as tx:
                with FrontendSession(tx) as frontend:
                    active[:] = [frontend]
                    result = fixture()
                    active.clear()
                    self.assertEqual(expected_calls, tuple(calls))
                    self.assertEqual(0, frontend._fallback_counts.get("builder-effects-retained", 0))
                    result = frontend.materialize(result)
                tx.commit()
            self.assertEqual(facts(expected), facts(result))


if __name__ == "__main__":
    unittest.main()
