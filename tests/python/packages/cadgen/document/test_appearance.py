"""Closed source appearance and independently imported native STEP styles."""
from __future__ import annotations

import json
import math
from pathlib import Path
import unittest

from cadgen._document.appearance import (appearance, authored_face_recipe, inherited,
    native_faces, physical_material, to_value)

RED = (1., 0., 0., 1.)
BLUE = (0., 0., 1., 1.)
GREEN = (0., 1., 0., 1.)
STEEL = {"name": "steel", "description": "fixture", "density": 7.8,
         "density_name": "density", "density_type": ""}


class AppearanceValueTests(unittest.TestCase):
    def test_frozen_closed_values_and_fieldwise_inheritance(self):
        raw = {"color": [1, 0, 0], "pbr": {"roughness": .2}, "physical_material": dict(STEEL)}
        first = appearance(raw)
        raw["color"][0] = 0; raw["pbr"]["roughness"] = .9; raw["physical_material"]["name"] = "changed"
        self.assertEqual(RED, first["color"])
        merged = inherited(first, {"pbr": {"metalness": .8}, "material": "brushed"})
        self.assertEqual({"roughness": .2, "metalness": .8}, merged["pbr"])
        self.assertEqual("steel", merged["physical_material"]["name"])
        with self.assertRaises(TypeError):
            merged["pbr"]["roughness"] = 1
        payload = to_value(merged)
        payload["pbr"]["roughness"] = 1
        self.assertEqual(.2, merged["pbr"]["roughness"])
        self.assertNotIn("face_colors", inherited({"face_colors": ((0, RED),)}, {}))

    def test_source_ordinals_use_explicit_copy_bijection(self):
        self.assertEqual(((1, RED), (2, BLUE)), authored_face_recipe(
            {1: RED, 2: BLUE}, face_count=3, correspondence=(1, 2, 0)))
        for value in ({0: RED}, {4: RED}, {True: RED}, {"1": RED}):
            with self.assertRaises(ValueError):
                authored_face_recipe(value, face_count=3)
        with self.assertRaises(ValueError):
            authored_face_recipe({1: RED}, face_count=3, correspondence=(0, 0, 2))

    def test_invalid_values_do_not_clamp_drop_or_coerce(self):
        for value in ({"color": [2, 0, 0]}, {"color": [math.nan, 0, 0]},
                      {"pbr": {"roughness": True}}, {"pbr": {"texture": "file"}},
                      {"pbr": {"opacity": -.1}}, {"material": object()},
                      {"face_colors": ((0, RED), (0, BLUE))},
                      {"face_colors": ((6, RED),)}, {"unrecognized": 1}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                appearance(value, face_count=6)
        with self.assertRaises(ValueError):
            appearance({"face_colors": ()}, allow_faces=False)
        with self.assertRaises(ValueError):
            physical_material({**STEEL, "density": math.inf})
        with self.assertRaises(ValueError):
            physical_material({**STEEL, "name": "x" * 4097})


def face_facts(native):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    faces = native_faces(native)
    rows = []
    for index in range(1, faces.Extent() + 1):
        properties = GProp_GProps()
        BRepGProp.SurfaceProperties_s(faces.FindKey(index), properties)
        center = properties.CentreOfMass()
        rows.append((index - 1, properties.Mass(), (center.X(), center.Y(), center.Z())))
    return tuple(rows)


class AppearanceNativeTests(unittest.TestCase):
    def setUp(self):
        from tests.python.support.tmp_root import generated_cad_directory
        temporary = generated_cad_directory(prefix="document-appearance-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()

    def test_source_24_style_edits_keep_geometry_and_mesh_bytes(self):
        from cadgen import build123d as bd
        from cadgen._document import Document
        from cadgen._document.display import build_display
        from cadgen._document.frontend import FrontendSession
        from cadgen._document.returned import bind_returned_shape
        document = Document("appearance24")
        products, roots = [], []
        for turn in range(2):
            with document.begin() as tx:
                with FrontendSession(tx) as frontend:
                    prototype = bd.Box(2, 3, 4)
                    children = []
                    for index in range(24):
                        child = bd.Pos(index * 4, 0, 0) * prototype
                        child.cad_material = {"metalness": .3 + .2 * turn}
                        child.material = "steel"
                        children.append(child)
                    root = bd.Compound(children=children)
                    root.cad_material = {"roughness": .2, "opacity": .8}
                    bind_returned_shape(frontend, root)
                revision = tx.commit()
            roots.append(revision.root)
            if turn:
                self.assertEqual(0, tx.stats.computed)
            product = build_display(document, revision.revision_id, previous=products[-1] if products else None)
            manifest = json.loads(product.manifest)
            self.assertEqual(24, len(manifest["occurrences"]))
            self.assertEqual(1, len(product.assets))
            self.assertEqual({"roughness": .2, "opacity": .8, "metalness": .3 + .2 * turn},
                             manifest["occurrences"][0]["appearance"]["pbr"])
            self.assertEqual("steel", manifest["occurrences"][0]["appearance"]["material"])
            products.append(product)
        self.assertIs(next(iter(products[0].assets.values())), next(iter(products[1].assets.values())))
        self.assertEqual(roots[0].children[0].geometry.prototype_id, roots[1].children[0].geometry.prototype_id)
        self.assertEqual(.3, roots[0].children[0].appearance["pbr"]["metalness"])

    def _styled_cut(self):
        from cadgen._document import Document, Mutation, NativeResult, OperatorSpec
        from cadgen._document.roots import AssemblyGroup, GeometryLeaf, IDENTITY_TRANSFORM
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
        document = Document("styled-cut")
        def compute(inputs, arena):
            box = BRepPrimAPI_MakeBox(16., 8., 2.).Shape()
            hole = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(5., 4., -1.), gp_Dir(0., 0., 1.)), 1., 4.).Shape()
            return NativeResult(BRepAlgoAPI_Cut(box, hole).Shape())
        with document.begin() as tx:
            handle = tx.evaluate(OperatorSpec("appearance-cut", "1", Mutation.READ_ONLY), (), (), compute)
            facts = tx.query(handle, face_facts)
            top = next(index for index, area, center in facts if abs(center[2] - 2) < 1e-8 and area > 100)
            bore = next(index for index, area, center in facts if abs(area - 4 * math.pi) < 1e-8)
            moved = list(IDENTITY_TRANSFORM); moved[3] = 25.
            tx.bind_root(AssemblyGroup("root", (
                GeometryLeaf("red", handle, label="red", appearance={"face_colors": ((top, RED), (bore, BLUE)), "physical_material": STEEL}),
                GeometryLeaf("green", handle, transform=tuple(moved), label="green", appearance={"face_colors": ((top, GREEN), (bore, BLUE))}),
            )), unrepresented_metadata=())
            revision = tx.commit()
        return document, revision

    def test_native_step_styles_material_and_independent_import_use_actual_faces(self):
        from cadgen._document import Document
        from cadgen._document.step_product import StepProductSession
        from cadgen._document.step_import import StepImportSession
        from cadgen._document.sources import CapturedInput
        from cadgen._document.roots import GeometryLeaf, walk_root
        source, revision = self._styled_cut()
        original = {key: face_facts(value.shape) for key, value in source._prototypes.items()}
        with StepProductSession(source, revision.revision_id, work_directory=self.directory) as session:
            product = session.prepare("styled.step")
            self.assertEqual(1, session.metrics.prototype_copies)
            self.assertEqual(1, session.metrics.appearance_copies)
            self.assertEqual(STEEL, product.returned_root.children[0].physical_material)
        path = self.directory / "styled.step"; path.write_bytes(product.payload)
        imported = Document("actual-saved-bytes")
        result = StepImportSession(imported, work_directory=self.directory).load(CapturedInput.read(path))
        leaves = [node for _, node in walk_root(result.root) if type(node) is GeometryLeaf]
        self.assertEqual(2, len(leaves))
        for node, top_color in zip(leaves, (RED, GREEN)):
            recipe = dict(node.appearance["face_colors"])
            facts = face_facts(imported._get(node.geometry).shape)
            top = next(index for index, area, center in facts if abs(center[2] - 2) < 1e-8 and area > 100)
            bore = next(index for index, area, center in facts if abs(area - 4 * math.pi) < 1e-8)
            self.assertEqual(top_color, recipe[top])
            self.assertEqual(BLUE, recipe[bore])
        self.assertEqual(STEEL, leaves[0].appearance["physical_material"])
        self.assertNotIn("physical_material", leaves[1].appearance)
        self.assertEqual(original, {key: face_facts(value.shape) for key, value in source._prototypes.items()})

    def test_checkpoint_preserves_exact_recipe_and_material_values(self):
        from cadgen._document.checkpoint import CheckpointCodec, checkpoint_engine_version
        from cadgen._document.storage import Catalog
        document, revision = self._styled_cut()
        with Catalog(self.directory / "catalog", engine_version=checkpoint_engine_version()) as catalog:
            codec = CheckpointCodec(catalog)
            checkpoint = codec.stage(document, revision.revision_id)
            self.assertTrue(codec.commit(checkpoint, expected_head=None))
            restored = codec.recover(document.document_id).document
            self.assertEqual(revision.root.children[0].appearance, restored.head.root.children[0].appearance)

    def test_native_step_rejects_material_field_lost_by_translation(self):
        from dataclasses import replace
        from cadgen._document.step_product import StepProductSession, UnsupportedStepProduct
        document, revision = self._styled_cut()
        first = revision.root.children[0]
        changed = replace(first, appearance={**first.appearance,
                          "physical_material": {**STEEL, "density_type": "g/cm3"}})
        with document.begin() as tx:
            tx.bind_root(replace(revision.root, children=(changed, revision.root.children[1])),
                         unrepresented_metadata=())
            revision = tx.commit()
        with StepProductSession(document, revision.revision_id, work_directory=self.directory) as session:
            with self.assertRaisesRegex(UnsupportedStepProduct, "physical material"):
                session.prepare("lost-density-type.step")

    def test_native_occurrence_and_face_alpha_are_independent_saved_facts(self):
        from dataclasses import replace
        from cadgen._document.step_product import StepProductSession
        document, revision = self._styled_cut()
        first = revision.root.children[0]
        face = first.appearance["face_colors"][0][0]
        color, face_color = (.2, .4, .6, .5), (1., 0., 0., .3)
        with document.begin() as tx:
            tx.bind_root(replace(revision.root, children=(replace(first, appearance={
                "color": color, "face_colors": ((face, face_color),)}),)), unrepresented_metadata=())
            revision = tx.commit()
        with StepProductSession(document, revision.revision_id, work_directory=self.directory) as session:
            actual = session.prepare("alpha.step").returned_root.children[0]
        for expected, saved in zip(color, actual.color):
            self.assertAlmostEqual(expected, saved, places=6)
        self.assertEqual(1, len(actual.face_colors))
        for expected, saved in zip(face_color, actual.face_colors[0][1]):
            self.assertAlmostEqual(expected, saved, places=6)
