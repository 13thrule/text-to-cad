"""Stock regular polygon constructors retain their actual generated profile."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import build123d as bd

from cadgen._document import Document
from cadgen._document.frontend import FrontendSession


def model(radius=2., sides=6, *, major=True, rotation=30., align=(bd.Align.CENTER, bd.Align.CENTER)):
    with bd.BuildPart() as part:
        bd.Box(12, 12, 3)
        with bd.BuildSketch(bd.Plane.XY.offset(1)):
            profile = bd.RegularPolygon(radius, sides, major, rotation, align)
        bd.extrude(amount=3, mode=bd.Mode.SUBTRACT)
    return part.part, profile


def facts(result):
    part, _profile = result
    box = part.bounding_box()
    return (round(part.volume, 8), round(part.area, 8), len(part.faces()),
            tuple(round(value, 8) for value in (*box.min, *box.max)))


class RegularPolygonEffectsTests(unittest.TestCase):
    def setUp(self):
        from cadgen._internal import op_memo
        installed = op_memo._installed
        if installed:
            op_memo.uninstall()
        self.addCleanup(op_memo.install if installed else lambda: None)

    def test_rotated_major_minor_and_aligned_profiles_match_stock_and_reuse(self):
        for sides, major, rotation, align in (
                (6, True, 30., (bd.Align.CENTER, bd.Align.CENTER)),
                (5, False, 17., (bd.Align.MIN, bd.Align.MAX))):
            settings = dict(sides=sides, major=major, rotation=rotation, align=align)
            expected = facts(model(**settings))
            document = Document(f"regular-polygon-{sides}")
            for turn in range(2):
                with document.begin() as tx:
                    with FrontendSession(tx) as frontend:
                        actual = model(**settings)
                        self.assertFalse(tx.escape_arena.active)
                        self.assertEqual(1, frontend._fallback_counts.get("sketch-effects-retained"))
                        self.assertEqual(1, frontend._fallback_counts.get("sketch-extrusion-retained"))
                        if turn:
                            self.assertEqual(0, tx.stats.computed)
                            self.assertGreater(tx.stats.reused, 0)
                        # Exact inspection may deliberately materialize private
                        # geometry; measure retention before invoking that door.
                        self.assertEqual(expected, facts(actual))
                    tx.commit()

    def test_profile_edit_recomputes_only_affected_operations(self):
        document = Document("regular-profile-edit")
        expected = [facts(model(radius)) for radius in (2., 2.2)]
        for turn, radius in enumerate((2., 2.2)):
            with document.begin() as tx:
                with FrontendSession(tx):
                    actual = model(radius)
                    self.assertFalse(tx.escape_arena.active)
                    if turn:
                        self.assertGreater(tx.stats.computed, 0)
                        self.assertGreater(tx.stats.reused, 0)
                    self.assertEqual(expected[turn], facts(actual))
                tx.commit()

    def test_constructor_provider_runs_normally_on_every_replay(self):
        original = bd.RegularPolygon.__init__
        calls = []
        def authored(shape, *args, **kwargs):
            calls.append(args)
            return original(shape, *args, **kwargs)
        expected = facts(model())
        document = Document("regular-provider-replay")
        with patch.object(bd.RegularPolygon, "__init__", authored):
            for _ in range(2):
                with document.begin() as tx:
                    with FrontendSession(tx) as frontend:
                        self.assertEqual(expected, facts(model()))
                        self.assertIsNone(frontend._fallback_counts.get("sketch-effects-retained"))
                    tx.commit()
        self.assertEqual(2, len(calls))

    def test_constructor_callback_cannot_bind_its_unrelated_face_to_the_profile(self):
        def build():
            with bd.BuildSketch() as sketch:
                profile = bd.RegularPolygon(2, 6)
            return profile, sketch.sketch
        # sort_by is an explicitly guarded provider; Vector.center is ordinary
        # source-side work before the wire, so final capture provenance must
        # reject its callback's unrelated tool independently of provider proof.
        for owner, name in ((bd.ShapeList, "sort_by"), (bd.Vector, "center")):
            original = getattr(owner, name)
            calls = []
            def callback(value, *args, **kwargs):
                if not calls:
                    calls.append("callback")
                    face = bd.Face(bd.Wire.make_polygon([
                        bd.Vector(x, y) for x, y in ((20, 0), (23, 0), (23, 3), (20, 3))]))
                    bd.BuildSketch._get_context()._add_to_context(*face.faces(), mode=bd.Mode.ADD)
                return original(value, *args, **kwargs)
            with patch.object(owner, name, callback):
                profile, sketch = build()
                expected = (profile.area, sketch.area)
            document = Document("regular-reentrant-" + name)
            for _turn in range(2):
                calls.clear()
                with document.begin() as tx:
                    with FrontendSession(tx):
                        with patch.object(owner, name, callback):
                            profile, sketch = build()
                            self.assertAlmostEqual(expected[0], profile.area)
                            self.assertAlmostEqual(expected[1], sketch.area)
                    tx.commit()
                self.assertEqual(["callback"], calls)

    def test_argument_errors_keep_the_stock_constructor_behavior(self):
        for sides in (2, True):
            with self.assertRaises(ValueError) as expected:
                model(sides=sides)
            with Document("regular-invalid").begin() as tx:
                with FrontendSession(tx):
                    with self.assertRaises(type(expected.exception)) as actual:
                        model(sides=sides)
                    self.assertEqual(str(expected.exception), str(actual.exception))
