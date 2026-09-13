"""Face style proofs use transfer identity across independent STEP sessions."""
from dataclasses import FrozenInstanceError, replace
import hashlib
import os
import re
import unittest
from unittest.mock import patch

from cadgen._document import Document, Mutation, NativeResult, OperatorSpec
from cadgen._document.roots import AssemblyGroup, GeometryLeaf
from cadgen._document.step_faces import FaceTransferError
from cadgen._document.step_product import StepProductSession, _read_saved_metadata
from cadgen._document import step_product
from tests.python.packages.cadgen.document.test_appearance import RED, BLUE
from tests.python.packages.cadgen.document.test_step_product import translation


class StepFaceProofTests(unittest.TestCase):
    def setUp(self):
        from tests.python.packages.cadgen.document.test_appearance import AppearanceNativeTests
        self.fixture = AppearanceNativeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.directory = self.fixture.directory

    def session(self, document, revision):
        return StepProductSession(document, revision.revision_id, work_directory=self.directory)

    def test_repeats_nested_placement_variants_and_both_canonicalizers(self):
        import cadgen.step_export as exporter
        document, revision = self.fixture._styled_cut()
        red, green = revision.root.children
        again = replace(red, node_id="again", label="again", transform=translation(50, 0, 0))
        root = AssemblyGroup("root", (AssemblyGroup("nested", (red, green, again),
                             translation(0, 20, 0), "nested"),), translation(100, 0, 0), "root")
        with document.begin() as tx:
            tx.bind_root(root, unrepresented_metadata=())
            revision = tx.commit()
        products = []
        for mode, helper in (("file", "_canonicalize_style_tail_in_file"),
                             ("model", "_apply_style_tail_plan_in_model")):
            with patch.dict(os.environ, {"CADGEN_STEP_STYLE_REORDER": mode}), \
                 patch.object(exporter, helper, wraps=getattr(exporter, helper)) as canonicalize, \
                 self.session(document, revision) as session:
                product = session.prepare("nested.step")
                self.assertGreater(canonicalize.call_count, 0)
            inventory = product.saved_faces
            self.assertEqual(product.sha256, inventory.step_sha256)
            self.assertEqual(len(product.payload), inventory.step_bytes)
            self.assertEqual(2, len(inventory.definitions))
            occurrences = dict(inventory.occurrences)
            self.assertEqual(occurrences[(1, 1, 1, 1)], occurrences[(1, 1, 1, 3)])
            self.assertNotEqual(occurrences[(1, 1, 1, 1)], occurrences[(1, 1, 1, 2)])
            with self.assertRaises(FrozenInstanceError):
                inventory.step_bytes = 1
            products.append(product)
        self.assertEqual(products[0].payload, products[1].payload)

    def test_actual_reordered_copy_has_nonidentity_source_to_saved_face_order(self):
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.TopoDS import TopoDS_Compound, TopoDS_Iterator
        from OCP.gp import gp_Pnt

        builder = BRep_Builder()
        native = TopoDS_Compound(); builder.MakeCompound(native)
        builder.Add(native, BRepPrimAPI_MakeBox(2., 3., 4.).Shape())
        builder.Add(native, BRepPrimAPI_MakeBox(gp_Pnt(10., 0., 0.), 5., 6., 7.).Shape())
        document = Document("reordered source face traversal")
        with document.begin() as tx:
            handle = tx.evaluate(OperatorSpec("two boxes", "1", Mutation.READ_ONLY), (), (),
                                 lambda inputs, arena: NativeResult(native))
            tx.bind_root(GeometryLeaf("part", handle, appearance={"face_colors": ((0, RED), (6, BLUE))}),
                         unrepresented_metadata=())
            revision = tx.commit()
        def reorder(*args):
            copier = BRepBuilderAPI_Copy(*args)
            iterator = TopoDS_Iterator(copier.Shape()); children = []
            while iterator.More():
                children.append(iterator.Value()); iterator.Next()
            copied = TopoDS_Compound(); builder.MakeCompound(copied)
            for child in reversed(children):
                builder.Add(copied, child)
            class Copy:
                def Shape(self): return copied
                def ModifiedShape(self, shape): return copier.ModifiedShape(shape)
            return Copy()
        transferred = []
        original = step_product.transfer_face_entities
        def capture(*args, **kwargs):
            result = original(*args, **kwargs); transferred.extend(result); return result
        with patch("OCP.BRepBuilderAPI.BRepBuilderAPI_Copy", side_effect=reorder), \
             patch.object(step_product, "transfer_face_entities", side_effect=capture), \
             self.session(document, revision) as session:
            product = session.prepare("reordered.step")
        actual = product.saved_faces.definitions[0]
        permutation = tuple(actual.index(label) for label in transferred[0])
        self.assertEqual(tuple(range(6, 12)) + tuple(range(6)), permutation)
        self.assertEqual(RED, dict(product.returned_root.face_colors)[permutation[0]])
        self.assertEqual(BLUE, dict(product.returned_root.face_colors)[permutation[6]])

    def test_reader_resolves_actual_nonordinal_file_entity_labels(self):
        from cadgen.step_export import _STEP_STRING_OR_REF
        document, revision = self.fixture._styled_cut()
        with self.session(document, revision) as session:
            product = session.prepare("labels.step")
        def label(value): return value * 3 + 101
        def rename(match):
            return match.group(0) if match.group(1) is None else f"#{label(int(match.group(1)))}".encode()
        payload = _STEP_STRING_OR_REF.sub(rename, product.payload)
        path = self.directory / "renumbered.step"; path.write_bytes(payload)
        wanted = tuple(tuple(label(value) for value in row) for row in product.saved_faces.definitions)
        _, inventory = _read_saved_metadata(path, hashlib.sha256(payload).hexdigest(), transferred=wanted)
        self.assertEqual(wanted, inventory.definitions)
        self.assertEqual(len(payload), inventory.step_bytes)

    def test_same_palette_on_wrong_saved_faces_is_rejected(self):
        import cadgen.step_export as exporter
        document, revision = self.fixture._styled_cut()
        captured = []
        original_transfer = step_product.transfer_face_entities
        original_write = exporter.write_xcaf_doc_step_file
        corrupted = self.directory / "wrong-faces.step"
        def capture(*args, **kwargs):
            result = original_transfer(*args, **kwargs); captured.extend(result); return result
        def corrupt(doc, path, **kwargs):
            result = original_write(doc, path, **kwargs)
            one, two = captured[0][2], captured[0][6]
            swaps = {one: two, two: one}
            changed = 0
            def swap(match):
                nonlocal changed
                value = int(match.group(2))
                if value not in swaps: return match.group(0)
                changed += 1
                return match.group(1) + str(swaps[value]).encode() + match.group(3)
            payload = re.sub(rb"(\bSTYLED_ITEM\s*\([^;]*?,\s*#)(\d+)(\s*\);)", swap, path.read_bytes())
            self.assertEqual(2, changed)
            path.write_bytes(payload); corrupted.write_bytes(payload)
            return result
        with patch.object(step_product, "transfer_face_entities", side_effect=capture), \
             patch.object(exporter, "write_xcaf_doc_step_file", side_effect=corrupt), \
             self.session(document, revision) as session:
            with self.assertRaisesRegex(FaceTransferError, "exactly transferred face color"):
                session.prepare("wrong.step")
        roots, _ = _read_saved_metadata(corrupted, hashlib.sha256(corrupted.read_bytes()).hexdigest())
        self.assertEqual({RED, BLUE}, {color for _, color in roots[0].children[0].face_colors})

    def test_multiple_writer_results_fail_explicitly(self):
        from OCP.Transfer import Transfer_SimpleBinderOfTransient
        document, revision = self.fixture._styled_cut()
        with patch.object(Transfer_SimpleBinderOfTransient, "IsMultiple", return_value=True), \
             self.session(document, revision) as session:
            with self.assertRaisesRegex(FaceTransferError, "multiple results"):
                session.prepare("split.step")
        self.assertFalse(document._step_products.entries)

    def test_merged_reader_entities_fail_explicitly(self):
        from OCP.STEPConstruct import STEPConstruct
        document, revision = self.fixture._styled_cut()
        original = STEPConstruct.FindShape_s
        first = []
        def merged(*args):
            face = original(*args)
            if not first: first.append(face)
            return first[0]
        with patch.object(STEPConstruct, "FindShape_s", side_effect=merged), \
             self.session(document, revision) as session:
            with self.assertRaisesRegex(FaceTransferError, "merged distinct face entities"):
                session.prepare("merged.step")
        self.assertFalse(document._step_products.entries)

    def test_incomplete_or_multiple_reader_binders_fail_before_shape_lookup(self):
        from OCP.STEPConstruct import STEPConstruct
        from OCP.Transfer import Transfer_TransientProcess
        original = Transfer_TransientProcess.MapItem
        document, revision = self.fixture._styled_cut()
        for failure in ("missing", "undefined", "multiple", "chained"):
            with self.subTest(failure=failure):
                def altered(process, index):
                    binder = original(process, index)
                    if failure == "missing":
                        return None
                    class Binder:
                        def HasResult(self):
                            return failure != "undefined" and binder.HasResult()
                        def IsMultiple(self):
                            return failure == "multiple" or binder.IsMultiple()
                        def NextResult(self):
                            return binder if failure == "chained" else binder.NextResult()
                    return Binder()
                message = "singleton binder" if failure in ("missing", "undefined") else "multiple results"
                with patch.object(Transfer_TransientProcess, "MapItem", altered), \
                     patch.object(STEPConstruct, "FindShape_s", wraps=STEPConstruct.FindShape_s) as lookup, \
                     self.session(document, revision) as session:
                    with self.assertRaisesRegex(FaceTransferError, message):
                        session.prepare("ambiguous-reader.step")
                    lookup.assert_not_called()
                self.assertFalse(document._step_products.entries)
