"""Deferred stock hierarchy ownership and exact private escape behavior."""
import copy
import functools
import json
import unittest
from contextlib import nullcontext
from unittest.mock import patch

from cadgen import build123d as bd
from cadgen._document import Document
from cadgen._document.display import build_display
from cadgen._document.frontend import FrontendSession, _state
from cadgen._document.returned import bind_returned_shape


def nested(shift=0):
    box, cylinder = bd.Box(2, 3, 4), bd.Cylinder(1, 4)
    leaves = [bd.Pos(i * 5 + shift, 0, 0) * (box if i % 2 else cylinder) for i in range(24)]
    group = bd.Compound(children=leaves, label="nested")
    root = bd.Compound(children=[group], label="root")
    return root, group, leaves


def facts(shape):
    bounds = shape.bounding_box()
    return (round(shape.volume, 7), tuple(round(v, 7) for v in bounds.min),
            tuple(round(v, 7) for v in bounds.max), len(shape.solids()))


class NestedHierarchyTests(unittest.TestCase):
    def setUp(self):
        from cadgen._internal import op_memo
        installed = op_memo._installed
        if installed:
            op_memo.uninstall()
        self.addCleanup(op_memo.install if installed else lambda: None)

    def test_nested_source_24_occurrences_have_two_assets_and_no_placement_recompute(self):
        document, previous = Document("nested-display"), None
        for shift in (0, 0, 5):
            with document.begin() as tx:
                with FrontendSession(tx) as frontend:
                    root, group, leaves = nested(shift)
                    self.assertIs(group.parent, root)
                    self.assertEqual(tuple(leaves), group.children)
                    self.assertTrue(all(leaf.parent is group for leaf in leaves))
                    self.assertIsNotNone(_state(root).children)
                    self.assertTrue(all(not _state(leaf).private for leaf in leaves))
                    bind_returned_shape(frontend, root)
                revision = tx.commit()
            product = build_display(document, revision.revision_id, previous=previous)
            self.assertEqual(2, len(product.assets))
            self.assertEqual(26, len(json.loads(product.manifest)["nodes"]))
            if previous:
                self.assertEqual(0, tx.stats.computed)
                self.assertTrue(all(previous.assets[key] is asset for key, asset in product.assets.items()))
            previous = product

    def test_recursive_native_escape_preserves_original_nodes_and_runs_once(self):
        expected = facts(nested()[0])
        document = Document("nested-escape")
        with document.begin() as tx:
            with FrontendSession(tx) as frontend:
                root, group, leaves = nested()
                original = frontend._native_originals["compound_init"]
                calls = []
                def construct(*args, **kwargs):
                    calls.append(kwargs["label"])
                    return original(*args, **kwargs)
                with patch.dict(frontend._native_originals, compound_init=construct):
                    actual = frontend.materialize(root)
                    _ = actual.wrapped
                    _ = actual.wrapped
                self.assertEqual(["nested", "root"], calls)
                self.assertIs(actual, root)
                self.assertIs(root.children[0], group)
                self.assertTrue(all(a is b for a, b in zip(group.children, leaves)))
                self.assertIs(group.parent, root)
                self.assertTrue(all(leaf.parent is group for leaf in leaves))
                self.assertEqual(expected, facts(actual))
                wrapped = actual.wrapped
                self.assertIs(wrapped, actual.wrapped)
            tx.commit()

    def test_descendant_mutation_retains_stock_parent_native_snapshot(self):
        for nested_group in (False, True):
            for query_first in (False, True):
                with self.subTest(nested=nested_group, query_first=query_first):
                    def model():
                        leaf = bd.Box(2, 3, 4)
                        group = bd.Compound(children=[leaf])
                        root = bd.Compound(children=[group]) if nested_group else group
                        if query_first:
                            _ = group.volume
                        # Native compounds keep the original placement while
                        # the author mutates the same attached child wrapper.
                        leaf.move(bd.Pos(100, 0, 0))
                        return root, group, leaf
                    expected = tuple(facts(shape) for shape in model())
                    document = Document("nested-alias")
                    with document.begin() as tx:
                        with FrontendSession(tx) as frontend:
                            shapes = model()
                            self.assertEqual(expected, tuple(facts(shape) for shape in shapes))
                            self.assertIs(shapes[2], shapes[1].children[0])
                            frontend.materialize(shapes[0])
                        tx.commit()

    def test_reparent_copy_and_moved_groups_match_ordinary_build123d(self):
        def model():
            leaf = bd.Box(2, 3, 4)
            first = bd.Compound(children=[leaf], label="first")
            root = bd.Compound(children=[first])
            second = bd.Compound(children=[leaf], label="second")
            copied = copy.deepcopy(second)
            moved = bd.Pos(20, 0, 0) * second
            return root, first, second, copied, moved, leaf
        ordinary = model()
        expected = [facts(shape) for shape in ordinary if shape.wrapped and not shape.wrapped.IsNull()]
        document = Document("nested-tree-mutations")
        with document.begin() as tx:
            with FrontendSession(tx):
                actual = model()
                self.assertEqual(expected, [facts(shape) for shape in actual if shape.wrapped and not shape.wrapped.IsNull()])
                self.assertIs(actual[-1].parent, actual[2])
                self.assertEqual((), actual[1].children)
                self.assertIsNot(actual[3].children[0], actual[-1])
                self.assertTrue(_state(actual[4]).private)
            tx.commit()

    def test_wrapped_hooks_before_or_during_session_execute_exactly_as_stock_path(self):
        original = bd.Compound._post_attach_children
        for when in ("before", "during", "spoofed-metadata"):
            events = []
            @functools.wraps(original)
            def observed(self, children):
                events.append((self.label, len(children)))
                return original(self, children)
            if when == "spoofed-metadata":
                del observed.__wrapped__
            with patch.object(bd.Compound, "_post_attach_children", observed):
                nested()
            expected, events[:] = list(events), []
            document = Document("nested-hooks")
            before = patch.object(bd.Compound, "_post_attach_children", observed) if when != "during" else nullcontext()
            during = patch.object(bd.Compound, "_post_attach_children", observed) if when == "during" else nullcontext()
            with before, document.begin() as tx:
                with FrontendSession(tx), during:
                    root, _, _ = nested()
                    self.assertTrue(_state(root).private)
                tx.commit()
            self.assertEqual(expected, events, when)

    def test_custom_subclass_attachment_effects_are_not_skipped(self):
        events = []
        class Custom(bd.Compound):
            def _post_attach(self, parent):
                events.append(parent.label)
                super()._post_attach(parent)
        def model():
            return bd.Compound(children=[Custom(children=[bd.Box(1, 2, 3)])], label="root")
        expected = facts(model())
        self.assertEqual(["root"], events)
        events.clear()
        document = Document("nested-custom")
        with document.begin() as tx:
            with FrontendSession(tx):
                root = model()
                self.assertEqual(expected, facts(root))
            tx.commit()
        self.assertEqual(["root"], events)

    def test_replaced_native_compound_helper_runs_instead_of_being_skipped(self):
        from build123d.topology import composite
        original = composite._make_topods_compound_from_shapes
        events = []
        @functools.wraps(original)
        def observed(shapes):
            shapes = tuple(shapes)
            events.append(len(shapes))
            return original(shapes)
        with patch.object(composite, "_make_topods_compound_from_shapes", observed):
            nested()
        expected = list(events)
        events.clear()
        document = Document("nested-provider")
        with document.begin() as tx:
            with FrontendSession(tx), patch.object(composite, "_make_topods_compound_from_shapes", observed):
                root, _, _ = nested()
                self.assertTrue(_state(root).private)
            tx.commit()
        self.assertEqual(expected, events)

    def test_replaced_volume_getter_executes_as_private_python_on_each_call(self):
        original = bd.Compound.volume
        events = []
        @functools.wraps(original.fget)
        def observed(shape):
            # Creating CAD here must not run under an outer query reservation.
            events.append(len(bd.Box(1, 1, 1).solids()))
            return original.fget(shape)
        document = Document("nested-volume-callback")
        with patch.object(bd.Compound, "volume", property(observed)), document.begin() as tx:
            with FrontendSession(tx):
                part = bd.Box(2, 3, 4)
                self.assertAlmostEqual(24, part.volume)
                self.assertAlmostEqual(24, part.volume)
            tx.commit()
        self.assertEqual([1, 1], events)
