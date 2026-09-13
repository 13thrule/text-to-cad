"""The retained scene must describe exactly the authored return value."""
from __future__ import annotations

import unittest

from cadgen import build123d as bd
from cadgen._document import Document
from cadgen._document.frontend import FrontendSession
from cadgen._document.native import copy_shape
from cadgen._document.returned import bind_returned_shape
from cadgen._document.roots import AssemblyGroup, GeometryLeaf, walk_root


def root_geometry(document, node):
    """Independent native reconstruction of the revision's scene tree."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Trsf

    if isinstance(node, GeometryLeaf):
        shape = copy_shape(document._get(node.geometry).shape)
    else:
        shape = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(shape)
        for child in node.children:
            builder.Add(shape, root_geometry(document, child))
    transform = gp_Trsf()
    transform.SetValues(*node.transform[:12])
    return shape.Moved(TopLoc_Location(transform))


class ReturnedTest(unittest.TestCase):
    def setUp(self):
        from cadgen._internal import op_memo
        installed = op_memo._installed
        if installed:
            op_memo.uninstall()
        self.addCleanup(op_memo.install if installed else lambda: None)

    def run_model(self, factory, document=None):
        document = document or Document("returned-model")
        with document.begin() as transaction:
            with FrontendSession(transaction) as frontend:
                result = factory()
                root = bind_returned_shape(frontend, result)
                result = frontend.materialize(result)
            revision = transaction.commit()
        self.assertIs(root, revision.root)
        native = bd.Compound.cast(root_geometry(document, root))
        self.assertTrue(native.is_valid)
        self.assertAlmostEqual(result.volume, native.volume, places=7)
        self.assertEqual(len(result.solids()), len(native.solids()))
        for expected, actual in zip(result.bounding_box().min, native.bounding_box().min):
            self.assertAlmostEqual(expected, actual, places=6)
        for expected, actual in zip(result.bounding_box().max, native.bounding_box().max):
            self.assertAlmostEqual(expected, actual, places=6)
        return document, transaction, root, result

    def test_direct_result_excludes_discarded_tools_and_groups(self):
        def model():
            bd.Compound(children=[bd.Pos(500, 0, 0) * bd.Box(2, 2, 2)], label="discarded")
            part = bd.Box(30, 20, 6) - bd.Cylinder(2, 10)
            part.label = "returned"
            return part

        _, _, root, _ = self.run_model(model)
        self.assertIsInstance(root, GeometryLeaf)
        self.assertEqual("returned", root.label)
        self.assertEqual(1, len(list(walk_root(root))))

    def test_metadata_not_yet_bound_is_reported_instead_of_silently_lost(self):
        def model():
            leaf = bd.Box(3, 4, 5)
            leaf.cad_material = {"roughness": .2}
            leaf.cad_face_ordinal_colors = {1: (1., 0., 0., 1.)}
            root = bd.Compound(children=[leaf])
            root._occurrence_tree = {"name": "authored-instance-hierarchy"}
            return root

        document, transaction, root, _ = self.run_model(model)
        self.assertEqual(("_occurrence_tree",),
                         document._revisions[transaction.revision_id].unrepresented_metadata)
        self.assertEqual({"roughness": .2}, root.children[0].appearance["pbr"])
        self.assertEqual(((0, (1., 0., 0., 1.)),), root.children[0].appearance["face_colors"])
        document, transaction, _, _ = self.run_model(lambda: bd.Box(3, 4, 5))
        self.assertEqual((), document._revisions[transaction.revision_id].unrepresented_metadata)

    def test_flat_placements_and_colors_retain_one_geometry_prototype(self):
        def model():
            source = bd.Box(3, 4, 5)
            children = []
            for x, color in ((0, "red"), (10, "blue"), (20, "green")):
                part = bd.Pos(x, 0, 0) * source
                part.label = "repeated label"
                part.color = bd.Color(color)
                children.append(part)
            return bd.Compound(children=children, label="assembly")

        _, _, root, _ = self.run_model(model)
        self.assertIsInstance(root, AssemblyGroup)
        self.assertEqual(3, len(root.children))
        self.assertEqual(1, len({child.geometry.prototype_id for child in root.children}))
        self.assertEqual([0, 10, 20], [child.transform[3] for child in root.children])
        self.assertNotEqual(root.children[0].appearance, root.children[1].appearance)

    def test_nested_opaque_group_placements_are_not_applied_twice(self):
        def model():
            groups = []
            for x in (0, 25):
                child = bd.Pos(2, 0, 0) * bd.Box(3, 4, 5)
                child.label = "leaf"
                group = bd.Compound(children=[child], label="group")
                groups.append(group.moved(bd.Pos(x, 9, 2) * bd.Rot(0, 0, 35)))
            return bd.Compound(children=groups, label="nested").moved(bd.Pos(7, 0, 0))

        _, _, root, _ = self.run_model(model)
        self.assertEqual(2, len(root.children))
        self.assertTrue(all(isinstance(child, AssemblyGroup) for child in root.children))
        self.assertEqual(2, sum(isinstance(node, GeometryLeaf) for _, node in walk_root(root)))

    def test_opaque_native_edit_binds_live_shape(self):
        def model():
            result = bd.Box(3, 4, 5)
            result.move(bd.Pos(12, 7, 2))
            return result

        _, _, root, _ = self.run_model(model)
        self.assertIsInstance(root, GeometryLeaf)

    def test_metadata_edit_reuses_geometry_and_keeps_previous_revision(self):
        color = ["red"]
        def model():
            result = bd.Box(3, 4, 5)
            result.color = bd.Color(color[0])
            return result

        document, _, first, _ = self.run_model(model)
        color[0] = "blue"
        _, transaction, second, _ = self.run_model(model, document)
        self.assertEqual(0, transaction.stats.computed)
        self.assertEqual(first.geometry.prototype_id, second.geometry.prototype_id)
        self.assertNotEqual(first.appearance, second.appearance)

    def test_located_queries_preserve_canonical_prototype_in_returned_root(self):
        offset = [4]
        def model():
            result = bd.Pos(offset[0], 7, 2) * bd.Box(3, 4, 5)
            self.assertAlmostEqual(60, result.volume)
            self.assertTrue(result.is_valid)
            self.assertAlmostEqual(offset[0] - 1.5, result.bounding_box().min.X)
            return result

        document, _, first, _ = self.run_model(model)
        offset[0] = 14
        _, _, second, _ = self.run_model(model, document)
        self.assertEqual(first.geometry.prototype_id, second.geometry.prototype_id)
        self.assertEqual(4, first.transform[3])
        self.assertEqual(14, second.transform[3])


if __name__ == "__main__":
    unittest.main()
