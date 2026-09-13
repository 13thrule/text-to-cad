"""Closed polygon producers and complete pending-face extrusion effects.

The source constructors and builder lifecycle execute normally. Native wire
and face outputs share one retained carrier so their real aliases can survive
later wrapper publication and one connected-family escape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import inspect
import math
from typing import Any

from .builder_effects import (EffectBundle, StockBuilderEffects, UnsupportedBuilderEffect, WrapperRef,
                             _decode_layout, _encode_layout, _pack, _slots)
from .core import GeometryHandle, Mutation, OperatorSpec
from .native import NativeResult, copy_shape


@dataclass(frozen=True)
class PolygonSeed:
    handle: GeometryHandle


@dataclass(frozen=True)
class PolygonNative:
    wire: Any
    face: Any


@dataclass(frozen=True)
class PendingTransfer:
    bundle: EffectBundle
    faces: tuple[WrapperRef, ...]


@dataclass(frozen=True)
class ExtrusionProduct:
    handle: GeometryHandle
    clean: bool
    count: int


def _polygon_slots(native, auxiliary):
    if (type(auxiliary) is not tuple or len(auxiliary) != 2
            or auxiliary[0] != "build123d.polygon-native" or type(auxiliary[1]) is not int or auxiliary[1] != 1):
        raise ValueError("invalid retained polygon auxiliary data")
    slots = _slots(native)
    if (len(slots) != 2 or tuple(shape.ShapeType().name for shape in slots) != ("TopAbs_WIRE", "TopAbs_FACE")):
        raise ValueError("invalid retained polygon native outputs")
    return slots


def _extrusion_slots(native, auxiliary, clean):
    if (type(auxiliary) is not tuple or len(auxiliary) != 4
            or auxiliary[0] != "build123d.polygon-extrusion"
            or type(auxiliary[1]) is not int or auxiliary[1] != 2
            or type(auxiliary[2]) is not bool or auxiliary[2] is not clean
            or type(auxiliary[3]) is not int or not 1 <= auxiliary[3] <= 4096):
        raise ValueError("invalid polygon extrusion auxiliary data")
    count = auxiliary[3]
    slots = _slots(native)
    if (len(slots) != 3 * count or tuple(shape.ShapeType().name for shape in slots) !=
            (("TopAbs_FACE",) * count + ("TopAbs_SOLID",) * (2 * count))):
        raise ValueError("invalid polygon extrusion native outputs")
    return slots


def _decode_pending(value, native, *, has_prior):
    if (type(value) is not tuple or len(value) != 4 or value[0] != "build123d.pending-sketch"
            or type(value[1]) is not int or value[1] != 1 or type(value[3]) is not tuple
            or not 1 <= len(value[3]) <= 4096):
        raise ValueError("invalid pending sketch auxiliary data")
    layout = _decode_layout(value[2], native, expected_root="Part" if has_prior else None)
    if (layout.input_count != 1 + int(has_prior) or layout.prior_slot != (0 if has_prior else None)
            or len(layout.tools) != 1 or layout.tools[0].kind != "Sketch"):
        raise ValueError("invalid pending sketch input roles")
    faces = []
    for ref in value[3]:
        if (type(ref) is not tuple or len(ref) != 2 or ref[0] != "created"
                or type(ref[1]) is not int or not 0 <= ref[1] < len(layout.created)
                or layout.created[ref[1]].kind != "Face"):
            raise ValueError("invalid pending sketch face role")
        faces.append(WrapperRef(*ref))
    if len(set(faces)) != len(faces):
        raise ValueError("invalid duplicate pending sketch face role")
    return layout, tuple(faces)


class PolygonKernel:
    """A stock numeric closed-profile producer with complete native outputs.

    The caller must establish stock provider identity and unexposed constructor
    provenance before invoking this adapter. It never accepts a caller-owned
    wire or face and never borrows a native input from another alias family.
    """

    def __init__(self, frontend=None, *, extra_providers=(), require_cached=False):
        import build123d as bd
        from build123d.topology import two_d
        self.bd = bd
        self.frontend = frontend
        self.make_wire = bd.Wire.make_polygon
        self.make_face = two_d._make_topods_face_from_wires
        self.providers = StockBuilderEffects(frontend, extra_providers=(
            (bd.Wire, "make_polygon"), (bd.Wire, "__init__"),
            *((bd.Vector, name) for name in ("__init__", "__iter__", "__eq__", "__sub__",
                                            "length", "to_pnt", "wrapped", "X", "Y", "Z")),
            (two_d, "_make_topods_face_from_wires"),
            *extra_providers,
        ), require_cached=require_cached)

    def evaluate(self, tx, points: tuple[tuple[float, float], ...]) -> PolygonSeed:
        if not self.providers.providers_match():
            raise UnsupportedBuilderEffect("closed polygon providers changed")
        if (type(points) is not tuple or len(points) < 3
                or any(type(point) is not tuple or len(point) != 2
                       or any(type(value) not in (float, int) or not math.isfinite(value)
                              for value in point) for point in points)):
            raise ValueError("a retained polygon requires a finite numeric planar point loop")
        canonical = tuple(tuple(float(value) for value in point) for point in points)
        def compute(_inputs, _arena):
            wire = self.make_wire([self.bd.Vector(*point) for point in canonical])
            native_wire = wire.wrapped
            native_face = self.make_face(native_wire, [])
            return NativeResult(_pack((native_wire, native_face)),
                                auxiliary=("build123d.polygon-native", 1))
        def execute(inputs, arena):
            return (compute(inputs, arena) if self.frontend is None
                    else self.frontend._inside_compute(compute, inputs, arena))
        handle = tx.evaluate(
            OperatorSpec("build123d.builder.polygon-native", "1", Mutation.READ_ONLY,
                         closed_constructor=True), (canonical, self.providers._context_key), (), execute)
        native = tx.document._get(handle)
        _polygon_slots(native.shape, native.auxiliary)
        return PolygonSeed(handle)

    def instantiate(self, tx, seed: PolygonSeed) -> PolygonNative:
        from .resources import ResourceRequest
        with tx.document.admission.admit(ResourceRequest(), cancellation=tx.cancellation):
            native = copy_shape(tx.document._get(seed.handle).shape)
        tx.stats.native_copies += 1
        wire, face = _polygon_slots(native, tx.document._get(seed.handle).auxiliary)
        return PolygonNative(wire, face)

    def own(self, tx, seed: PolygonSeed, *, logical_id: str | None = None) -> PolygonSeed:
        """Retain one private input family including the pre-face wire.

        Copying the complete carrier preserves wire/face sharing and avoids
        coupling a fresh authored polygon to the canonical kernel allocation.
        """
        handle = tx.evaluate(OperatorSpec("build123d.builder.polygon-input", "1"),
                             (), (seed.handle,),
                             lambda inputs, arena: NativeResult(
                                 inputs[0], auxiliary=("build123d.polygon-native", 1)),
                             logical_id=logical_id)
        return PolygonSeed(handle)

    def project(self, tx, seed: PolygonSeed, slot: int) -> GeometryHandle:
        if type(slot) is not int or slot not in (0, 1):
            raise ValueError("a polygon has only wire and face output slots")
        return tx.evaluate(
            OperatorSpec("build123d.builder.polygon-output", "1", Mutation.READ_ONLY),
            slot, (seed.handle,), lambda inputs, arena: NativeResult(_slots(inputs[0])[slot]))


class SketchNativeEffects:
    """Sequential ADDs of closed Polygons, retaining all local sketch effects."""

    def __init__(self, frontend=None, *, require_cached=False):
        import build123d as bd
        from build123d import objects_sketch, operations_part
        self.bd = bd
        self.frontend = frontend
        self.kernel = PolygonKernel(frontend, extra_providers=(
            (bd.Polygon, "__init__"), (objects_sketch.BaseSketchObject, "__init__"),
            (bd.BuildSketch, "_obj"), (bd.BuildSketch, "_add_to_pending"),
            (bd.Sketch, "__init__"), (bd.Sketch, "cast"),
            *((bd.Face, name) for name in ("is_coplanar", "_uv_bounds", "normal_at", "__neg__")),
            *((bd.Plane, name) for name in ("__init__", "contains", "z_dir", "x_dir",
                                           "origin", "to_local_coords", "from_local_coords", "_to_from_local_coords",
                                           "reverse_transform", "forward_transform", "to_gp_ax3", "wrapped")),
            (type(bd.Plane), "XY"),
            *((owner, name) for owner in (bd.BuildSketch, bd.Sketch, bd.Polygon, bd.Wire, bd.Plane, bd.Vector)
              for name in ("__getattribute__", "__setattr__")),
            (bd.Builder, "_get_context"), (bd.BuildSketch, "_get_context"),
            *((bd.LocationList, name) for name in ("_get_context", "__getattribute__", "__setattr__")),
            *((bd.Location, name) for name in ("__init__", "__eq__", "wrapped")),
            *((owner, name) for owner in (bd.Face, bd.Sketch, bd.Compound, bd.Part)
              for name in ("__deepcopy__", "__new__")),
            *((bd.Compound, name) for name in ("get_type", "compounds")),
            *((bd.Matrix, name) for name in ("__init__", "__new__", "__getattribute__", "__setattr__")),
            (bd.Solid, "extrude"), (operations_part, "extrude"),
            *((bd.Vector, name) for name in ("dot", "normalized", "__mul__", "__add__", "__sub__")),
        ), require_cached=require_cached)
        self.stock = self.kernel.providers
        self.solid_extrude = inspect.getattr_static(bd.Solid, "extrude")
        self.clean = inspect.getattr_static(bd.Shape, "clean")

    def add(self, tx, seed: PolygonSeed,
            previous: EffectBundle | None = None) -> EffectBundle:
        bd = self.bd
        if not self.stock.providers_match():
            raise UnsupportedBuilderEffect("stock sketch providers changed")
        if tx.escape_arena.active:
            raise UnsupportedBuilderEffect("sketch inputs have no post-escape reuse proof")
        skip_clean = inspect.getattr_static(bd.SkipClean, "clean")
        def tool(native):
            # BaseSketchObject extracts a new face wrapper whose topo_parent
            # remains the original constructor face. Preserve both wrappers.
            face = bd.Face(bd.Face.cast(_slots(native)[1]).wrapped)
            return face.faces()[0]
        def compute(inputs, arena):
            def capture():
                return self.stock._capture(previous, inputs, bd.Mode.ADD, True, skip_clean,
                                           builder_type=bd.BuildSketch, tool_factory=tool)
            native, layout = self.stock._execute(capture)
            return NativeResult(native, auxiliary=_encode_layout(layout))
        arguments = (() if previous is None else (previous.handle,)) + (seed.handle,)
        handle = tx.evaluate(
            OperatorSpec("build123d.builder.sketch-add-effects", "1", Mutation.READ_ONLY),
            (skip_clean, self.stock._context_key), arguments, compute)
        prototype = tx.document._get(handle)
        decoded_key = (handle.prototype_id, "sketch-effects-decoded-layout")
        layout = tx.document._derivations.get(decoded_key)
        if layout is None:
            layout = _decode_layout(prototype.auxiliary, prototype.shape, expected_root="Sketch")
            if (layout.input_count != 1 + int(previous is not None)
                    or layout.prior_slot != (0 if previous is not None else None)
                    or len(layout.tools) != 1 or layout.tools[0].kind != "Face"):
                raise ValueError("invalid sketch addition input roles")
            tx.document._derivations[decoded_key] = layout
        return EffectBundle(handle, layout, previous, (seed.handle,))

    def transfer(self, tx, sketch: EffectBundle, previous: EffectBundle | None) -> PendingTransfer:
        bd = self.bd
        if not self.stock.providers_match() or tx.escape_arena.active:
            raise UnsupportedBuilderEffect("pending face transfer requires unexposed stock inputs")
        workplanes = self.stock._workplane_current.get(None)
        if workplanes is None or len(workplanes.workplanes) != 1:
            raise UnsupportedBuilderEffect("pending transfer requires one workplane")
        plane = workplanes.workplanes[0]
        from OCP.gp import gp_Pln
        if type(object.__getattribute__(plane, "__dict__").get("_wrapped")) is not gp_Pln:
            raise UnsupportedBuilderEffect("pending transfer requires a stock plane transform")
        reverse = plane.reverse_transform
        transform = tuple(reverse.wrapped.Value(row, column) for row in range(1, 4) for column in range(1, 5))
        arguments = (() if previous is None else (previous.handle,)) + (sketch.handle,)
        skip = inspect.getattr_static(bd.SkipClean, "clean")
        def tool(native):
            return self.stock._root_wrapper(sketch, native)
        def compute(inputs, arena):
            def capture():
                return self.stock._capture(previous, inputs, bd.Mode.ADD, True, skip,
                                           tool_factory=tool, include_pending=True)
            native, layout, faces = self.stock._execute(capture)
            return NativeResult(native, auxiliary=("build123d.pending-sketch", 1, _encode_layout(layout),
                                                    tuple((ref.role, ref.index) for ref in faces)))
        handle = tx.evaluate(OperatorSpec("build123d.builder.pending-sketch", "1", Mutation.READ_ONLY),
                             (transform, skip, self.stock._context_key), arguments, compute)
        prototype = tx.document._get(handle)
        key = (handle.prototype_id, "pending-sketch-decoded-layout")
        decoded = tx.document._derivations.get(key)
        if decoded is None:
            decoded = _decode_pending(prototype.auxiliary, prototype.shape, has_prior=previous is not None)
            tx.document._derivations[key] = decoded
        layout, faces = decoded
        return PendingTransfer(EffectBundle(handle, layout, previous, (sketch.handle,)), faces)

    def extrude(self, tx, faces: tuple[GeometryHandle, ...],
                direction: tuple[float, float, float], *, clean: bool) -> ExtrusionProduct:
        bd = self.bd
        if not self.stock.providers_match() or tx.escape_arena.active:
            raise UnsupportedBuilderEffect("extrusion requires an unexposed stock polygon face")
        if (type(faces) is not tuple or not 1 <= len(faces) <= 4096
                or any(type(face) is not GeometryHandle for face in faces)
                or type(direction) is not tuple or len(direction) != 3 or type(clean) is not bool
                or any(type(v) not in (float, int) or not math.isfinite(v) for v in direction)
                or not any(direction)):
            raise UnsupportedBuilderEffect("extrusion requires a finite nonzero direction")
        def compute(inputs, arena):
            def kernel():
                raw, cleaned = [], []
                for native in inputs:
                    source = bd.Face(bd.Face.cast(native).wrapped)
                    solid = self.solid_extrude.__func__(bd.Solid, source, direction)
                    raw.append(self.stock._wrapped.fget(solid))
                    if clean:
                        self.clean(solid)
                    cleaned.append(self.stock._wrapped.fget(solid))
                return NativeResult(
                    _pack((*inputs, *raw, *cleaned)),
                    auxiliary=("build123d.polygon-extrusion", 2, clean, len(inputs)))
            return self.stock._execute(kernel)
        handle = tx.evaluate(OperatorSpec("build123d.builder.polygon-extrusion", "2", Mutation.READ_ONLY),
                             (direction, clean, self.stock._context_key), faces, compute)
        prototype = tx.document._get(handle)
        _extrusion_slots(prototype.shape, prototype.auxiliary, clean)
        return ExtrusionProduct(handle, clean, len(faces))

    def extrusion_inputs(self, tx, product: ExtrusionProduct) -> tuple[GeometryHandle, ...]:
        result = []
        for index in range(product.count):
            slot = 2 * product.count + index
            result.append(tx.evaluate(
                OperatorSpec("build123d.builder.extrusion-input", "2", Mutation.READ_ONLY),
                index, (product.handle,),
                lambda inputs, arena, slot=slot: NativeResult(_slots(inputs[0])[slot])))
        return tuple(result)

    def extrusion_result(self, tx, inputs: tuple[GeometryHandle, ...]) -> GeometryHandle:
        bd = self.bd
        def compute(native_inputs, _arena):
            def kernel():
                solids = [bd.Solid(bd.Solid.cast(native).wrapped) for native in native_inputs]
                return NativeResult(self.stock._wrapped.fget(bd.Part(solids)))
            return self.stock._execute(kernel)
        return tx.evaluate(
            OperatorSpec("build123d.builder.extrusion-result", "1", Mutation.READ_ONLY),
            self.stock._context_key, inputs, compute)


@dataclass
class _PolygonFrame:
    shape: Any
    builder: Any
    points: tuple
    logical_id: str
    previous: "_SketchState | None" = None
    seed: PolygonSeed | None = None
    native: PolygonNative | None = None
    wire: Any = None
    bundle: EffectBundle | None = None
    pending: list = field(default_factory=list)
    wrappers: list = field(default_factory=list)


@dataclass
class _SketchState:
    bundle: EffectBundle
    result: Any
    result_handle: GeometryHandle
    lasts: Any = None
    rows: tuple = ()
    eligible: bool = True


@dataclass
class _PendingState:
    transfer: PendingTransfer
    source_faces: tuple
    handles: tuple[GeometryHandle, ...]
    faces: list
    planes: list
    plane: Any


@dataclass
class _ExtrudeFrame:
    builder: Any
    pending_state: _PendingState
    clean: bool
    mode: Any
    direction: tuple[float, float, float]
    product: ExtrusionProduct | None = None
    input_handles: tuple[GeometryHandle, ...] = ()
    result_handle: GeometryHandle | None = None
    native_slots: tuple | None = None
    sources: list = field(default_factory=list)
    source_indices: dict = field(default_factory=dict)
    cleaned: set = field(default_factory=set)
    outputs: tuple[GeometryHandle, ...] = ()
    source_natives: tuple = ()
    published: bool = False
    pending: list = field(default_factory=list)
    wrappers: list = field(default_factory=list)


class SketchEffectsFrontend:
    """Provenance for sequential stock Polygon construction sequences."""

    def __init__(self, frontend, *, deferred=False):
        import contextvars
        from build123d import operations_part
        from build123d.topology import two_d
        f, bd = frontend, frontend._bd
        self.frontend = f
        self.effects = (None if deferred else
                        SketchNativeEffects(f, require_cached=False))
        self.stock = None if self.effects is None else self.effects.stock
        self.current = None
        self.extruding = None
        self.builders = {}
        self.owners = {}
        self.pending = {}
        self.context = inspect.getattr_static(bd.Builder, "_current")
        self.locations = inspect.getattr_static(bd.LocationList, "_current")
        self.contexts_stock = (type(self.context) is contextvars.ContextVar
                               and type(self.locations) is contextvars.ContextVar)
        if self.stock is not None:
            self.stock._guards.extend(((bd.Builder, "_current", self.context),
                                       (bd.LocationList, "_current", self.locations)))
        self.polygon_init = bd.Polygon.__init__
        original_wire = inspect.getattr_static(bd.Wire, "make_polygon")
        original_face = two_d._make_topods_face_from_wires

        def polygon(shape, *points, **kwargs):
            if f._compute_depth:
                return self.polygon_init(shape, *points, **kwargs)
            if self.stock is None:
                self.activate(require_cached=True)
            admitted = self._admit(shape, points, kwargs)
            old = self.current
            self.current = (_PolygonFrame(
                shape, self.context.get(None), admitted[0], f._logical("polygon-input"),
                admitted[1]) if admitted is not None else None)
            succeeded = False
            try:
                self.polygon_init(shape, *points, **kwargs)
                succeeded = True
            finally:
                frame = self.current
                self.current = old
                if frame is not None:
                    self._finish(frame, succeeded)

        def wire(cls, vertices, close=True):
            frame = self.current
            if (f._compute_depth or frame is None or frame.seed is not None
                    or cls is not bd.Wire or close is not True
                    or type(vertices) is not list or not all(type(v) is bd.Vector for v in vertices)
                    or not self.stock.providers_match()):
                return original_wire.__func__(cls, vertices, close)
            actual = tuple((v.X, v.Y) for v in vertices)
            if actual != frame.points or any(v.Z != 0 for v in vertices):
                return original_wire.__func__(cls, vertices, close)
            frame.seed = self.effects.kernel.own(
                f.transaction, self.effects.kernel.evaluate(f.transaction, frame.points),
                logical_id=frame.logical_id)
            frame.native = self.effects.kernel.instantiate(f.transaction, frame.seed)
            frame.wire = cls(bd.Wire.cast(frame.native.wire).wrapped)
            return frame.wire

        def face(outer_wire, inner_wires):
            frame = self.current
            if (not f._compute_depth and frame is not None and frame.native is not None
                    and type(inner_wires) is list and not inner_wires
                    and outer_wire.IsSame(frame.native.wire) and self.stock.providers_match()):
                return frame.native.face
            return original_face(outer_wire, inner_wires)

        self._patch(bd.Polygon, "__init__", polygon)
        self._patch(bd.Wire, "make_polygon", classmethod(wire))
        self._patch(two_d, "_make_topods_face_from_wires", face)
        self._install_extrude(operations_part)

    def activate(self, *, require_cached=True, finalize=True):
        if self.stock is not None:
            return self
        bd = self.frontend._bd
        self.effects = SketchNativeEffects(self.frontend, require_cached=require_cached)
        self.stock = self.effects.stock
        self.stock._guards.extend(((bd.Builder, "_current", self.context),
                                   (bd.LocationList, "_current", self.locations)))
        if finalize:
            self.frontend._finalize_effect_guards()
        return self

    def _install_extrude(self, operations_part):
        f, bd = self.frontend, self.frontend._bd
        original = operations_part.extrude
        import cadgen.build123d as proxy
        # Seed the ordinary lazy export before installing the native-module
        # interceptor. Otherwise the proxy's first lookup could retain this
        # session's closure after all native attributes have been restored.
        vars(proxy).setdefault("extrude", original)
        solid_extrude = inspect.getattr_static(bd.Solid, "extrude")
        clean_shape = inspect.getattr_static(bd.Shape, "clean")
        def extrude(to_extrude=None, amount=None, dir=None, until=None, target=None,
                    both=False, taper=0., clean=True, mode=bd.Mode.ADD):
            if self.stock is None:
                self.activate(require_cached=True)
            old = self.extruding
            admitted = self._admit_extrude(
                to_extrude, amount, dir, until, target, both, taper, clean, mode)
            self.extruding = (_ExtrudeFrame(
                self.context.get(None), admitted[0], clean, mode, admitted[1])
                if admitted is not None else None)
            result, succeeded = None, False
            try:
                # This is the original Python body: pending lists are consumed
                # before its later validation, including when it raises.
                result = original(to_extrude, amount, dir, until, target, both, taper, clean, mode)
                succeeded = True
                return result
            finally:
                frame = self.extruding
                self.extruding = old
                if frame is not None:
                    self._finish_extrude(frame, result, succeeded)

        def solid(cls, obj, direction):
            frame = self.extruding
            from OCP.gp import gp_Vec
            index = -1 if frame is None else len(frame.sources)
            if (f._compute_depth or frame is None
                    or index >= len(frame.pending_state.source_faces)
                    or cls is not bd.Solid or obj is not frame.pending_state.source_faces[index]
                    or type(direction) is not bd.Vector
                    or type(object.__getattribute__(direction, "__dict__").get("_wrapped")) is not gp_Vec
                    or not self.stock.providers_match()):
                return solid_extrude.__func__(cls, obj, direction)
            values = tuple(direction)
            if values != frame.direction:
                return solid_extrude.__func__(cls, obj, direction)
            if frame.product is None:
                frame.product = self.effects.extrude(
                    f.transaction, frame.pending_state.handles, frame.direction,
                    clean=frame.clean)
                frame.input_handles = self.effects.extrusion_inputs(
                    f.transaction, frame.product)
                frame.result_handle = self.effects.extrusion_result(
                    f.transaction, frame.input_handles)
                from .resources import ResourceRequest
                with f.transaction.document.admission.admit(
                        ResourceRequest(), cancellation=f.transaction.cancellation):
                    owned = copy_shape(f.transaction.document._get(frame.product.handle).shape)
                f.transaction.stats.native_copies += 1
                frame.native_slots = _slots(owned)
            count = frame.product.count
            source = cls(bd.Solid.cast(frame.native_slots[count + index]).wrapped)
            frame.source_indices[id(source)] = index
            frame.sources.append(source)
            return source

        def clean(shape):
            frame = self.extruding
            index = None if frame is None else frame.source_indices.get(id(shape))
            if (not f._compute_depth and frame is not None and index is not None
                    and frame.product is not None and frame.clean
                    and index not in frame.cleaned and self.stock.providers_match()):
                count = frame.product.count
                f._native_originals["wrapped"].fset(
                    shape, bd.Solid.cast(frame.native_slots[2 * count + index]).wrapped)
                frame.cleaned.add(index)
                return shape
            return clean_shape(shape)

        self._patch(bd.Solid, "extrude", classmethod(solid))
        self._patch(bd.Shape, "clean", clean)
        self._patch(operations_part, "extrude", extrude)
        self._patch(bd, "extrude", extrude)
        self._patch(proxy, "extrude", extrude)

    def _admit_extrude(self, to_extrude, amount, direction, until, target, both, taper, clean, mode):
        from .frontend import _state
        f, bd = self.frontend, self.frontend._bd
        try:
            finite_amount = type(amount) in (float, int) and math.isfinite(amount) and amount != 0
        except OverflowError:
            finite_amount = False
        if (f._compute_depth or not self.contexts_stock or not self.stock.providers_match()
                or f.transaction.escape_arena.active or to_extrude is not None or direction is not None
                or until is not None or target is not None or both is not False
                or type(taper) not in (float, int) or taper != 0 or type(clean) is not bool
                or not finite_amount
                or type(mode) is not bd.Mode or mode not in (bd.Mode.ADD, bd.Mode.SUBTRACT, bd.Mode.REPLACE)):
            return None
        builder = self.context.get(None)
        if type(builder) is not bd.BuildPart:
            return None
        pending = self.pending.get(id(builder))
        if (pending is None or builder.pending_faces is not pending.faces or builder.pending_face_planes is not pending.planes
                or not 1 <= len(pending.faces) <= 4096
                or len(pending.faces) != len(pending.source_faces)
                or len(pending.planes) != len(pending.source_faces)
                or any(pending.faces[index] is not face
                       for index, face in enumerate(pending.source_faces))
                or any(plane is not pending.plane for plane in pending.planes)
                or any(_state(face) is None or _state(face).private
                       or _state(face).handle != pending.handles[index]
                       for index, face in enumerate(pending.source_faces))):
            return None
        vector = pending.plane.z_dir * amount
        direction_values = tuple(vector)
        if (len(direction_values) != 3
                or any(type(value) not in (int, float) or not math.isfinite(value)
                       for value in direction_values)
                or not any(direction_values)):
            return None
        return pending, direction_values

    def _patch(self, owner, name, replacement):
        old = inspect.getattr_static(owner, name)
        self.frontend._patch(owner, name, replacement)
        # This is our own installed interceptor, after validating the original
        # provider. Runtime comparisons still reject subsequent authored edits.
        for audit in (self.stock, self.frontend._builder_effects.stock):
            if audit is None:
                continue
            audit._guards = [(o, n, replacement if n == name and v is old
                             and inspect.getattr_static(o, n) is replacement else v)
                             for o, n, v in audit._guards]
            if not inspect.isclass(owner):
                audit._globals = [(ns, n, replacement if ns is vars(owner) and n == name and v is old else v)
                                  for ns, n, v in audit._globals]

    def _admit(self, shape, points, kwargs):
        f, bd = self.frontend, self.frontend._bd
        if (not self.contexts_stock or not self.stock.providers_match()
                or type(shape) is not bd.Polygon or f.transaction.escape_arena.active
                or not f._can_defer_hierarchy(shape, ())
                or set(kwargs) - {"rotation", "align", "mode"}
                or kwargs.get("align", (bd.Align.NONE,) * 2) is not None
                or type(kwargs.get("rotation", 0)) not in (int, float)
                or kwargs.get("rotation", 0) != 0 or kwargs.get("mode", bd.Mode.ADD) is not bd.Mode.ADD):
            return None
        builder = self.context.get(None)
        if type(builder) is not bd.BuildSketch:
            return None
        if (builder._tag != "BuildSketch" or builder._shape is not bd.Face or builder._sub_class is not bd.Sketch
                or type(builder.lasts) is not dict
                or any(name in vars(builder) for name in ("_add_to_context", "_add_to_pending", "_obj", "_shapes"))):
            return None
        previous = self.builders.get(id(builder))
        if previous is None:
            if vars(builder).get("_sketch_local") is not None:
                return None
        elif not self._builder_unchanged(builder, previous):
            return None
        locations = self.locations.get(None)
        if type(locations) is not bd.LocationList:
            return None
        if inspect.getattr_static(bd.LocationList, "local_locations", None) is not None:
            return None
        backing = vars(locations).get("local_locations")
        from OCP.TopLoc import TopLoc_Location
        if (type(backing) not in (list, tuple) or len(backing) != 1
                or type(backing[0]) is not bd.Location
                or type(object.__getattribute__(backing[0], "__dict__").get("_wrapped")) is not TopLoc_Location
                or backing[0] != bd.Location()):
            return None
        if len(points) == 1 and type(points[0]) in (list, tuple):
            points = points[0]
        try:
            if (len(points) < 3 or any(type(p) not in (tuple, list) or len(p) != 2
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in p) for p in points)):
                return None
            return tuple(tuple(float(v) for v in p) for p in points), previous
        except OverflowError:
            return None

    def add(self, builder, objects, kwargs):
        if self.stock is None:
            return False
        f, bd, frame = self.frontend, self.frontend._bd, self.current
        if not f._compute_depth and self.extruding is not None:
            return self._extrude_add(builder, objects, kwargs)
        if not f._compute_depth and frame is None and self._transfer(builder, objects, kwargs):
            return True
        if (f._compute_depth or frame is None or frame.builder is not builder or frame.seed is None
                or frame.bundle is not None or len(objects) != 1 or type(objects[0]) is not bd.Face
                or kwargs != {"mode": bd.Mode.ADD} or f.transaction.escape_arena.active
                or not self.stock.providers_match()):
            return False
        previous = frame.previous
        if ((previous is None and vars(builder).get("_sketch_local") is not None)
                or (previous is not None and not self._builder_unchanged(builder, previous))):
            return False
        source = objects[0]
        raw = object.__getattribute__(source, "__dict__")
        parent = raw.get("topo_parent")
        if (type(parent) is not bd.Face or not f._native_originals["wrapped"].fget(parent).IsSame(frame.native.face)
                or not f._native_originals["wrapped"].fget(source).IsSame(frame.native.face)):
            return False
        bundle = self.effects.add(
            f.transaction, frame.seed, None if previous is None else previous.bundle)
        frame.bundle = bundle
        made = {WrapperRef("tool", 0): source}
        if previous is not None:
            made[WrapperRef("prior")] = previous.result
        parent_ref = bundle.layout.tools[0].topo_parent
        if parent_ref is None:
            raise ValueError("stock sketch effect lost its constructor face")
        made[parent_ref] = parent
        def wrapper(ref):
            if ref in made:
                return made[ref]
            record = bundle.layout.created[ref.index]
            handle = self.stock.project(f.transaction, bundle, ref)
            shape = self.stock._execute(self.stock._instantiate, record, f.transaction.document._get(handle).shape)
            made[ref] = shape
            shape.topo_parent = None if record.topo_parent is None else wrapper(record.topo_parent)
            self._manage(shape, handle, builder)
            return shape
        result = wrapper(bundle.layout.result)
        builder.obj_before = None if previous is None else previous.result
        builder.to_combine = list(objects)
        builder._obj = result
        for kind, row in zip((bd.Vertex, bd.Edge, bd.Face, bd.Solid), bundle.layout.lasts):
            builder.lasts[kind] = bd.ShapeList(wrapper(ref) for ref in row)
        frame.pending.extend((shape, self.stock.project(f.transaction, bundle, ref))
                             for ref, shape in ((WrapperRef("tool", 0), source), (parent_ref, parent)))
        frame.pending.append((frame.wire, self.effects.kernel.project(f.transaction, frame.seed, 0)))
        from .frontend import _state
        result_state = _state(result)
        if result_state is None or result_state.handle is None:
            raise ValueError("stock sketch result lost its managed geometry handle")
        result_handle = result_state.handle
        self.builders[id(builder)] = _SketchState(bundle, result, result_handle)
        f._record_fallback("sketch-effects-retained")
        return True

    def _extrude_add(self, builder, objects, kwargs):
        from .builder_effects import _BuilderState, _single_solid
        from .native import topology_map
        f, bd, frame = self.frontend, self.frontend._bd, self.extruding
        if (frame.builder is not builder or frame.product is None or frame.result_handle is None
                or len(objects) != frame.product.count or len(frame.sources) != len(objects)
                or len(frame.input_handles) != len(objects)
                or any(type(source) is not bd.Solid or objects[index] is not source
                       for index, source in enumerate(frame.sources))
                or kwargs != {"clean": frame.clean, "mode": frame.mode}
                or (frame.clean and frame.cleaned != set(range(len(objects))))
                or f.transaction.escape_arena.active
                or not self.stock.providers_match()):
            return False
        solid = f._builder_effects.activate(require_cached=True)
        raw = vars(builder)
        if (any(name in raw for name in ("_add_to_context", "_add_to_pending", "_obj", "_shapes"))
                or type(raw.get("lasts")) is not dict
                or builder._tag != "BuildPart" or builder._shape is not bd.Solid or builder._sub_class is not bd.Part):
            return False
        previous = solid.builders.get(id(builder))
        if previous is not None:
            if not previous.eligible or builder._part is not previous.part or not solid._part_unchanged(previous):
                return False
            prior = topology_map(f.transaction.document._get(previous.bundle.handle).shape)
            if any(prior.Contains(_single_solid(f.transaction.document._get(handle).shape))
                   for handle in frame.input_handles):
                return False
        elif builder._part is not None or frame.mode is bd.Mode.SUBTRACT:
            return False
        natives = tuple(f._native_originals["wrapped"].fget(source)
                        for source in frame.sources)
        builder.obj_before = builder._part
        builder.to_combine = list(objects)
        bundle = solid.stock.evaluate(
            f.transaction, None if previous is None else previous.bundle,
            frame.input_handles, mode=frame.mode, clean=frame.clean)
        made = {WrapperRef("tool", index): source
                for index, source in enumerate(frame.sources)}
        if previous is not None:
            made[WrapperRef("prior")] = previous.part
        def wrapper(ref):
            if ref in made:
                return made[ref]
            record = bundle.layout.created[ref.index]
            handle = solid.stock.project(f.transaction, bundle, ref)
            shape = solid.stock._execute(
                solid.stock._instantiate, record,
                f.transaction.document._get(handle).shape)
            made[ref] = shape
            shape.topo_parent = None if record.topo_parent is None else wrapper(record.topo_parent)
            solid._manage(shape, handle, builder)
            return shape
        result = wrapper(bundle.layout.result)
        builder._part = result
        for kind, row in zip((bd.Vertex, bd.Edge, bd.Face, bd.Solid), bundle.layout.lasts):
            builder.lasts[kind] = bd.ShapeList(wrapper(ref) for ref in row)
        frame.outputs = tuple(solid.stock.project(
            f.transaction, bundle, WrapperRef("tool", index))
            for index in range(len(frame.sources)))
        frame.source_natives = natives
        frame.pending.extend(zip(frame.sources, frame.outputs))
        solid.builders[id(builder)] = _BuilderState(bundle, result)
        f._record_fallback("builder-effects-retained")
        f._record_fallback("sketch-extrusion-retained")
        frame.published = True
        return True

    def _transfer(self, builder, objects, kwargs):
        from .builder_effects import _BuilderState
        from .frontend import _state
        f, bd = self.frontend, self.frontend._bd
        if (type(builder) is not bd.BuildPart or len(objects) != 1 or type(objects[0]) is not bd.Sketch
                or kwargs != {"mode": bd.Mode.ADD} or f.transaction.escape_arena.active
                or not self.stock.providers_match()):
            return False
        source = objects[0]
        owner = self.owners.get(id(source))
        sketch = self.builders.get(id(owner))
        if (sketch is None or not sketch.eligible or source is not sketch.result
                or _state(source) is None or _state(source).private
                or not self._sketch_unchanged(sketch)):
            return False
        raw = vars(builder)
        if (any(name in raw for name in ("_add_to_context", "_add_to_pending", "_obj", "_shapes"))
                or type(raw.get("lasts")) is not dict
                or builder._tag != "BuildPart" or builder._shape is not bd.Solid or builder._sub_class is not bd.Part
                or any(type(raw.get(name)) is not list or raw[name] for name in
                       ("pending_faces", "pending_face_planes", "pending_edges"))):
            return False
        solid = f._builder_effects.activate(require_cached=True)
        previous = solid.builders.get(id(builder))
        if previous is not None:
            if not previous.eligible or builder._part is not previous.part or not solid._part_unchanged(previous):
                return False
        elif builder._part is not None:
            return False
        context = self.stock._workplane_current.get(None)
        if context is None or len(context.workplanes) != 1:
            return False
        transfer = self.effects.transfer(f.transaction, sketch.bundle, None if previous is None else previous.bundle)
        bundle = transfer.bundle
        made = {WrapperRef("tool", 0): source}
        if previous is not None:
            made[WrapperRef("prior")] = previous.part
        projected = {}
        def wrapper(ref):
            if ref in made:
                return made[ref]
            record = bundle.layout.created[ref.index]
            handle = self.stock.project(f.transaction, bundle, ref)
            projected[ref] = handle
            shape = self.stock._execute(self.stock._instantiate, record, f.transaction.document._get(handle).shape)
            made[ref] = shape
            shape.topo_parent = None if record.topo_parent is None else wrapper(record.topo_parent)
            solid._manage(shape, handle, builder)
            return shape
        builder.obj_before = None if previous is None else previous.part
        builder.to_combine = list(objects)
        result = None if bundle.layout.result is None else wrapper(bundle.layout.result)
        builder._part = result
        for kind, row in zip((bd.Vertex, bd.Edge, bd.Face, bd.Solid), bundle.layout.lasts):
            builder.lasts[kind] = bd.ShapeList(wrapper(ref) for ref in row)
        faces = tuple(wrapper(ref) for ref in transfer.faces)
        handles = tuple(projected[ref] for ref in transfer.faces)
        plane = context.workplanes[0]
        builder.pending_faces.extend(faces)
        builder.pending_face_planes.extend(plane for _face in faces)
        self.pending[id(builder)] = _PendingState(
            transfer, faces, handles, builder.pending_faces,
            builder.pending_face_planes, plane)
        if result is not None:
            solid.builders[id(builder)] = _BuilderState(bundle, result)
        f._record_fallback("sketch-pending-retained")
        return True

    def _sketch_unchanged(self, state):
        from .frontend import _state
        source = state.result
        raw = object.__getattribute__(source, "__dict__")
        record = state.bundle.layout.created[state.bundle.layout.result.index]
        if raw.keys() - {"_wrapped", "_cadgen_document_state", "for_construction", "label", "_color",
                         "topo_parent", "material", "joints", "_NodeMixin__children", "_NodeMixin__parent"}:
            return False
        managed = _state(source)
        return (managed is not None and managed.session is self.frontend
                and not managed.private and managed.handle == state.result_handle
                and type(raw.get("label")) is str and raw["label"] == record.label
                and type(raw.get("material")) is str and raw["material"] == record.material
                and raw.get("for_construction") is record.for_construction and raw.get("_color") is None
                and raw.get("topo_parent") is None and type(raw.get("joints")) is dict and not raw["joints"]
                and type(raw.get("_NodeMixin__children")) is list and not raw["_NodeMixin__children"]
                and raw.get("_NodeMixin__parent") is None)

    def _builder_unchanged(self, builder, state):
        from .frontend import _state
        bd = self.frontend._bd
        if (not state.eligible or vars(builder).get("_sketch_local") is not state.result
                or builder.lasts is not state.lasts or not self._sketch_unchanged(state)
                or len(state.rows) != 4):
            return False
        for kind, expected_list, expected in state.rows:
            current = state.lasts.get(kind)
            if (current is not expected_list or type(current) is not bd.ShapeList
                    or list.__len__(current) != len(expected)):
                return False
            for index, (shape, handle, parent) in enumerate(expected):
                if list.__getitem__(current, index) is not shape:
                    return False
                managed = _state(shape)
                raw = object.__getattribute__(shape, "__dict__")
                if (managed is None or managed.session is not self.frontend or managed.private
                        or managed.handle != handle or raw.get("topo_parent") is not parent):
                    return False
        return True

    def _snapshot_builder(self, builder, state):
        from .frontend import _state
        bd = self.frontend._bd
        rows = []
        for kind in (bd.Vertex, bd.Edge, bd.Face, bd.Solid):
            current = builder.lasts.get(kind)
            if type(current) is not bd.ShapeList:
                state.eligible = False
                return
            expected = []
            for shape in list.__iter__(current):
                managed = _state(shape)
                if managed is None or managed.session is not self.frontend or managed.private:
                    state.eligible = False
                    return
                raw = object.__getattribute__(shape, "__dict__")
                expected.append((shape, managed.handle, raw.get("topo_parent")))
            rows.append((kind, current, tuple(expected)))
        state.lasts = builder.lasts
        state.rows = tuple(rows)

    def _manage(self, shape, handle, builder):
        self.frontend._builder_effects._manage(shape, handle, builder)
        self.owners[id(shape)] = builder

    def capture(self, shape):
        extruding = self.extruding
        if extruding is not None and extruding.result_handle is not None:
            native = self.frontend._native_originals["wrapped"].fget(shape)
            from OCP.TopAbs import TopAbs_SOLID
            from OCP.TopExp import TopExp_Explorer
            explorer = TopExp_Explorer(native, TopAbs_SOLID)
            solids = []
            while explorer.More():
                solids.append(explorer.Current())
                explorer.Next()
            remaining = list(extruding.source_natives)
            matches = len(solids) == len(remaining)
            for solid in solids:
                indices = [index for index, expected in enumerate(remaining)
                           if solid.IsSame(expected)]
                if len(indices) != 1:
                    matches = False
                    break
                remaining.pop(indices[0])
            if matches:
                extruding.wrappers.append(shape)
            return matches
        frame = self.current
        if frame is None or frame.bundle is None:
            return False
        native = self.frontend._native_originals["wrapped"].fget(shape)
        # Only the two constructor-owned compounds containing this one face
        # can inherit the pending tool binding. No arbitrary compound is reused.
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        faces = TopExp_Explorer(native, TopAbs_FACE)
        if not faces.More() or not faces.Current().IsSame(frame.native.face):
            return False
        faces.Next()
        if faces.More():
            return False
        frame.wrappers.append(shape)
        return True

    def _finish(self, frame, succeeded):
        if not succeeded or frame.bundle is None:
            self.revoke(frame.builder)
            return
        for shape, handle in frame.pending:
            self._manage(shape, handle, frame.builder)
        tool = self.stock.project(self.frontend.transaction, frame.bundle, WrapperRef("tool", 0))
        for shape in (*frame.wrappers, frame.shape):
            self._manage(shape, tool, frame.builder)
        state = self.builders.get(id(frame.builder))
        if state is not None and state.bundle is frame.bundle:
            self._snapshot_builder(frame.builder, state)

    def _finish_extrude(self, frame, result, succeeded):
        solid = self.frontend._builder_effects
        self.pending.pop(id(frame.builder), None)
        captured_result = any(shape is result for shape in frame.wrappers)
        if (not succeeded or not frame.published or frame.result_handle is None
                or not captured_result):
            solid.revoke(frame.builder)
            return
        for shape, handle in frame.pending:
            solid._manage(shape, handle, frame.builder)
        for shape in frame.wrappers:
            solid._manage(shape, frame.result_handle, frame.builder)

    def revoke(self, builder):
        state = self.builders.get(id(builder))
        if state is not None:
            state.eligible = False

    def revoke_shape(self, shape):
        builder = self.owners.get(id(shape))
        if builder is not None:
            self.revoke(builder)
