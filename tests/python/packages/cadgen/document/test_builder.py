"""Solid builder primitive reuse with ordinary private context effect replay."""
from __future__ import annotations

import inspect
from functools import wraps
import unittest
from unittest.mock import patch

from cadgen import build123d as bd
from cadgen._document import Document
from cadgen._document.frontend import FrontendSession


def facts(shape):
    if shape is None:
        return None
    bounds = shape.bounding_box()
    return (round(shape.volume, 6), tuple(round(value, 6) for value in bounds.min),
            tuple(round(value, 6) for value in bounds.max), len(shape.solids()),
            len(shape.faces()), len(shape.edges()), bool(shape.is_valid))


def effects(builder):
    """Inspect observable state, including native aliases used by LAST/NEW."""
    combined = [solid for shape in builder.to_combine if shape is not None
                for solid in shape.solids()]
    lasts = builder.solids(bd.Select.LAST)
    aliases = sum(a.wrapped.IsSame(b.wrapped) for a in lasts for b in combined)
    return (facts(builder.part), facts(builder.obj_before),
            tuple(facts(shape) for shape in builder.to_combine),
            tuple(len(getattr(builder, kind)(bd.Select.LAST))
                  for kind in ("vertices", "edges", "faces", "solids")),
            len(builder.edges(bd.Select.NEW)), aliases,
            len(builder.pending_edges), len(builder.pending_faces))


def mode_fixture():
    observations = []
    with bd.BuildPart() as part:
        first = bd.Box(12, 10, 4)
        observations.append(effects(part))
        bd.Cylinder(2, 8, mode=bd.Mode.SUBTRACT)
        observations.append(effects(part))
        private = bd.Box(2, 3, 4, mode=bd.Mode.PRIVATE)
        observations.append(effects(part))
        bd.Box(9, 7, 3, mode=bd.Mode.REPLACE)
        observations.append(effects(part))
        observations.append((first.length, tuple(first.rotation), first.mode,
                             private.volume, private.mode))
    return part.part, observations


def locations_fixture():
    with bd.BuildPart(bd.Plane.XY.offset(3), bd.Plane.XY.offset(12)) as part:
        with bd.Locations((-6, 0), (6, 0)):
            box = bd.Box(4, 3, 2, rotation=(0, 0, 25),
                         align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
        first = effects(part)
        with bd.Locations((-4, 0, 0), (8, 0, 0)):
            cylinder = bd.Cylinder(0.5, 20, mode=bd.Mode.SUBTRACT)
        second = effects(part)
    return part.part, (first, second, len(box.solids()), len(cylinder.solids()))


def nested_fixture():
    def helper():
        with bd.BuildPart() as separate:
            bd.Box(2, 3, 4)
        return separate

    with bd.BuildPart() as outer:
        bd.Box(10, 10, 4)
        before_helper = facts(outer.part)
        separate = helper()  # A different Python frame must not transfer.
        after_helper = facts(outer.part)
        with bd.BuildPart(mode=bd.Mode.SUBTRACT) as hole:
            bd.Cylinder(2, 10)
        after_nested = effects(outer)
        with bd.BuildPart(mode=bd.Mode.PRIVATE) as private:
            bd.Box(3, 4, 5)
        after_private = effects(outer)
    return outer.part, (before_helper, after_helper, after_nested, after_private,
                        separate.builder_parent is None, hole.builder_parent is outer,
                        private.builder_parent is outer, facts(private.part))


class BuilderTest(unittest.TestCase):
    def setUp(self):
        from cadgen._internal import op_memo
        installed = op_memo._installed
        if installed:
            op_memo.uninstall()
        self.addCleanup(op_memo.install if installed else lambda: None)

    def run_model(self, document, model):
        with document.begin() as transaction:
            with FrontendSession(transaction) as frontend:
                result, observations = model()
                fallbacks = dict(frontend._fallback_counts)
                native = frontend.materialize(result)
            revision = transaction.commit()
        return native, observations, transaction.stats, fallbacks, revision

    def test_modes_and_last_new_effects_match_on_primitive_hits(self):
        expected, observations = mode_fixture()
        document = Document("builder-modes")
        for turn in range(2):
            actual, recorded, stats, fallbacks, _ = self.run_model(document, mode_fixture)
            self.assertEqual(facts(expected), facts(actual))
            self.assertEqual(observations, recorded)
            self.assertEqual(4, fallbacks["builder-effects-replayed"])
            if turn:
                self.assertGreater(stats.reused, 4)
                self.assertEqual(1, fallbacks["builder-effects-retained"])
                # The first complete stock effect is retained. The authored
                # topology observations then escape and revoke later effects;
                # those native actions and their captures still execute.
                self.assertGreater(stats.computed, 0)

    def test_locations_workplanes_rotation_and_alignment(self):
        expected, observations = locations_fixture()
        document = Document("builder-locations")
        for _ in range(2):
            actual, recorded, *_ = self.run_model(document, locations_fixture)
            self.assertEqual(facts(expected), facts(actual))
            self.assertEqual(observations, recorded)

    def test_nested_same_scope_different_scope_and_private_lifecycle(self):
        lifecycle = tuple(inspect.getattr_static(bd.Builder, name)
                          for name in ("__init__", "__enter__", "__exit__"))
        expected, observations = nested_fixture()
        document = Document("builder-nested")
        def checked():
            self.assertEqual(lifecycle, tuple(inspect.getattr_static(bd.Builder, name)
                                             for name in ("__init__", "__enter__", "__exit__")))
            return nested_fixture()
        for _ in range(2):
            actual, recorded, *_ = self.run_model(document, checked)
            self.assertEqual(facts(expected), facts(actual))
            self.assertEqual(observations, recorded)

    def test_caught_failures_and_selector_callbacks_execute_each_replay(self):
        calls = []
        def fixture():
            observations = []
            with bd.BuildPart() as part:
                try:
                    bd.Box(2, 3, 4, mode=bd.Mode.SUBTRACT)
                except RuntimeError as error:
                    observations.append((type(error).__name__, str(error), effects(part)))
                try:
                    bd.Cylinder(0, 2)
                except Exception as error:
                    observations.append((type(error).__name__, str(error), effects(part)))
                bd.Box(10, 8, 4)
                # LAST is a native-identity set difference with no stable
                # cross-build iteration order. Author an explicit value order.
                selected = part.edges(bd.Select.LAST).sort_by(lambda edge: edge.length).filter_by(
                    lambda edge: calls.append(round(edge.length, 6)) or True)
                observations.append(len(selected))
            return part.part, observations
        expected, observations = fixture()
        expected_calls = tuple(calls)
        document = Document("builder-errors")
        for _ in range(2):
            calls.clear()
            actual, recorded, *_ = self.run_model(document, fixture)
            self.assertEqual(facts(expected), facts(actual))
            self.assertEqual(observations, recorded)
            self.assertEqual(expected_calls, tuple(calls))

    def test_sketch_line_and_unsupported_solid_stay_private(self):
        def fixture():
            with bd.BuildPart() as part:
                bd.Box(8, 8, 2)
                with bd.BuildSketch(bd.Plane.XY.offset(2)):
                    with bd.BuildLine():
                        bd.Polyline((0, 0), (2, 0), (2, 2), (0, 2), close=True)
                    bd.make_face()
                pending = (len(part.pending_faces), len(part.pending_edges))
                bd.extrude(amount=2)
                bd.Sphere(1, mode=bd.Mode.SUBTRACT)
            return part.part, pending
        expected, observations = fixture()
        document = Document("builder-unsupported")
        for _ in range(2):
            actual, recorded, *_ = self.run_model(document, fixture)
            self.assertEqual(facts(expected), facts(actual))
            self.assertEqual(observations, recorded)

    def test_builder_mutation_cannot_change_retained_primitive(self):
        document = Document("builder-private-primitives")
        def fixture():
            with bd.BuildPart() as part:
                primitive = bd.Box(4, 5, 6)
                original = facts(part.part)
                # LAST and the authored constructor share ordinary private
                # input topology, even when the primitive comes from a hit.
                self.assertEqual(1, sum(a.wrapped.IsSame(b.wrapped)
                                       for a in part.solids(bd.Select.LAST)
                                       for b in primitive.solids()))
            return part.part, original
        first, original, *_ = self.run_model(document, fixture)
        first.move(bd.Pos(100, 0, 0))
        second, recorded, stats, fallbacks, _ = self.run_model(document, fixture)
        self.assertEqual(original, recorded)
        self.assertEqual(original, facts(second))
        self.assertGreater(stats.reused, 1)
        self.assertEqual(1, fallbacks["builder-effects-retained"])
        self.assertNotEqual(facts(first), facts(second))

    def test_custom_kernel_wrapper_is_opaque_and_runs_once_per_constructor(self):
        descriptor = inspect.getattr_static(bd.Solid, "make_box")
        calls = []
        @wraps(descriptor.__func__)
        def authored(cls, *args, **kwargs):
            calls.append(tuple(args))
            return descriptor.__func__(cls, *args, **kwargs)
        def fixture():
            with bd.BuildPart() as part:
                bd.Box(2, 3, 4)
            return part.part, None
        document = Document("builder-authored-kernel-hook")
        with patch.object(bd.Solid, "make_box", classmethod(authored)):
            for _ in range(2):
                _, _, stats, fallbacks, _ = self.run_model(document, fixture)
                self.assertEqual(0, stats.reused)
                self.assertEqual(1, fallbacks["builder-opaque-constructor"])
        self.assertEqual([(2, 3, 4), (2, 3, 4)], calls)
        def static_factory(length, width, height):
            calls.append((length, width, height))
            return descriptor.__get__(None, bd.Solid)(length, width, height)
        with patch.object(bd.Solid, "make_box", staticmethod(static_factory)):
            self.run_model(document, fixture)
        self.assertEqual([(2, 3, 4)] * 3, calls)

    def test_validation_callback_keeps_normal_managed_escape_checks(self):
        calls = []
        def fixture():
            observer = bd.Box(2, 3, 4)
            with bd.BuildPart() as part:
                validate = part.validate_inputs
                def authored(*args, **kwargs):
                    # Direct native access inside ordinary callbacks must
                    # materialize the private wrapper just as it does outside.
                    calls.append(observer._wrapped is not None)
                    return validate(*args, **kwargs)
                part.validate_inputs = authored
                bd.Box(6, 7, 8)
            return part.part, None
        document = Document("builder-validation-callback")
        for _ in range(2):
            self.run_model(document, fixture)
        self.assertEqual([True, True], calls)


if __name__ == "__main__":
    unittest.main()
