"""Native polygon/face aliases precede the bounded sketch frontend adapter."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from cadgen import build123d as bd
from cadgen._document import Document
from cadgen._document.sketch_effects import PolygonKernel, SketchNativeEffects
from cadgen._document.native import topology_map
from cadgen._document.frontend import FrontendSession


POINTS = ((0., 0.), (8., 0.), (8., 6.), (5., 6.), (5., 4.), (0., 4.))


class SketchEffectsTests(unittest.TestCase):
    def setUp(self):
        from cadgen._internal import op_memo
        installed = op_memo._installed
        if installed:
            op_memo.uninstall()
        self.addCleanup(op_memo.install if installed else lambda: None)

    def test_projecting_last_outputs_scans_the_carrier_once_and_escape_stays_private(self):
        from cadgen._document import builder_effects as effects_module
        from cadgen._document.builder_effects import WrapperRef
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Pnt

        effects = SketchNativeEffects()
        document = Document("projected-slot-views")
        with document.begin() as tx:
            seed = effects.kernel.own(tx, effects.kernel.evaluate(tx, POINTS))
            bundle = effects.first(tx, seed)
            native = document._get(bundle.handle).shape
            expected = effects_module._slots(native)
            refs = tuple(WrapperRef("created", index) for index in range(len(bundle.layout.created)))
            self.assertGreater(len(refs), 10)
            with patch.object(effects_module, "_slots", wraps=effects_module._slots) as scan:
                handles = [effects.stock.project(tx, bundle, ref) for ref in refs]
                self.assertEqual(1, scan.call_count)
            for ref, handle in zip(refs, handles):
                self.assertTrue(document._get(handle).shape.IsSame(
                    expected[bundle.layout.created[ref.index].native_slot]))
            vertex_index = next(index for index, record in enumerate(bundle.layout.created)
                                if record.kind == "Vertex")
            vertex_handle = handles[vertex_index]
            before = BRep_Tool.Pnt_s(TopoDS.Vertex(document._get(vertex_handle).shape)).X()
            private = TopoDS.Vertex(tx.escape_arena.native(vertex_handle))
            BRep_Builder().UpdateVertex(private, gp_Pnt(99., 31., 17.), .01)
            projected = effects.stock.project(tx, bundle, refs[vertex_index])
            self.assertEqual(99., BRep_Tool.Pnt_s(TopoDS.Vertex(document._get(projected).shape)).X())
            self.assertEqual(before, BRep_Tool.Pnt_s(TopoDS.Vertex(document._get(vertex_handle).shape)).X())
            self.assertIsNone(effects.stock._projection_carrier)
            tx.commit()

    def test_polygon_wire_and_face_match_stock_and_reuse_without_native_rebuild(self):
        kernel = PolygonKernel()
        expected_wire = bd.Wire.make_polygon(POINTS)
        expected_face = bd.Face(expected_wire)
        document = Document("polygon-native")
        for turn in range(2):
            with document.begin() as tx:
                seed = kernel.evaluate(tx, POINTS)
                native = kernel.instantiate(tx, seed)
                wire, face = bd.Wire(bd.Wire.cast(native.wire).wrapped), bd.Face(bd.Face.cast(native.face).wrapped)
                self.assertAlmostEqual(expected_wire.length, wire.length)
                self.assertAlmostEqual(expected_face.area, face.area)
                self.assertEqual(len(expected_face.edges()), len(face.edges()))
                self.assertTrue(face.is_valid)
                self.assertTrue(topology_map(native.face).Contains(native.wire))
                if turn:
                    self.assertEqual(0, tx.stats.computed)
                    self.assertEqual(1, tx.stats.reused)
                tx.commit()

    def test_owned_family_and_projection_preserve_wire_face_aliases_on_escape(self):
        kernel = PolygonKernel()
        document = Document("polygon-family")
        for turn in range(2):
            with document.begin() as tx:
                seed = kernel.own(tx, kernel.evaluate(tx, POINTS))
                wire_handle = kernel.project(tx, seed, 0)
                face_handle = kernel.project(tx, seed, 1)
                native_wire = tx.escape_arena.native(wire_handle)
                copied = tx.escape_arena.copy_batches
                native_face = tx.escape_arena.native(face_handle)
                self.assertTrue(topology_map(native_face).Contains(native_wire))
                self.assertEqual(copied, tx.escape_arena.copy_batches)
                if turn:
                    self.assertEqual(0, tx.stats.computed)
                tx.commit()

    def test_native_mutation_does_not_change_the_retained_polygon(self):
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.gp import gp_Pnt
        kernel = PolygonKernel()
        document = Document("polygon-isolation")
        with document.begin() as tx:
            seed = kernel.evaluate(tx, POINTS)
            native = kernel.instantiate(tx, seed)
            wire = bd.Wire(bd.Wire.cast(native.wire).wrapped)
            face = bd.Face(bd.Face.cast(native.face).wrapped)
            vertex = wire.vertices()[0].wrapped
            BRep_Builder().UpdateVertex(vertex, gp_Pnt(40., 30., 20.), .01)
            self.assertTrue(any(BRep_Tool.Pnt_s(v.wrapped).X() == 40. for v in face.vertices()))
            clean = kernel.instantiate(tx, seed)
            clean_face = bd.Face(bd.Face.cast(clean.face).wrapped)
            self.assertAlmostEqual(38., clean_face.area)
            self.assertFalse(any(v.X == 40. for v in clean_face.vertices()))
            tx.commit()

    def test_first_sketch_preserves_complete_last_and_constructor_parent_roles(self):
        def observations(builder):
            result = builder._obj
            tool = builder.to_combine[0]
            parent = tool.topo_parent
            return (round(result.area, 8), len(result.faces()), len(result.edges()),
                    tuple(len(builder.lasts[kind]) for kind in (bd.Vertex, bd.Edge, bd.Face, bd.Solid)),
                    builder.lasts[bd.Face][0] is tool,
                    all(edge.topo_parent is parent for edge in builder.lasts[bd.Edge]),
                    all(vertex.topo_parent is parent for vertex in builder.lasts[bd.Vertex]),
                    parent is not tool, round(parent.area, 8),
                    sum(a.wrapped.IsSame(b.wrapped) for a in parent.edges() for b in tool.edges()))
        with bd.BuildSketch() as baseline:
            bd.Polygon(POINTS, align=None)
            expected = observations(baseline)
        document = Document("sketch-first-effects")
        effects = SketchNativeEffects()
        for turn in range(2):
            with document.begin() as tx:
                seed = effects.kernel.own(tx, effects.kernel.evaluate(tx, POINTS))
                bundle = effects.first(tx, seed)
                view = effects.stock.materialize(tx, bundle)
                actual = object.__new__(bd.BuildSketch)
                actual._obj = view.result
                actual.to_combine = list(view.to_combine)
                actual.lasts = {kind: bd.ShapeList(row) for kind, row in
                                zip((bd.Vertex, bd.Edge, bd.Face, bd.Solid), view.lasts)}
                self.assertEqual(expected, observations(actual))
                if turn:
                    self.assertEqual(0, tx.stats.computed)
                tx.commit()

    def test_stock_polygon_body_and_frontend_effects_keep_source_wrapper_roles(self):
        def build():
            with bd.BuildSketch() as sketch:
                polygon = bd.Polygon(POINTS, align=None)
            return sketch, polygon
        expected, polygon = build()
        document = Document("source-polygon")
        for turn in range(2):
            with document.begin() as tx:
                with FrontendSession(tx) as frontend:
                    sketch, polygon = build()
                    self.assertEqual(1, frontend._fallback_counts.get("sketch-effects-retained"))
                    before = tx.stats.computed
                    self.assertEqual(list(POINTS), polygon.pts)
                    self.assertEqual(None, polygon.align)
                    self.assertAlmostEqual(expected._obj.area, sketch._obj.area)
                    self.assertAlmostEqual(expected._obj.area, polygon.area)
                    self.assertTrue(all(edge.topo_parent is sketch.to_combine[0].topo_parent
                                        for edge in sketch.lasts[bd.Edge]))
                    self.assertIs(sketch.to_combine[0], sketch.lasts[bd.Face][0])
                    if turn:
                        self.assertEqual(0, before)
                tx.commit()

    def test_sketch_exit_keeps_pending_list_and_plane_identities_with_and_without_part(self):
        def build(prior):
            with bd.BuildPart() as part:
                if prior:
                    bd.Box(10, 10, 2)
                old = part._part
                pending, planes = part.pending_faces, part.pending_face_planes
                plane = bd.Plane.XY.offset(3)
                with bd.BuildSketch(plane) as sketch:
                    bd.Polygon(POINTS, align=None)
                result = (part, sketch, old, pending, planes, sketch.exit_workplanes[0])
            return result
        for prior in (False, True):
            expected = build(prior)
            document = Document(f"pending-sketch-{prior}")
            for turn in range(2):
                with document.begin() as tx:
                    with FrontendSession(tx) as frontend:
                        part, sketch, old, pending, planes, plane = build(prior)
                        self.assertEqual(1, frontend._fallback_counts.get("sketch-pending-retained"))
                        computed = tx.stats.computed
                        self.assertIs(part.obj_before, old)
                        self.assertIs(part.to_combine[0], sketch._obj)
                        self.assertIs(part.pending_faces, pending)
                        self.assertIs(part.pending_face_planes, planes)
                        self.assertIs(planes[0], plane)
                        self.assertEqual(1, len(pending))
                        self.assertAlmostEqual(expected[0].pending_faces[0].area, pending[0].area)
                        self.assertAlmostEqual(3, pending[0].center().Z)
                        self.assertEqual(tuple(len(part.lasts[k]) for k in (bd.Vertex, bd.Edge, bd.Face, bd.Solid)),
                                         tuple(len(expected[0].lasts[k]) for k in (bd.Vertex, bd.Edge, bd.Face, bd.Solid)))
                        if prior:
                            self.assertIsNot(part._part, old)
                            self.assertTrue(part._part.wrapped.IsSame(old.wrapped))
                        else:
                            self.assertIsNone(part._part)
                        if turn:
                            self.assertEqual(0, computed)
                    tx.commit()

    def test_prism_base_aliases_and_native_input_records_match_stock_without_mutating_prototype(self):
        from cadgen._document.builder_effects import _slots
        def native_records(face):
            return tuple((e.wrapped.TShape().Curves().Size(), e.wrapped.TShape().Tolerance(),
                          e.wrapped.TShape().Modified()) for e in face.edges())
        def observations(face, solid):
            return (round(solid.volume, 7), len(solid.faces()), len(solid.edges()),
                    sum(part.wrapped.IsSame(face.wrapped) for part in solid.faces()),
                    sum(a.wrapped.IsSame(b.wrapped) for a in face.edges() for b in solid.edges()))
        effects = SketchNativeEffects()
        document = Document("polygon-prism")
        for clean in (False, True):
            for amount in (3., 5., 3.):
                face = bd.Face(bd.Wire.make_polygon(POINTS))
                expected_solid = bd.Solid.extrude(face, (0, 0, amount))
                if clean:
                    expected_solid.clean()
                expected = observations(face, expected_solid)
                with document.begin() as tx:
                    seed = effects.kernel.own(tx, effects.kernel.evaluate(tx, POINTS))
                    handle = effects.kernel.project(tx, seed, 1)
                    prototype_face = bd.Face(bd.Face.cast(tx.document._get(handle).shape).wrapped)
                    before = native_records(prototype_face)
                    product = effects.extrude(tx, handle, (0., 0., amount), clean=clean)
                    self.assertEqual(before, native_records(prototype_face))
                    slots = _slots(tx.escape_arena.native(product.handle))
                    actual_face = bd.Face(bd.Face.cast(slots[0]).wrapped)
                    solid = bd.Solid(bd.Solid.cast(slots[2]).wrapped)
                    self.assertEqual(expected, observations(actual_face, solid))
                    tx.commit()

    def test_complete_polygon_pending_extrude_warm_geometry_and_tool_aliases(self):
        def build(prior, amount, clean):
            with bd.BuildPart() as part:
                if prior:
                    bd.Box(20, 20, 2)
                with bd.BuildSketch(bd.Plane.XY.offset(1)) as sketch:
                    polygon = bd.Polygon(POINTS, align=None)
                pending, planes = part.pending_faces, part.pending_face_planes
                base = pending[0]
                extruded = bd.extrude(amount=amount, clean=clean)
            return part, sketch, polygon, pending, planes, base, extruded
        def observed(values):
            part, sketch, polygon, pending, planes, face, extruded = values
            return (round(part.part.volume, 7), len(part.part.faces()), len(part.part.edges()),
                    round(extruded.volume, 7), len(extruded.solids()),
                    tuple(len(part.lasts[k]) for k in (bd.Vertex, bd.Edge, bd.Face, bd.Solid)),
                    part.to_combine[0] is part.lasts[bd.Solid][0],
                    part.pending_faces is not pending, part.pending_face_planes is not planes,
                    len(pending), len(planes),
                    sum(f.wrapped.IsSame(face.wrapped) for f in extruded.faces()))
        for prior in (False, True):
            for clean in (False, True):
                document = Document(f"polygon-extrude-{prior}-{clean}")
                for turn, amount in enumerate((3., 3., 5., 3.)):
                    expected = observed(build(prior, amount, clean))
                    with document.begin() as tx:
                        with FrontendSession(tx) as frontend:
                            built = build(prior, amount, clean)
                            self.assertEqual(1, frontend._fallback_counts.get("sketch-extrusion-retained"))
                            computed = tx.stats.computed
                            self.assertEqual(expected, observed(built))
                            if turn in (1, 3):
                                self.assertEqual(0, computed)
                        tx.commit()

    def test_provider_callbacks_execute_normally_once_on_cold_and_warm_requests(self):
        import inspect
        from build123d.topology import two_d
        calls, active = [], []
        def build():
            with bd.BuildPart() as part:
                with bd.BuildSketch():
                    bd.Polygon(POINTS, align=None)
                bd.extrude(amount=3.)
            return part.part
        providers = ((bd.Wire, "make_polygon"), (two_d, "_make_topods_face_from_wires"),
                     (bd.Plane, "_to_from_local_coords"), (bd.Solid, "extrude"),
                     (bd.Shape, "clean"), (bd.ShapeList, "__init__"),
                     (bd.WorkplaneList, "_get_context"), (bd.Plane, "reverse_transform"))
        for owner, name in providers:
            descriptor = inspect.getattr_static(owner, name)
            function = (descriptor.__func__ if isinstance(descriptor, classmethod)
                        else descriptor.fget if isinstance(descriptor, property) else descriptor)
            def callback(*args, _original=function, **kwargs):
                calls.append(name)
                if active:
                    self.assertEqual(0, active[0]._compute_depth)
                return _original(*args, **kwargs)
            replacement = (classmethod(callback) if isinstance(descriptor, classmethod)
                           else property(callback) if isinstance(descriptor, property) else callback)
            with self.subTest(provider=name), patch.object(owner, name, replacement):
                calls.clear()
                expected = build()
                expected_count = len(calls)
                expected_volume = expected.volume
                document = Document("sketch-callback-" + name)
                for _ in range(2):
                    with document.begin() as tx:
                        with FrontendSession(tx) as frontend:
                            calls.clear()
                            active[:] = [frontend]
                            actual = build()
                            active.clear()
                            self.assertEqual(expected_count, len(calls))
                            self.assertAlmostEqual(expected_volume, actual.volume)
                            self.assertEqual(0, frontend._fallback_counts.get("sketch-extrusion-retained", 0))
                        tx.commit()

    def test_extrude_failure_consumes_pending_lists_and_caught_source_continues(self):
        def build(amount):
            with bd.BuildPart() as part:
                with bd.BuildSketch():
                    bd.Polygon(POINTS, align=None)
                old_faces, old_planes = part.pending_faces, part.pending_face_planes
                try:
                    bd.extrude(amount=amount)
                except (ValueError, OverflowError, TypeError) as error:
                    failed = type(error)
                else:
                    self.fail("expected a failing extrusion")
                effects = (failed, len(old_faces), len(old_planes), part.pending_faces is not old_faces,
                           part.pending_face_planes is not old_planes, len(part.pending_faces), len(part.pending_face_planes))
                bd.Box(2, 3, 4)
            return effects, part.part.volume
        for amount in (None, 10 ** 400):
            expected = build(amount)
            document = Document("sketch-failure")
            for _ in range(2):
                with document.begin() as tx:
                    with FrontendSession(tx):
                        self.assertEqual(expected, build(amount))
                    tx.commit()

    def test_checkpoint_restart_reuses_sketch_pending_and_prism_auxiliary_results(self):
        from cadgen._document.checkpoint import CheckpointCodec, checkpoint_engine_version
        from cadgen._document.service import DocumentService
        from cadgen._document.storage import Catalog
        from tests.python.support.tmp_root import generated_cad_directory
        source = '''from pathlib import Path
from cadgen import step, build123d as bd
@step
def model():
    counter = Path(__file__).with_suffix('.runs')
    counter.write_text((counter.read_text() if counter.exists() else '') + 'run\\n')
    with bd.BuildPart() as part:
        with bd.BuildSketch(bd.Plane.XY.offset(2)):
            bd.Polygon(((0,0),(8,0),(8,6),(5,6),(5,4),(0,4)), align=None)
        pending, planes = part.pending_faces, part.pending_face_planes
        result = bd.extrude(amount=3)
        assert part.pending_faces is not pending and len(pending) == 1
        assert part.pending_face_planes is not planes and len(planes) == 1
        assert part.lasts[bd.Solid][0] is part.to_combine[0]
    return part.part
'''
        with generated_cad_directory(prefix="document-sketch-restart-") as directory:
            root = Path(directory).resolve()
            source_path = root / "sketch.py"
            source_path.write_text(source)
            catalog = Catalog(root / "catalog", engine_version=checkpoint_engine_version())
            self.addCleanup(catalog.close)
            codec = CheckpointCodec(catalog, runtime={"sketch-effects-test": 1})
            first = DocumentService(checkpoint_codec=codec)
            built = first.generate(source_path)
            self.assertTrue(first.checkpoint(built.document).published)
            second = DocumentService(checkpoint_codec=codec)
            with patch("cadgen._internal.generation._generate_step_outputs", side_effect=AssertionError("old pipeline")):
                second.generate(source_path)
            self.assertEqual(["recovered"], list(second.recovery.values()))
            self.assertEqual(0, second.last_attempt.stats.computed)
            self.assertEqual(1, second.last_attempt.fallback_counts.get("sketch-extrusion-retained"))
            self.assertAlmostEqual(114., bd.import_step(source_path.with_suffix(".step")).volume)
            self.assertEqual("run\nrun\n", source_path.with_suffix(".runs").read_text())

    def test_closed_auxiliary_schemas_reject_wrong_roles_versions_and_native_slot_kinds(self):
        from cadgen._document.sketch_effects import _polygon_slots, _extrusion_slots, _decode_pending
        from cadgen._document.builder_effects import _pack, _slots
        effects = SketchNativeEffects()
        document = Document("sketch-auxiliary-validation")
        with document.begin() as tx:
            seed = effects.kernel.own(tx, effects.kernel.evaluate(tx, POINTS))
            polygon = document._get(seed.handle)
            wire, face = _slots(polygon.shape)
            for value in (None, ("build123d.polygon-native", True), ("build123d.polygon-native", 2)):
                with self.assertRaises(ValueError):
                    _polygon_slots(polygon.shape, value)
            with self.assertRaises(ValueError):
                _polygon_slots(_pack((face, wire)), polygon.auxiliary)
            sketch = effects.first(tx, seed)
            with bd.WorkplaneList(bd.Plane.XY):
                transfer = effects.transfer(tx, sketch, None)
            pending = document._get(transfer.bundle.handle)
            value = pending.auxiliary
            for invalid in (None, (value[0], True, *value[2:]),
                            (*value[:3], (("tool", 0),)), (*value[:3], (("created", True),))):
                with self.assertRaises(ValueError):
                    _decode_pending(invalid, pending.shape, has_prior=False)
            face_handle = effects.stock.project(tx, transfer.bundle, transfer.faces[0])
            product = effects.extrude(tx, face_handle, (0., 0., 3.), clean=True)
            extrusion = document._get(product.handle)
            for invalid in (None, ("build123d.polygon-extrusion", True, True),
                            ("build123d.polygon-extrusion", 1, 1)):
                with self.assertRaises(ValueError):
                    _extrusion_slots(extrusion.shape, invalid, True)
            slots = _slots(extrusion.shape)
            with self.assertRaises(ValueError):
                _extrusion_slots(_pack((slots[1], slots[1], slots[2])), extrusion.auxiliary, True)
            tx.commit()

    def test_clockwise_profile_and_tilted_plane_match_stock_and_polygon_raw_compound_aliases(self):
        def build(points, escape):
            with bd.BuildPart() as part:
                with bd.BuildSketch(bd.Plane(origin=(2, 3, 4), x_dir=(0, 1, 0), z_dir=(1, 0, 0))) as sketch:
                    polygon = bd.Polygon(points, align=None)
                    aliases = None
                    if escape:
                        aliases = (polygon.wrapped.ShapeType().name,
                                   polygon.wrapped.IsSame(sketch._obj.wrapped),
                                   sum(a.wrapped.IsSame(b.wrapped) for a in polygon.faces() for b in sketch._obj.faces()))
                bd.extrude(amount=3.)
            return part.part, aliases
        def facts(shape):
            return round(shape.volume, 7), tuple(round(v, 7) for v in (*shape.bounding_box().min, *shape.bounding_box().max))
        for points in (POINTS, tuple(reversed(POINTS))):
            for escape in (False, True):
                expected, aliases = build(points, escape)
                document = Document("tilted-sketch")
                for _ in range(2):
                    with document.begin() as tx:
                        with FrontendSession(tx) as frontend:
                            actual, actual_aliases = build(points, escape)
                            self.assertEqual(aliases, actual_aliases)
                            self.assertEqual(facts(expected), facts(actual))
                            self.assertEqual(int(not escape), frontend._fallback_counts.get("sketch-extrusion-retained", 0))
                        tx.commit()

    def test_multiple_locations_execute_stock_path_and_native_escape_preserves_retained_result(self):
        def located():
            with bd.BuildPart() as part:
                with bd.BuildSketch():
                    with bd.Locations((0, 0), (12, 0)):
                        bd.Polygon(POINTS, align=None)
                bd.extrude(amount=3.)
            return part.part
        expected = located()
        with Document("repeated-sketch-locations").begin() as tx:
            with FrontendSession(tx) as frontend:
                actual = located()
                self.assertEqual(0, frontend._fallback_counts.get("sketch-effects-retained", 0))
                self.assertAlmostEqual(expected.volume, actual.volume)
            tx.commit()

        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.gp import gp_Pnt
        document = Document("sketch-result-isolation")
        for turn in range(2):
            with document.begin() as tx:
                with FrontendSession(tx):
                    with bd.BuildPart() as part:
                        with bd.BuildSketch():
                            bd.Polygon(POINTS, align=None)
                        base = part.pending_faces[0]
                        result = bd.extrude(amount=3.)
                    computed = tx.stats.computed
                    self.assertAlmostEqual(114., result.volume)
                    if turn:
                        self.assertEqual(0, computed)
                        self.assertFalse(any(vertex.X == 40. for vertex in result.vertices()))
                    else:
                        vertex = base.vertices()[0].wrapped
                        BRep_Builder().UpdateVertex(vertex, gp_Pnt(40., 30., 20.), .01)
                        self.assertTrue(any(BRep_Tool.Pnt_s(v.wrapped).X() == 40. for v in result.vertices()))
                        self.assertTrue(any(BRep_Tool.Pnt_s(v.wrapped).X() == 40. for v in part.part.vertices()))
                tx.commit()

    def test_lazy_extrude_export_restores_the_ordinary_function_after_session(self):
        import build123d
        import cadgen.build123d as proxy
        original = build123d.extrude
        proxy.__dict__.pop("extrude", None)
        with Document("extrude-export-restoration").begin() as tx:
            with FrontendSession(tx):
                self.assertIs(proxy.extrude, build123d.extrude)
                self.assertIsNot(original, proxy.extrude)
            self.assertIs(original, proxy.extrude)
            self.assertIs(original, build123d.extrude)
            tx.commit()


if __name__ == "__main__":
    unittest.main()
