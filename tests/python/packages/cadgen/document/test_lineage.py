"""Exact native boolean history, allocation routes, and explicit unknowns."""
import dataclasses
import unittest
from threading import Event
from unittest.mock import patch

from cadgen._document import Document, GeometryLeaf, OperatorSpec, Mutation
from cadgen._document.consumers import RevisionConsumer, OccurrencePath
from cadgen._document.native import NativeResult, TopologyHistory, TopologyRelation, SubelementRef, history_from_builder, topology_map
from cadgen._document.lineage import capture_routes, selection, resolve
from cadgen._document.resources import Cancelled


def box(tx, dimensions=(10., 10., 2.), origin=(0., 0., 0.)):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt
    return tx.evaluate(OperatorSpec("lineage.box", mutation=Mutation.READ_ONLY),
                       (dimensions, origin), (),
                       lambda *_: NativeResult(BRepPrimAPI_MakeBox(gp_Pnt(*origin), *dimensions).Shape()))


def cut(tx, first, tool, *, complete=True, private=False):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.TopTools import TopTools_ListOfShape
    def compute(inputs, _):
        algorithm = BRepAlgoAPI_Cut()
        arguments, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
        arguments.Append(inputs[0]); tools.Append(inputs[1])
        algorithm.SetArguments(arguments)
        algorithm.SetTools(tools)
        algorithm.SetNonDestructive(True)
        algorithm.Build()
        history = history_from_builder(algorithm, inputs)
        if not complete:
            history = dataclasses.replace(history, complete=False, reason="cleanup history unavailable")
        return NativeResult(algorithm.Shape(), history)
    return tx.evaluate(OperatorSpec("lineage.cut", mutation=Mutation.PRIVATE_INPUTS if private else Mutation.READ_ONLY),
                       complete, (first, tool), compute)


def passthrough(tx, *inputs, unknown=False, generated=False):
    def compute(shapes, _):
        output = topology_map(shapes[0])
        rows = []
        for input_index, shape in enumerate(shapes):
            mapping = topology_map(shape)
            for index in range(1, mapping.Extent() + 1):
                native = mapping.FindKey(index)
                found = output.FindIndex(native)
                if found:
                    rows.append(TopologyRelation(SubelementRef(input_index, native.ShapeType().name, index),
                                                 (SubelementRef(None, native.ShapeType().name, found),)))
        history = TopologyHistory(**{("generated" if generated else "unchanged"): tuple(rows)},
                                  complete=not unknown, reason="unknown operator" if unknown else "")
        return NativeResult(shapes[0], history)
    return tx.evaluate(OperatorSpec("lineage.pass", mutation=Mutation.READ_ONLY),
                       (unknown, generated), inputs, compute)


def finish(tx, handle):
    tx.bind_root(GeometryLeaf("result", handle))
    return tx.commit()


def snapshot(doc, revision, source=None):
    with RevisionConsumer(doc, revision.revision_id) as consumer:
        return capture_routes(consumer, consumer.occurrences()[0].path, source=source)


class LineageTests(unittest.TestCase):
    def test_native_cut_modified_split_deleted_and_unknown_cleanup(self):
        doc = Document("lineage-native")
        with doc.begin() as tx:
            original = box(tx)
            tool = box(tx, (2., 12., 4.), (4., -1., -1.))
            result = cut(tx, original, tool)
            revision = finish(tx, result)
        routes = snapshot(doc, revision)
        outcomes = [resolve(routes, selection(routes, original, "face", i)) for i in range(6)]
        self.assertTrue(doc.history(result).generated)
        self.assertTrue(any(target.kind == "edge" for row in outcomes for target in row.targets),
                        "native Generated edges are retained alongside Modified face descendants")
        self.assertIn("ambiguous", [row.status for row in outcomes], "slot splits top/bottom/front/back faces")
        self.assertIn("unique", [row.status for row in outcomes], "outer end faces remain exact")
        self.assertTrue(all(row.status in {"unique", "ambiguous"} for row in outcomes))
        self.assertTrue(all(target.path == routes.target for row in outcomes for target in row.targets))
        # Deletion is proven by an enclosing subtractor, rather than inferred
        # merely from a missing generated/modified relation.
        with doc.begin() as tx:
            cover = box(tx, (20., 20., 20.), (-5., -5., -5.))
            empty = cut(tx, original, cover)
            deleted_revision = finish(tx, empty)
        deleted = snapshot(doc, deleted_revision)
        self.assertEqual("deleted", resolve(deleted, selection(deleted, original, "face", 0)).status)
        with doc.begin() as tx:
            uncertain = cut(tx, original, tool, complete=False)
            uncertain_revision = finish(tx, uncertain)
        uncertain = snapshot(doc, uncertain_revision)
        answer = resolve(uncertain, selection(uncertain, original, "face", 0))
        self.assertEqual("unavailable", answer.status)
        self.assertIn("cleanup", answer.reason)

    def test_generated_and_unchanged_exact_kind_translation(self):
        doc = Document("lineage-kind-maps")
        with doc.begin() as tx:
            original = box(tx)
            generated = passthrough(tx, original, generated=True)
            result = passthrough(tx, generated)
            revision = finish(tx, result)
        routes = snapshot(doc, revision)
        for kind, count in (("face", 6), ("edge", 12)):
            for ordinal in range(count):
                answer = resolve(routes, selection(routes, original, kind, ordinal))
                self.assertEqual("unique", answer.status)
                self.assertEqual((kind, ordinal), (answer.targets[0].kind, answer.targets[0].ordinal))
        self.assertNotEqual(0, routes.nodes[0].faces[0], "ALL ordinals are one-based")

    def test_shared_diamond_routes_coalesce_exact_targets_and_unknown_branch_blocks_selection(self):
        doc = Document("lineage-diamond")
        with doc.begin() as tx:
            source = box(tx)
            first = passthrough(tx, source)
            second = passthrough(tx, source)
            shared = passthrough(tx, first, second)
            revision = finish(tx, shared)
        routes = snapshot(doc, revision)
        self.assertNotEqual(first.allocation_id, second.allocation_id)
        self.assertEqual(first.prototype_id, second.prototype_id)
        self.assertEqual("unique", resolve(routes, selection(routes, source, "face", 0)).status)
        with doc.begin() as tx:
            unknown = passthrough(tx, source, unknown=True)
            mixed = passthrough(tx, first, unknown)
            revision = finish(tx, mixed)
        routes = snapshot(doc, revision)
        answer = resolve(routes, selection(routes, source, "face", 0))
        self.assertEqual("unavailable", answer.status)
        self.assertEqual(1, len(answer.targets), "known candidate does not erase an unknown parallel route")

    def test_independent_equal_allocations_never_gain_routes_from_prototype_identity(self):
        doc = Document("lineage-independent")
        with doc.begin() as tx:
            first = box(tx)
            independent = box(tx)
            result = passthrough(tx, first)
            revision = finish(tx, result)
        self.assertEqual(first.prototype_id, independent.prototype_id)
        routes = snapshot(doc, revision, independent)
        self.assertEqual("unavailable", resolve(routes, selection(routes, independent, "face", 0)).status)
        with doc.begin() as tx:
            coincident = passthrough(tx, first, independent)
            revision = finish(tx, coincident)
        routes = snapshot(doc, revision)
        answer = resolve(routes, selection(routes, first, "face", 0))
        self.assertEqual("unavailable", answer.status)
        self.assertIn("independent inputs", answer.reason)
        with doc.begin() as tx:
            identical = passthrough(tx, first, first)
            revision = finish(tx, identical)
        routes = snapshot(doc, revision)
        self.assertEqual("unique", resolve(routes, selection(routes, first, "face", 0)).status)

    def test_private_inputs_require_explicit_copy_correspondence(self):
        doc = Document("lineage-private")
        with doc.begin() as tx:
            first = box(tx)
            tool = box(tx, (2., 12., 4.), (4., -1., -1.))
            result = cut(tx, first, tool, private=True)
            revision = finish(tx, result)
        routes = snapshot(doc, revision)
        answer = resolve(routes, selection(routes, first, "face", 0))
        self.assertEqual("unavailable", answer.status)
        self.assertIn("history-input correspondence", answer.reason)

    def test_warm_hit_uses_current_allocation_inputs_not_original_prototype_dependencies(self):
        doc = Document("lineage-warm")
        with doc.begin() as tx:
            old = box(tx)
            old_tool = box(tx, (2., 12., 4.), (4., -1., -1.))
            old_result = cut(tx, old, old_tool)
            finish(tx, old_result)
        with doc.begin() as tx:
            current = box(tx)
            tool = box(tx, (2., 12., 4.), (4., -1., -1.))
            result = cut(tx, current, tool)
            revision = finish(tx, result)
        self.assertEqual(0, tx.stats.computed)
        self.assertEqual(3, tx.stats.reused)
        routes = snapshot(doc, revision, old)
        self.assertEqual("unavailable", resolve(routes, selection(routes, old, "face", 0)).status)
        self.assertEqual("unique", resolve(routes, selection(routes, current, "face", 0)).status)
        self.assertEqual(result.prototype_id, old_result.prototype_id)

    def test_missing_or_malformed_history_is_unavailable_not_unchanged_or_deleted(self):
        doc = Document("lineage-malformed")
        with doc.begin() as tx:
            source = box(tx)
            malformed = TopologyHistory(unchanged=(TopologyRelation(
                SubelementRef(0, "TopAbs_SOLID", 1),
                (SubelementRef(None, "TopAbs_FACE", 999_999),)),), complete=True)
            histories = (TopologyHistory(complete=True), malformed)
            handles = [tx.evaluate(OperatorSpec("lineage.bad", mutation=Mutation.READ_ONLY),
                                   i, (source,), lambda inputs, _, h=h: NativeResult(inputs[0], h))
                       for i, h in enumerate(histories)]
            revision = finish(tx, handles[0])
        for index, handle in enumerate(handles):
            if index:
                with doc.begin() as tx:
                    revision = finish(tx, handle)
            routes = snapshot(doc, revision)
            answer = resolve(routes, selection(routes, source, "face", 0))
            self.assertEqual("unavailable", answer.status)
            self.assertFalse(answer.targets)

    def test_stale_forged_scope_and_out_of_range_references_are_rejected(self):
        doc = Document("lineage-validation")
        with doc.begin() as tx:
            original = box(tx)
            result = passthrough(tx, original)
            revision = finish(tx, result)
        with RevisionConsumer(doc, revision.revision_id) as consumer:
            path = consumer.occurrences()[0].path
            for invalid in (dataclasses.replace(original, owner_id="foreign"),
                            dataclasses.replace(original, allocation_id="stale")):
                with self.assertRaises(ValueError):
                    capture_routes(consumer, path, source=invalid)
            with self.assertRaises(ValueError):
                capture_routes(consumer, OccurrencePath(path.owner_id, path.revision_id + 1, path.nodes))
            routes = capture_routes(consumer, path)
        selected = selection(routes, original, "face", 0)
        for invalid in (dataclasses.replace(selected, owner_id="foreign"),
                        dataclasses.replace(selected, revision_id=999),
                        dataclasses.replace(selected, revision_id=True),
                        dataclasses.replace(selected, prototype_id="forged"),
                        dataclasses.replace(selected, ordinal=100),
                        dataclasses.replace(selected, ordinal=True)):
            with self.assertRaises(ValueError):
                resolve(routes, invalid)
        with self.assertRaises(RuntimeError):
            capture_routes(consumer, path)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            routes.nodes[0].handle = result
        self.assertEqual("unique", resolve(routes, selected).status, "snapshot remains value-only after close")
        with doc.begin() as tx:
            replacement = box(tx, (3., 3., 3.))
            newer = finish(tx, replacement)
        doc.collect(keep_revisions=0)
        with RevisionConsumer(doc, newer.revision_id) as current:
            with self.assertRaisesRegex(ValueError, "no longer retained"):
                capture_routes(current, current.occurrences()[0].path, source=original)

    def test_native_state_unchanged_and_budgets_cancellation(self):
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRep import BRep_Tool
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS
        from cadgen._document import lineage
        doc = Document("lineage-readonly")
        with doc.begin() as tx:
            original = box(tx)
            result = passthrough(tx, original)
            revision = finish(tx, result)
        native = doc._get(original).shape
        BRepMesh_IncrementalMesh(native, .01, False, .2, False)
        def state():
            mapping = topology_map(native)
            return tuple((mapping.FindKey(i).ShapeType().name, mapping.FindKey(i).Location().IsIdentity(),
                          BRep_Tool.Triangulation_s(TopoDS.Face_s(mapping.FindKey(i)), TopLoc_Location()).NbTriangles())
                         for i in range(1, mapping.Extent() + 1) if mapping.FindKey(i).ShapeType().name == "TopAbs_FACE")
        before = state()
        allocations = len(doc._allocations)
        routes = snapshot(doc, revision)
        selected = selection(routes, original, "face", 0)
        self.assertEqual("unique", resolve(routes, selected).status)
        self.assertEqual(before, state())
        self.assertEqual(allocations, len(doc._allocations))
        event = Event(); event.set()
        with self.assertRaises(Cancelled):
            resolve(routes, selected, cancellation=event)
        with patch.object(lineage, "MAX_WORK", 1):
            with self.assertRaisesRegex(ValueError, "work limit"):
                resolve(routes, selected)
        with patch.object(lineage, "MAX_NODES", 1):
            with self.assertRaisesRegex(ValueError, "allocation limit"):
                snapshot(doc, revision)
        with patch.object(lineage, "MAX_TOPOLOGY", 1):
            with self.assertRaisesRegex(ValueError, "topology limit"):
                snapshot(doc, revision)
