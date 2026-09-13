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

    def test_chained_absolute_locations_replace_prior_placement_and_reuse_mesh(self):
        from cadgen._document.consumers import RevisionConsumer
        from cadgen._document.frontend import _state
        from cadgen._document.meshing import mesh_for_occurrence
        from cadgen._document.returned import bind_returned_shape

        def model(target, repeated):
            original = bd.Box(2, 3, 4).moved(bd.Pos(10, 2, 1) * bd.Rot(0, 0, 30))
            if repeated:
                original = original.located(bd.Pos(-4, 3, 5)).moved(bd.Pos(2, 0, 0))
            return original, original.located(target)

        for repeated in (False, True):
            document = Document(f"located-chain-{repeated}")
            prototype_ids, packets = [], []
            for turn, shift in enumerate((20, 35, 20)):
                target = bd.Pos(shift, 4, 2) * bd.Rot(0, 0, -20)
                source, expected = model(target, repeated)
                expected_source = _facts(source)
                with document.begin() as transaction:
                    with FrontendSession(transaction) as frontend:
                        original, result = model(target, repeated)
                        self.assertFalse(_state(result).private)
                        bind_returned_shape(frontend, result)
                        prototype_ids.append(_state(result).handle.prototype_id)
                        # Changing only absolute placement neither rebuilds
                        # the copied native prototype nor changes its mesh.
                        if turn:
                            self.assertEqual(0, transaction.stats.computed)
                        result = frontend.materialize(result)
                        original = frontend.materialize(original)
                    revision = transaction.commit()
                self.assertEqual(_facts(expected), _facts(result))
                self.assertEqual(expected_source, _facts(original))
                with RevisionConsumer(document, revision.revision_id) as consumer:
                    packets.append(mesh_for_occurrence(consumer, consumer.occurrences()[0].path))
                    self.assertEqual(int(turn == 0), consumer.metrics.derivations_computed)
            self.assertEqual(1, len(set(prototype_ids)))
            self.assertTrue(all(packet is packets[0] for packet in packets))

    def test_located_then_moved_assembly_child_supports_native_queries(self):
        document = Document("copied-child-query")
        def model():
            return bd.Compound(children=(bd.Pos(7, 2, 0) * bd.Box(2, 3, 4),)).located(bd.Pos(10, 0, 0))
        expected = model()
        with document.begin() as transaction:
            with FrontendSession(transaction) as frontend:
                copied = model()
                child = object.__getattribute__(copied, "_NodeMixin__children")[0]
                self.assertEqual(str(expected.children[0].bounding_box()), str(child.bounding_box()))
                result = frontend.materialize(copied)
            transaction.commit()
        self.assertEqual(_facts(expected), _facts(result))

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
                for turn in range(2):
                    with document.begin() as transaction:
                        with FrontendSession(transaction) as frontend:
                            group = _nested_group()
                            inner, third = group.children
                            first, second = inner.children
                            self.assertEqual(("inner", "third"), tuple(c.label for c in group.children))
                            self.assertEqual(("first", "second"), tuple(c.label for c in inner.children))
                            self.assertIs(group, inner.parent)
                            self.assertIs(group, third.parent)
                            self.assertIs(inner, first.parent)
                            self.assertIs(inner, second.parent)
                            self.assertFalse(transaction.escape_arena.active)
                            self.assertEqual(0, frontend._fallback_counts.get("compound-native-construction", 0))
                            if turn:
                                self.assertEqual(0, transaction.stats.computed)
                                self.assertGreaterEqual(transaction.stats.reused, 3)
                            result = frontend.materialize(place(group))
                            if operation == "unchanged":
                                self.assertIs(group, result)
                                self.assertIs(inner, result.children[0])
                                self.assertIs(first, result.children[0].children[0])
                                if turn:
                                    self.assertEqual(0, transaction.stats.computed)
                        transaction.commit()
                    self.assertEqual(_facts(expected), _facts(result))
                    self.assertIs(result, result.children[0].parent)
                    self.assertIs(result.children[0], result.children[0].children[0].parent)
                    self.assertEqual(_facts(result), _facts(copy.deepcopy(result)))

    def test_flat_group_placements_retain_validated_wrapper_trees(self):
        def group():
            return bd.Compound(children=(bd.Box(2, 3, 4),), label="group")

        for operation in ("moved", "located"):
            with self.subTest(operation=operation):
                expected = getattr(group(), operation)(bd.Pos(10, 2, 1))
                document = Document(f"flat-group-{operation}")
                for turn in range(2):
                    with document.begin() as transaction:
                        with FrontendSession(transaction) as frontend:
                            result = getattr(group(), operation)(bd.Pos(10, 2, 1))
                            self.assertEqual({}, frontend._fallback_counts)
                            if turn:
                                self.assertEqual(0, transaction.stats.computed)
                            result = frontend.materialize(result)
                        transaction.commit()
                    self.assertEqual(_facts(expected), _facts(result))

    def test_assembly_copy_isolates_wrappers_allocations_and_appearance(self):
        from cadgen._document.frontend import _state
        from cadgen._document.returned import bind_returned_shape

        red = (1., 0., 0., .5)
        location = bd.Pos(10, 2, 1) * bd.Rot(0, 0, 25)

        def group():
            source = bd.Box(2, 3, 4)
            source.label = "leaf"
            source.color = bd.Color(.1, .2, .3, .4)
            source.material = "steel"
            source.cad_material = {"roughness": .2}
            source.cad_face_ordinal_colors = {1: red}
            first = bd.Pos(0, 0, 0) * source
            second = bd.Pos(7, 0, 0) * source
            result = bd.Compound(children=(first, second), label="assembly", material="wood")
            result.cad_material = {"metalness": .7}
            return result

        for operation in ("moved", "located"):
            with self.subTest(operation=operation):
                expected_source = group()
                expected = getattr(expected_source, operation)(location)
                expected.children[0].label = "changed"
                expected.children[0].cad_material["roughness"] = .6

                document = Document(f"assembly-copy-appearance-{operation}")
                for turn in range(2):
                    with document.begin() as transaction:
                        with FrontendSession(transaction) as frontend:
                            source = group()
                            result = getattr(source, operation)(location)
                            self.assertEqual({}, frontend._fallback_counts)
                            self.assertIsNot(source, result)
                            self.assertIsNot(source.children[0], result.children[0])
                            self.assertIs(source, source.children[0].parent)
                            self.assertIs(result, result.children[0].parent)
                            self.assertIsNot(source.cad_material, result.cad_material)
                            self.assertIsNot(source.children[0].cad_material,
                                             result.children[0].cad_material)
                            self.assertIsNot(source.children[0].cad_face_ordinal_colors,
                                             result.children[0].cad_face_ordinal_colors)
                            first = _state(result.children[0]).handle
                            second = _state(result.children[1]).handle
                            self.assertEqual(first.prototype_id, second.prototype_id)
                            self.assertNotEqual(first.allocation_id, second.allocation_id)

                            result.children[0].label = "changed"
                            result.children[0].cad_material["roughness"] = .6
                            self.assertEqual("leaf", source.children[0].label)
                            self.assertEqual(.2, source.children[0].cad_material["roughness"])
                            root = bind_returned_shape(frontend, result)
                            self.assertEqual(.7, root.appearance["pbr"]["metalness"])
                            self.assertEqual(.6, root.children[0].appearance["pbr"]["roughness"])
                            self.assertEqual(((0, red),), root.children[0].appearance["face_colors"])
                            if turn:
                                self.assertEqual(0, transaction.stats.computed)
                            result = frontend.materialize(result)
                        transaction.commit()
                    self.assertEqual(_facts(expected), _facts(result))
                    self.assertFalse(result.children[0].wrapped.IsPartner(
                        result.children[1].wrapped
                    ))

    def test_callback_bearing_appearance_mapping_uses_private_copy_once(self):
        copied = []

        class ObservedMapping(dict):
            def __deepcopy__(self, memo):
                copied.append("copied")
                result = type(self)(self)
                memo[id(self)] = result
                return result

        document = Document("appearance-mapping-private-copy")
        with document.begin() as transaction:
            with FrontendSession(transaction) as frontend:
                source = bd.Box(2, 3, 4)
                source.cad_material = ObservedMapping(roughness=.2)
                result = source.moved(bd.Pos(4, 0, 0))
                self.assertEqual(["copied"], copied)
                self.assertEqual(1, frontend._fallback_counts["moved-wrapper-copy"])
                self.assertIsNot(source.cad_material, result.cad_material)
                frontend.materialize(result)
            transaction.commit()

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
