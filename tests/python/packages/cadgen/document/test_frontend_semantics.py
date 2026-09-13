"""Ordinary build123d semantics at the bounded frontend's managed edges."""

from __future__ import annotations

from contextlib import nullcontext
import copy
import unittest

import build123d as bd

from cadgen._document import Document
from cadgen._document.frontend import FrontendSession


def _facts(shape):
    bounds = shape.bounding_box()
    return (
        type(shape).__name__, shape.label, shape.material,
        round(shape.volume, 7),
        tuple(round(value, 6) for value in (*bounds.min, *bounds.max)),
        tuple(_facts(child) for child in shape.children),
    )


def _nested_group():
    first = bd.Box(4, 6, 2)
    first.label = "first"
    second = bd.Pos(8, 0, 0) * bd.Cylinder(1, 2)
    second.label = "second"
    inner = bd.Compound(children=(first, second), label="inner", material="steel")
    third = bd.Pos(-8, 0, 0) * bd.Box(2, 3, 4)
    third.label = "third"
    return bd.Compound(children=(inner, third), label="outer", material="wood")


class FrontendSemanticsTest(unittest.TestCase):
    def setUp(self):
        from cadgen._internal import op_memo
        was_installed = op_memo._installed
        if was_installed:
            op_memo.uninstall()
        self.addCleanup(op_memo.install if was_installed else lambda: None)

    def test_boolean_cleanup_context_is_part_of_identity_in_both_orders(self):
        def adjacent_boxes():
            return (bd.Box(2, 2, 2, align=(bd.Align.MAX, bd.Align.CENTER, bd.Align.CENTER))
                    + bd.Box(3, 2, 2, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER)))

        expected = {}
        for clean in (True, False):
            with nullcontext() if clean else bd.SkipClean():
                expected[clean] = len(adjacent_boxes().faces())
        self.assertNotEqual(expected[True], expected[False])

        for order in ((True, False), (False, True)):
            with self.subTest(order=order):
                document = Document(f"boolean-cleanup-{order}")
                identities = {}
                for clean in (*order, *order):
                    with document.begin(str(clean)) as transaction:
                        with FrontendSession(transaction) as frontend:
                            with nullcontext() if clean else bd.SkipClean():
                                result = adjacent_boxes()
                                handle = frontend._geometry_handle(result)
                                self.assertEqual(expected[clean], len(result.faces()))
                            native = frontend.materialize(result)
                        transaction.commit()
                    self.assertEqual(expected[clean], len(native.faces()))
                    if clean in identities:
                        self.assertEqual(identities[clean], handle.evaluation_id)
                        self.assertEqual(0, transaction.stats.computed)
                    identities[clean] = handle.evaluation_id
                self.assertNotEqual(identities[True], identities[False])

    def test_equal_adjacent_boxes_escape_before_boolean_without_replaying_python(self):
        for order in ((True, False), (False, True)):
            document = Document(f"equal-adjacent-boxes-{order}")
            calls = []
            for clean in (*order, *order):
                with nullcontext() if clean else bd.SkipClean():
                    plain = bd.Box(2, 2, 2) + bd.Pos(2, 0, 0) * bd.Box(2, 2, 2)
                with self.subTest(order=order, clean=clean):
                    before = len(calls)
                    with document.begin() as transaction:
                        with FrontendSession(transaction) as frontend:
                            def authored_box():
                                calls.append("box")
                                return bd.Box(2, 2, 2)

                            with nullcontext() if clean else bd.SkipClean():
                                result = authored_box() + bd.Pos(2, 0, 0) * authored_box()
                            self.assertEqual(1, frontend._fallback_counts["boolean-independent-partners"])
                            result = frontend.materialize(result)
                        transaction.commit()
                    self.assertEqual(before + 2, len(calls))
                    self.assertEqual(len(plain.faces()), len(result.faces()))
                    self.assertAlmostEqual(plain.volume, result.volume, places=7)
                    self.assertTrue(result.is_valid)

    def test_placed_fuse_uses_private_inputs_before_mixed_location_aliases_form(self):
        for clean in (False, True):
            with self.subTest(clean=clean):
                with nullcontext() if clean else bd.SkipClean():
                    expected = bd.Box(2, 2, 2) + bd.Pos(2.5, 0, 0) * bd.Box(3, 2, 2)
                document = Document(f"mixed-location-fuse-{clean}")
                with document.begin() as transaction:
                    with FrontendSession(transaction) as frontend:
                        with nullcontext() if clean else bd.SkipClean():
                            result = bd.Box(2, 2, 2) + bd.Pos(2.5, 0, 0) * bd.Box(3, 2, 2)
                        self.assertEqual(1, frontend._fallback_counts["boolean-placed-fuse"])
                        result = frontend.materialize(result)
                    transaction.commit()
                self.assertEqual(_facts(expected), _facts(result))
                self.assertEqual(len(expected.faces()), len(result.faces()))

    def test_ordinary_placement_copies_constructor_attributes(self):
        for operation in ("moved", "located"):
            for constructor, attributes in (
                (lambda: bd.Box(3, 5, 7), ("length", "width", "box_height")),
                (lambda: bd.Cylinder(2, 7), ("radius", "cylinder_height", "arc_size", "align")),
            ):
                with self.subTest(operation=operation, attributes=attributes):
                    expected = getattr(constructor(), operation)(bd.Pos(10, 2, 1))
                    document = Document(f"placement-attributes-{operation}-{attributes}")
                    with document.begin() as transaction:
                        with FrontendSession(transaction) as frontend:
                            result = getattr(constructor(), operation)(bd.Pos(10, 2, 1))
                            # Metadata copying must stay managed for this bounded
                            # constructor subset; attribute reads can then escape.
                            self.assertEqual({}, frontend._fallback_counts)
                            for attribute in attributes:
                                self.assertEqual(getattr(expected, attribute),
                                                 getattr(result, attribute))
                            result = frontend.materialize(result)
                        transaction.commit()
                    self.assertEqual(_facts(expected), _facts(result))

    def test_custom_attributes_use_ordinary_copy_once_without_session_locks(self):
        copied = []

        class Annotation:
            def __init__(self, values):
                self.values = values

            def __deepcopy__(self, memo):
                copied.append("copied")
                result = type(self)(copy.deepcopy(self.values, memo))
                memo[id(self)] = result
                return result

        for operation in ("moved", "located"):
            for revision in ("first", "second"):
                with self.subTest(operation=operation, revision=revision):
                    before = len(copied)
                    document = Document(f"custom-copy-{operation}-{revision}")
                    with document.begin() as transaction:
                        with FrontendSession(transaction) as frontend:
                            original = bd.Box(3, 5, 7)
                            original.annotation = Annotation([1, {"label": "original"}])
                            annotation = object.__getattribute__(original, "annotation")
                            result = getattr(original, operation)(bd.Pos(10, 2, 1))
                            self.assertEqual(before + 1, len(copied))
                            self.assertEqual(1, frontend._fallback_counts[f"{operation}-wrapper-copy"])
                            self.assertIsNot(annotation, result.annotation)
                            result.annotation.values[1]["label"] = "changed"
                            self.assertEqual("original", annotation.values[1]["label"])
                            self.assertEqual(3, result.length)
                            result = frontend.materialize(result)
                        transaction.commit()
                    self.assertFalse(hasattr(result, "_cadgen_document_state"))
                    copy.deepcopy(result)

    def test_generator_children_and_obj_are_consumed_once_in_native_fallbacks(self):
        for argument in ("children", "obj"):
            for mixed in (False, True):
                with self.subTest(argument=argument, mixed=mixed):
                    outside = bd.Pos(10, 0, 0) * bd.Box(3, 4, 5)
                    outside.label = "outside"
                    visits = []
                    document = Document(f"generator-{argument}-{mixed}")
                    with document.begin() as transaction:
                        with FrontendSession(transaction) as frontend:
                            inside = bd.Box(2, 3, 4) if mixed else outside
                            values = (inside, outside) if mixed else (outside,)

                            def once():
                                for index, value in enumerate(values):
                                    visits.append(index)
                                    yield value

                            result = bd.Compound(**{argument: once()}, label="generator")
                            self.assertEqual(list(range(len(values))), visits)
                            self.assertEqual(len(values) if argument == "children" else 0,
                                             len(result.children))
                            native = frontend.materialize(result)
                        transaction.commit()
                    self.assertAlmostEqual(84 if mixed else 60, native.volume, places=7)
                    self.assertEqual(len(values), len(native.solids()))
                    self.assertEqual(list(range(len(values))), visits)

    def test_managed_flat_compound_exposes_declared_children_and_parents_immediately(self):
        from cadgen._document.returned import bind_returned_shape

        document = Document("immediate-compound-hierarchy")
        with document.begin() as transaction:
            with FrontendSession(transaction) as frontend:
                first, second = bd.Box(2, 3, 4), bd.Pos(5, 0, 0) * bd.Box(2, 3, 4)
                result = bd.Compound(children=(first, second), label="group")
                self.assertEqual((id(first), id(second)), tuple(map(id, result.children)))
                self.assertIs(result, first.parent)
                self.assertIs(result, second.parent)
                self.assertFalse(transaction.escape_arena.active)
                bind_returned_shape(frontend, result)
                native = frontend.materialize(result)
            revision = transaction.commit()
        self.assertEqual(2, len(revision.root.children))
        self.assertIs(native, first.parent)
        self.assertIs(native, second.parent)
        self.assertAlmostEqual(48, native.volume, places=7)

    def test_nested_groups_and_placements_preserve_native_hierarchy(self):
        placements = {
            "unchanged": lambda value: value,
            "moved": lambda value: value.moved(bd.Pos(20, 3, 0) * bd.Rot(0, 0, 35)),
            "located": lambda value: value.located(bd.Pos(-7, 4, 2)),
        }
        for operation, place in placements.items():
            with self.subTest(operation=operation):
                expected = place(_nested_group())
                document = Document(f"nested-group-{operation}")
                with document.begin() as transaction:
                    with FrontendSession(transaction) as frontend:
                        group = _nested_group()
                        self.assertEqual(("inner", "third"), tuple(c.label for c in group.children))
                        self.assertEqual(("first", "second"), tuple(c.label for c in group.children[0].children))
                        result = frontend.materialize(place(group))
                        self.assertGreater(frontend._fallback_counts["compound-native-construction"], 0)
                    transaction.commit()
                self.assertEqual(_facts(expected), _facts(result))
                self.assertIs(result, result.children[0].parent)
                self.assertIs(result.children[0], result.children[0].children[0].parent)
                copy.deepcopy(result)

    def test_flat_group_placements_cross_private_boundary_before_copying(self):
        def group():
            return bd.Compound(children=(bd.Box(2, 3, 4),), label="group")

        for operation in ("moved", "located"):
            with self.subTest(operation=operation):
                expected = getattr(group(), operation)(bd.Pos(10, 2, 1))
                document = Document(f"flat-group-{operation}")
                with document.begin() as transaction:
                    with FrontendSession(transaction) as frontend:
                        result = getattr(group(), operation)(bd.Pos(10, 2, 1))
                        self.assertEqual(1, frontend._fallback_counts[f"{operation}-wrapper-copy"])
                        result = frontend.materialize(result)
                    transaction.commit()
                self.assertEqual(_facts(expected), _facts(result))

    def test_reparenting_managed_children_preserves_ordinary_group_mutation(self):
        def reparent():
            child = bd.Box(2, 3, 4)
            sibling = bd.Pos(5, 0, 0) * bd.Box(2, 3, 4)
            original = bd.Compound(children=(child, sibling), label="original")
            replacement = bd.Compound(children=(child,), label="replacement")
            return original, replacement

        expected = tuple(map(_facts, reparent()))
        document = Document("reparent-managed-child")
        with document.begin() as transaction:
            with FrontendSession(transaction) as frontend:
                original, replacement = reparent()
                actual = tuple(_facts(frontend.materialize(value))
                               for value in (original, replacement))
            transaction.commit()
        self.assertEqual(expected, actual)

    def test_custom_attachment_hooks_execute_once_and_preserve_validation(self):
        observations = []

        class ObservedBox(bd.Box):
            def _pre_attach(self, parent):
                observations.append((self.label, parent.label))
                if parent.label == "blocked":
                    raise ValueError("attachment blocked by authored hook")
                super()._pre_attach(parent)

        for kind in ("subclass", "instance", "validation"):
            with self.subTest(kind=kind):
                observations.clear()
                document = Document(f"attachment-hook-{kind}")
                with document.begin() as transaction:
                    with FrontendSession(transaction) as frontend:
                        child = bd.Box(2, 3, 4) if kind == "instance" else ObservedBox(2, 3, 4)
                        child.label = "child"
                        if kind == "instance":
                            child._pre_attach = lambda parent: observations.append(("child", parent.label))
                        if kind == "validation":
                            with self.assertRaisesRegex(ValueError, "attachment blocked"):
                                bd.Compound(children=(child,), label="blocked")
                            self.assertEqual([("child", "blocked")], observations)
                        else:
                            result = bd.Compound(children=(child,), label="group")
                            self.assertEqual([("child", "group")], observations)
                            frontend.materialize(result)
                            self.assertEqual([("child", "group")], observations)
                        self.assertGreater(frontend._fallback_counts["compound-native-construction"], 0)
                    transaction.commit()


if __name__ == "__main__":
    unittest.main()
