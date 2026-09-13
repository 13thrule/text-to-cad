"""Resident revision display products, with no exchange file or old store."""
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from cadgen._document import Document, GeometryLeaf, AssemblyGroup, IDENTITY_TRANSFORM
from cadgen._document.core import OperatorSpec
from cadgen._document.display import build_display
from cadgen._document.native import NativeResult


def moved(x):
    matrix = list(IDENTITY_TRANSFORM)
    matrix[3] = x
    return tuple(matrix)


def revision(document, shift=0, appearance=None):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    with document.begin() as tx:
        box = tx.evaluate(OperatorSpec("display-box"), (), (), lambda *_: NativeResult(BRepPrimAPI_MakeBox(2., 3., 4.).Shape()))
        cylinder = tx.evaluate(OperatorSpec("display-cylinder"), (), (), lambda *_: NativeResult(BRepPrimAPI_MakeCylinder(1., 4.).Shape()))
        children = tuple(GeometryLeaf(str(i), box if i % 2 else cylinder, moved(i * 5),
                                      appearance={"color": (0., 0., 1., .5)} if i == 0 else {}) for i in range(24))
        group = AssemblyGroup("nested", children, moved(10), appearance={"pbr": {"roughness": .25}})
        tx.bind_root(AssemblyGroup("root", (group,), moved(shift),
                                   appearance=appearance if appearance is not None else {"color": (1., 0., 0.)}),
                     unrepresented_metadata=())
        return tx.commit().revision_id


class DisplayTests(unittest.TestCase):
    def test_nested_24_occurrences_share_two_assets_and_inherit_appearance(self):
        document = Document("display")
        product = build_display(document, revision(document, 20))
        manifest = json.loads(product.manifest)
        self.assertEqual(2, len(product.assets))
        self.assertEqual(26, len(manifest["nodes"]))
        self.assertEqual(24, len(manifest["occurrences"]))
        first, second = manifest["occurrences"][:2]
        self.assertEqual(["root", "nested", "0"], first["path"])
        self.assertEqual(30, first["transform"][3])
        self.assertEqual(35, second["transform"][3])
        self.assertEqual({"color": [0., 0., 1., .5], "pbr": {"roughness": .25}}, first["appearance"])
        self.assertEqual([1., 0., 0.], second["appearance"]["color"])
        for row in manifest["prototypes"].values():
            self.assertEqual({"mesh", "bytes"}, set(row))
            self.assertEqual(len(product.assets[row["mesh"]].payload), row["bytes"])
        with self.assertRaises(TypeError):
            product.assets["forged"] = None

    def test_placement_revision_reuses_exact_validated_bytes_without_hashing(self):
        document = Document("reuse")
        first = build_display(document, revision(document))
        with patch("cadgen._document.display.unpack_mesh", side_effect=AssertionError("revalidated")), \
             patch("cadgen._document.display.hashlib.sha256", side_effect=AssertionError("rehashed")):
            second = build_display(document, revision(document, 5), previous=first)
        self.assertNotEqual(first.manifest, second.manifest)
        self.assertEqual(first.assets.keys(), second.assets.keys())
        self.assertTrue(all(first.assets[key] is value for key, value in second.assets.items()))

    def test_constructed_previous_is_not_validation_provenance(self):
        document = Document("provenance")
        first = build_display(document, revision(document))
        # Even an otherwise exact copied dataclass is not trusted provenance.
        copied = replace(first)
        from cadgen._document.display import unpack_mesh
        with patch("cadgen._document.display.unpack_mesh", wraps=unpack_mesh) as validate:
            build_display(document, first.revision_id, previous=copied)
        self.assertEqual(2, validate.call_count)

    def test_unknown_or_invalid_appearance_fails_before_native_meshing(self):
        for appearance in ({"material": "steel"}, {"pbr": {"texture": "image"}},
                           {"color": [1, 0]}, {"color": [2, 0, 0]}, {"pbr": {"opacity": True}}):
            document = Document("invalid-appearance")
            rid = revision(document, appearance=appearance)
            with patch("cadgen._document.display.mesh_for_occurrence", side_effect=AssertionError("meshed invalid metadata")):
                with self.assertRaises(ValueError):
                    build_display(document, rid)

    def test_failure_preserves_previous_and_asset_limit_precedes_validation(self):
        document = Document("limits")
        first = build_display(document, revision(document))
        with patch("cadgen._document.display.MAX_ASSET_BYTES", 1), \
             patch("cadgen._document.display.unpack_mesh", side_effect=AssertionError("validated before limit")):
            with self.assertRaisesRegex(ValueError, "scene limit"):
                build_display(document, revision(document, 2))
        self.assertEqual(24, len(json.loads(first.manifest)["occurrences"]))
        with patch("cadgen._document.display.unpack_mesh", side_effect=AssertionError("lost previous")):
            build_display(document, first.revision_id, previous=first)

    def test_build123d_flat_source_reuses_box_and_cylinder_assets(self):
        from cadgen import build123d as bd
        from cadgen._document.frontend import FrontendSession
        from cadgen._document.returned import bind_returned_shape

        document = Document("source-display")
        previous = None
        for shift in (0, 5):
            with document.begin() as tx:
                with FrontendSession(tx) as frontend:
                    box, cylinder = bd.Box(2, 3, 4), bd.Cylinder(1, 4)
                    children = [bd.Pos(i * 5 + shift + 10, 0, 0) * (box if i % 2 else cylinder) for i in range(24)]
                    result = bd.Compound(children=children, label="root")
                    result.color = bd.Color(1., 0., 0.)
                    bind_returned_shape(frontend, result)
                committed = tx.commit()
            product = build_display(document, committed.revision_id, previous=previous)
            manifest = json.loads(product.manifest)
            self.assertEqual(2, len(product.assets))
            self.assertEqual(25, len(manifest["nodes"]))
            self.assertEqual(24, len(manifest["occurrences"]))
            self.assertEqual(shift + 10, manifest["occurrences"][0]["transform"][3])
            self.assertEqual([1., 0., 0., 1.], manifest["occurrences"][0]["appearance"]["color"])
            if previous:
                self.assertEqual(0, tx.stats.computed)
                self.assertTrue(all(previous.assets[key] is asset for key, asset in product.assets.items()))
            previous = product
