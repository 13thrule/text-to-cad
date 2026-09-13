"""Bounded build123d frontend for the retained-document P1 proof.

The public authoring spelling remains ``from cadgen import build123d as bd``.
While a :class:`FrontendSession` is active, a deliberately small algebraic
subset records native computations in a document transaction.  Every other
operation crosses one explicit boundary into the transaction's private native
arena and then executes as ordinary build123d Python.

This is runtime tracing, not AST purity inference.  Model bodies, helpers,
branches, loops, callbacks, and their side effects execute on every revision.
"""
from __future__ import annotations

from contextvars import ContextVar
import copy
from dataclasses import dataclass
from dataclasses import replace
import inspect
import math
import sys
import threading
from types import FunctionType
from typing import Any, Iterable, Iterator

from .core import GeometryHandle, Mutation, OperatorSpec, RevisionTransaction
from .native import NativeResult, copy_shape, history_from_builder
from .resources import ResourceRequest


_ACTIVE: ContextVar["FrontendSession | None"] = ContextVar(
    "cadgen_document_frontend", default=None
)
_PATCH_LOCK = threading.RLock()
_IDENTITY = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


@dataclass
class _ManagedState:
    session: "FrontendSession"
    handle: GeometryHandle | None
    logical_id: str
    location: Any = None
    transform: tuple[float, ...] = _IDENTITY
    children: tuple[Any, ...] | None = None
    private: bool = False
    geometry_view: GeometryHandle | None = None

    def __deepcopy__(self, memo: dict) -> "_ManagedState":
        # build123d copies a wrapper's attribute dictionary for operations such
        # as rotate().  The session owns locks/native state and must never be
        # pickled or recursively copied; the copied wrapper remains in the same
        # private execution arena and is recaptured at its next managed edge.
        return _ManagedState(self.session, self.handle, self.logical_id,
                             self.location, self.transform, self.children, True)


def _state(shape: Any) -> _ManagedState | None:
    try:
        return object.__getattribute__(shape, "_cadgen_document_state")
    except AttributeError:
        return None


def _matrix(location: Any) -> tuple[float, ...]:
    trsf = location.wrapped.Transformation()
    return (
        *(float(trsf.Value(row, column)) for row in range(1, 4) for column in range(1, 5)),
        0.0, 0.0, 0.0, 1.0,
    )


def _axis_key(axis: Any) -> tuple[float, ...]:
    position = axis.position
    direction = axis.direction
    return (*map(float, position), *map(float, direction))


def _stock_function(value: Any, module: str, name: str) -> bool:
    """Recognize installed provider code, never an author's decorated wrapper."""
    if isinstance(value, (classmethod, staticmethod)):
        value = value.__func__
    provider = sys.modules.get(module)
    return (type(value) is FunctionType and value.__module__ == module
            and value.__qualname__ == name and not hasattr(value, "__wrapped__")
            and provider is not None
            and value.__code__.co_filename == provider.__file__)


def _stock_global(name: str, value: Any) -> bool:
    if type(value) is FunctionType:
        module = value.__module__
        return ((module.startswith("build123d.") or module.split(".")[0] in sys.stdlib_module_names)
                and _stock_function(value, module, value.__qualname__))
    if callable(value):
        module = getattr(value, "__module__", "")
        return (module.startswith(("build123d.", "OCP."))
                or module.split(".")[0] in sys.stdlib_module_names)
    return True


class ManagedSelection:
    """A deferred topology selection that never leaks resident subshapes."""

    __slots__ = ("_owner", "_kind", "_filters")

    def __init__(self, owner: Any, kind: str, filters: tuple = ()) -> None:
        self._owner = owner
        self._kind = kind
        self._filters = filters

    def filter_by(self, criterion: Any, reverse: bool = False,
                  tolerance: float = 1e-5) -> "ManagedSelection | Any":
        session = _require_session(self._owner)
        if callable(criterion):
            # A callback is ordinary Python with observable effects.  Run it,
            # and therefore the selection, privately on every source replay.
            return self._private_value().filter_by(criterion, reverse, tolerance)
        bd = session._bd
        if isinstance(criterion, bd.Axis):
            descriptor = ("axis", _axis_key(criterion), bool(reverse), float(tolerance), criterion)
        elif isinstance(criterion, bd.Plane):
            descriptor = ("plane", tuple(map(float, criterion.origin)),
                          tuple(map(float, criterion.z_dir)), bool(reverse),
                          float(tolerance), criterion)
        elif isinstance(criterion, bd.GeomType):
            descriptor = ("geom", criterion.name, bool(reverse), float(tolerance), criterion)
        elif isinstance(criterion, property):
            # A property may invoke arbitrary author code.  Preserve that
            # behavior by crossing the native boundary.
            return self._private_value().filter_by(criterion, reverse, tolerance)
        else:
            return self._private_value().filter_by(criterion, reverse, tolerance)
        return ManagedSelection(self._owner, self._kind, self._filters + (descriptor,))

    def _parameters(self) -> tuple:
        return (self._kind, tuple(item[:-1] for item in self._filters))

    def _apply(self, native_owner: Any) -> Any:
        session = _require_session(self._owner)
        wrapped = session._wrap_native(native_owner)
        values = getattr(wrapped, self._kind)()
        for descriptor in self._filters:
            values = values.filter_by(
                descriptor[-1], reverse=descriptor[-3], tolerance=descriptor[-2]
            )
        return values

    def _private_value(self) -> Any:
        session = _require_session(self._owner)
        native_owner = session._escape_shape(self._owner)
        return self._apply(native_owner)

    def __len__(self) -> int:
        session = _require_session(self._owner)
        state = _state(self._owner)
        if state is None or state.private or state.handle is None:
            return len(self._private_value())
        handle = session._geometry_handle(self._owner)
        return session.transaction.query(handle, lambda native: len(self._apply(native)))

    def __iter__(self) -> Iterator[Any]:
        return iter(self._private_value())

    def __getitem__(self, index: Any) -> Any:
        return self._private_value()[index]


def _require_session(shape: Any | None = None) -> "FrontendSession":
    state = None if shape is None else _state(shape)
    session = _ACTIVE.get() if state is None else state.session
    if session is None or not session.active:
        raise RuntimeError("managed build123d value used outside its document execution")
    return session


class FrontendSession:
    """Temporarily route the explicit P1 build123d subset into ``transaction``.

    Sessions are intentionally thread-affine and non-overlapping: build123d's
    class methods are process globals, while document ownership is one kernel
    thread.  The adapters restore every attribute on exit.
    """

    _SAFE_ATTRIBUTES = frozenset({
        "_cadgen_document_state", "__class__", "label", "color", "_color",
        "material", "joints", "parent", "children", "topo_parent", "_dim",
        "dimension", "wrapped", "edges", "faces", "vertices", "solids",
        "bounding_box", "volume", "is_valid", "moved", "located", "__dict__",
        "_NodeMixin__children", "_NodeMixin__parent",
        "_NodeMixin__children_or_empty",
    })

    def __init__(self, transaction: RevisionTransaction) -> None:
        if not isinstance(transaction, RevisionTransaction):
            raise TypeError("FrontendSession requires a document revision transaction")
        self.transaction = transaction
        self.active = False
        self._token = None
        self._originals: list[tuple[Any, str, Any]] = []
        self._logical_counts: dict[tuple, int] = {}
        self._compute_depth = 0
        self._bd = None
        self._topology = None
        self._fallback_counts: dict[str, int] = {}
        self._builder_kernel: tuple[str, str] | None = None

    @classmethod
    def current(cls) -> "FrontendSession | None":
        return _ACTIVE.get()

    def __enter__(self) -> "FrontendSession":
        if _ACTIVE.get() is not None:
            raise RuntimeError("a build123d document frontend is already active")
        _PATCH_LOCK.acquire()
        try:
            # Managed execution must never coexist with the old BREP-key memo
            # or its approximate global shape-equality shims.
            from cadgen._internal import op_memo
            if op_memo._installed:  # internal engine boundary, intentionally explicit
                raise RuntimeError(
                    "document frontend cannot run while the retired op memo is installed"
                )
            import build123d as bd
            from build123d import topology
            self._bd, self._topology = bd, topology
            self._token = _ACTIVE.set(self)
            self.active = True
            self._install()
            return self
        except BaseException as original_error:
            restore_error = None
            try:
                self._restore()
            except BaseException as error:
                restore_error = error
            finally:
                self.active = False
                if self._token is not None:
                    _ACTIVE.reset(self._token)
                    self._token = None
                _PATCH_LOCK.release()
            if restore_error is not None:
                raise restore_error from original_error
            raise

    def __exit__(self, *exc: Any) -> None:
        try:
            self._restore()
        finally:
            self.active = False
            if self._token is not None:
                _ACTIVE.reset(self._token)
                self._token = None
            _PATCH_LOCK.release()

    def _restore(self) -> None:
        failure = None
        for owner, name, original in reversed(self._originals):
            try:
                setattr(owner, name, original)
            except BaseException as error:  # finish restoring the process-global surface
                failure = failure or error
        self._originals.clear()
        if failure is not None:
            raise failure

    def _patch(self, owner: Any, name: str, replacement: Any) -> None:
        original = inspect.getattr_static(owner, name)
        self._originals.append((owner, name, original))
        setattr(owner, name, replacement)

    def _install(self) -> None:
        bd, topology = self._bd, self._topology
        session = self

        original_getattribute = inspect.getattr_static(bd.Shape, "__getattribute__")
        original_wrapped = inspect.getattr_static(bd.Shape, "wrapped")
        original_box_init = inspect.getattr_static(bd.Box, "__init__")
        original_cylinder_init = inspect.getattr_static(bd.Cylinder, "__init__")
        original_compound_init = inspect.getattr_static(bd.Compound, "__init__")
        original_add = inspect.getattr_static(bd.Shape, "__add__")
        original_sub = inspect.getattr_static(bd.Shape, "__sub__")
        original_compound_add = inspect.getattr_static(bd.Compound, "__add__")
        original_compound_sub = inspect.getattr_static(bd.Compound, "__sub__")
        original_moved = inspect.getattr_static(bd.Shape, "moved")
        original_located = inspect.getattr_static(bd.Shape, "located")
        original_rmul = inspect.getattr_static(bd.Shape, "__rmul__")
        original_fillet_method = inspect.getattr_static(topology.Mixin3D, "fillet")
        original_bounding_box = inspect.getattr_static(bd.Shape, "bounding_box")
        original_is_valid = inspect.getattr_static(bd.Shape, "is_valid")
        original_volume = inspect.getattr_static(bd.Compound, "volume")
        original_location_mul = inspect.getattr_static(bd.Location, "__mul__")
        original_fillet_function = bd.fillet
        original_make_box = inspect.getattr_static(bd.Solid, "make_box")
        original_make_cylinder = inspect.getattr_static(bd.Solid, "make_cylinder")

        self._native_originals = {
            "getattribute": original_getattribute,
            "wrapped": original_wrapped,
            "compound_init": original_compound_init,
            "add": original_add,
            "sub": original_sub,
            "compound_add": original_compound_add,
            "compound_sub": original_compound_sub,
            "moved": original_moved,
            "located": original_located,
            "rmul": original_rmul,
            "fillet_method": original_fillet_method,
            "bounding_box": original_bounding_box,
            "is_valid": original_is_valid,
            "volume": original_volume,
            "location_mul": original_location_mul,
            "fillet_function": original_fillet_function,
        }

        def shape_getattribute(shape: Any, name: str) -> Any:
            state = _state(shape)
            if (state is not None and not state.private and session._compute_depth == 0
                    and name not in session._SAFE_ATTRIBUTES):
                session._escape_shape(shape)
            return original_getattribute(shape, name)

        def wrapped_get(shape: Any) -> Any:
            state = _state(shape)
            if state is not None and not state.private:
                session._escape_shape(shape)
            return original_wrapped.fget(shape)

        def wrapped_set(shape: Any, value: Any) -> None:
            state = _state(shape)
            if state is not None:
                if not state.private:
                    session._escape_shape(shape)
                state.private = True
            original_wrapped.fset(shape, value)

        def box_init(shape: Any, length: float, width: float, height: float,
                     rotation=(0, 0, 0), align=None, mode=None) -> None:
            context = bd.Builder._get_context(log=False)
            if session._compute_depth or context is not None:
                kwargs = {"rotation": rotation}
                if align is not None:
                    kwargs["align"] = align
                if mode is not None:
                    kwargs["mode"] = mode
                session._builder_constructor(
                    "box", shape, context, original_box_init,
                    (length, width, height), kwargs,
                    original_make_box, (length, width, height),
                )
                return
            align = (bd.Align.CENTER,) * 3 if align is None else align
            mode = bd.Mode.ADD if mode is None else mode
            if not session._closed_primitive(
                    "box", shape, (length, width, height), rotation, align, mode):
                session._record_fallback("opaque-box-provider-or-parameters")
                original_box_init(shape, length, width, height,
                                  rotation=rotation, align=align, mode=mode)
                session._capture_private(shape, "opaque-box")
                return
            logical = session._logical("box")
            parameters = (float(length), float(width), float(height),
                          session._rotation_key(rotation), session._align_key(align), mode,
                          session._primitive_context_key("box", original_make_box))
            def compute(_inputs, _arena):
                native = object.__new__(bd.Box)
                session._inside_compute(original_box_init, native, length, width, height,
                                        rotation=rotation, align=align, mode=mode)
                return NativeResult(original_wrapped.fget(native))
            handle = session.transaction.evaluate(
                OperatorSpec("build123d.Box", "1", Mutation.READ_ONLY,
                             closed_constructor=True), parameters, (), compute,
                logical_id=logical,
            )
            session._init_empty(shape, logical, handle)
            shape.length, shape.width, shape.box_height = length, width, height

        def cylinder_init(shape: Any, radius: float, height: float, arc_size: float = 360,
                          rotation=(0, 0, 0), align=None, mode=None) -> None:
            context = bd.Builder._get_context(log=False)
            if session._compute_depth or context is not None:
                kwargs = {"arc_size": arc_size, "rotation": rotation}
                if align is not None:
                    kwargs["align"] = align
                if mode is not None:
                    kwargs["mode"] = mode
                session._builder_constructor(
                    "cylinder", shape, context, original_cylinder_init,
                    (radius, height), kwargs, original_make_cylinder,
                    (radius, height, arc_size),
                )
                return
            align = (bd.Align.CENTER,) * 3 if align is None else align
            mode = bd.Mode.ADD if mode is None else mode
            if not session._closed_primitive(
                    "cylinder", shape, (radius, height, arc_size), rotation, align, mode):
                session._record_fallback("opaque-cylinder-provider-or-parameters")
                original_cylinder_init(shape, radius, height, arc_size,
                                       rotation=rotation, align=align, mode=mode)
                session._capture_private(shape, "opaque-cylinder")
                return
            logical = session._logical("cylinder")
            parameters = (float(radius), float(height), float(arc_size),
                          session._rotation_key(rotation), session._align_key(align), mode,
                          session._primitive_context_key("cylinder", original_make_cylinder))
            def compute(_inputs, _arena):
                native = object.__new__(bd.Cylinder)
                session._inside_compute(original_cylinder_init, native, radius, height,
                                        arc_size=arc_size, rotation=rotation,
                                        align=align, mode=mode)
                return NativeResult(original_wrapped.fget(native))
            handle = session.transaction.evaluate(
                OperatorSpec("build123d.Cylinder", "1", Mutation.READ_ONLY,
                             closed_constructor=True), parameters, (), compute,
                logical_id=logical,
            )
            session._init_empty(shape, logical, handle)
            shape.radius, shape.cylinder_height, shape.arc_size = radius, height, arc_size
            shape.align = align

        def compound_init(shape: Any, obj=None, label="", color=None, material="",
                          joints=None, parent=None, children=None) -> None:
            supplied = children if children is not None else obj
            values = None
            if (not session._compute_depth and supplied is not None
                    and not hasattr(supplied, "ShapeType")):
                try:
                    values = tuple(supplied)
                except TypeError:
                    values = None
            # BasePartObject passes its real native compound in ``obj`` and an
            # author hierarchy in ``children``.  Empty iterables and calls
            # carrying both cannot establish managed occurrence ownership;
            # treating them as such would discard Sphere/Torus/etc. geometry.
            if (values and not (obj is not None and children is not None)
                    and type(shape) is bd.Compound and children is not None
                    and parent is None
                    and len({id(value) for value in values}) == len(values)
                    and session._can_defer_hierarchy(shape, values)
                    and all(_state(value) is not None
                            and _state(value).handle is not None
                            and _state(value).children is None
                            and value.parent is None for value in values)):
                logical = session._logical("compound")
                session._init_empty(shape, logical, None, children=values)
                shape.label = label
                shape._color = color
                shape.material = "" if material is None else material
                shape.joints = {} if joints is None else joints
                # These exact, unattached Shape children have no hierarchy
                # validation or detach work left. Attach their Python nodes
                # immediately, deferring only native compound construction.
                object.__setattr__(shape, "_NodeMixin__children", list(values))
                for child in values:
                    object.__setattr__(child, "_NodeMixin__parent", shape)
                return
            # A one-shot iterable has already been inspected. The ordinary
            # constructor must receive that same buffered sequence, including
            # unmanaged/mixed children and obj= geometry-only compounds.
            if values is not None:
                if children is not None:
                    children = values
                else:
                    obj = values
            if not session._compute_depth:
                session._record_fallback("compound-native-construction")
            original_compound_init(shape, obj=obj, label=label, color=color,
                                   material=material, joints=joints, parent=parent,
                                   children=children)
            if not session._compute_depth:
                session._capture_private(shape, "opaque-compound")

        def add(shape: Any, other: Any) -> Any:
            if _state(shape) is not None and session._managed_operand(other):
                return session._boolean("fuse", shape, other)
            if _state(shape) is not None:
                session._escape_shape(shape)
            return original_add(shape, other)

        def sub(shape: Any, other: Any) -> Any:
            if _state(shape) is not None and session._managed_operand(other):
                return session._boolean("cut", shape, other)
            if _state(shape) is not None:
                session._escape_shape(shape)
            return original_sub(shape, other)

        def compound_add(shape: Any, other: Any) -> Any:
            if _state(shape) is not None and session._managed_operand(other):
                return session._boolean("fuse", shape, other)
            if _state(shape) is not None:
                session._escape_shape(shape)
            return original_compound_add(shape, other)

        def compound_sub(shape: Any, other: Any) -> Any:
            if _state(shape) is not None and session._managed_operand(other):
                return session._boolean("cut", shape, other)
            if _state(shape) is not None:
                session._escape_shape(shape)
            return original_compound_sub(shape, other)

        def moved(shape: Any, location: Any) -> Any:
            state = _state(shape)
            if state is None or state.private:
                return original_moved(shape, location)
            return session._placed(shape, location, absolute=False)

        def located(shape: Any, location: Any) -> Any:
            state = _state(shape)
            if state is None or state.private:
                return original_located(shape, location)
            return session._located(shape, location)

        def rmul(shape: Any, other: Any) -> Any:
            if _state(shape) is not None and isinstance(other, (bd.Location, bd.Plane)):
                return moved(shape, other.location if isinstance(other, bd.Plane) else other)
            return original_rmul(shape, other)

        def location_mul(location: Any, other: Any) -> Any:
            # build123d's Location.__mul__ probes arbitrary iterables before
            # returning NotImplemented.  A managed Shape is iterable through
            # its hierarchy, and that probe would cross the native boundary
            # before Shape.__rmul__ gets the placement.
            if _state(other) is not None:
                return NotImplemented
            return original_location_mul(location, other)

        def edges(shape: Any) -> Any:
            state = _state(shape)
            return (ManagedSelection(shape, "edges") if state is not None and not state.private
                    else session._native_call("edges", shape))

        def faces(shape: Any) -> Any:
            state = _state(shape)
            return (ManagedSelection(shape, "faces") if state is not None and not state.private
                    else session._native_call("faces", shape))

        def vertices(shape: Any) -> Any:
            state = _state(shape)
            return (ManagedSelection(shape, "vertices") if state is not None and not state.private
                    else session._native_call("vertices", shape))

        def solids(shape: Any) -> Any:
            state = _state(shape)
            return (ManagedSelection(shape, "solids") if state is not None and not state.private
                    else session._native_call("solids", shape))

        def bounding_box(shape: Any, tolerance=None, optimal=True) -> Any:
            state = _state(shape)
            if state is None or state.private:
                return original_bounding_box(shape, tolerance, optimal)
            handle = session._geometry_handle(shape)
            return session.transaction.query(
                handle,
                lambda native: original_bounding_box(
                    session._wrap_native(native), tolerance, optimal
                ),
            )

        def volume_get(shape: Any) -> float:
            state = _state(shape)
            if state is None or state.private:
                return original_volume.fget(shape)
            handle = session._geometry_handle(shape)
            return session.transaction.query(
                handle, lambda native: float(session._wrap_native(native).volume)
            )

        def is_valid_get(shape: Any) -> bool:
            state = _state(shape)
            if state is None or state.private:
                return original_is_valid.fget(shape)
            handle = session._geometry_handle(shape)
            return session.transaction.query(
                handle,
                lambda native: bool(original_is_valid.fget(session._wrap_native(native))),
            )

        def fillet_method(shape: Any, radius: float, edge_list: Iterable[Any]) -> Any:
            if isinstance(edge_list, ManagedSelection) and edge_list._owner is shape:
                return session._fillet(shape, edge_list, radius)
            if _state(shape) is not None:
                session._escape_shape(shape)
            result = original_fillet_method(shape, radius, edge_list)
            return session._capture_private(result, "opaque-fillet-method")

        def fillet_function(objects: Any, radius: float) -> Any:
            if isinstance(objects, ManagedSelection):
                return session._fillet(objects._owner, objects, radius)
            result = original_fillet_function(objects, radius)
            return (session._capture_private(result, "opaque-fillet")
                    if isinstance(result, bd.Shape) else result)

        def make_box(cls, *args, **kwargs):
            return session._builder_solid("box", cls, original_make_box, args, kwargs)

        def make_cylinder(cls, *args, **kwargs):
            return session._builder_solid("cylinder", cls, original_make_cylinder, args, kwargs)

        self._patch(bd.Shape, "__getattribute__", shape_getattribute)
        self._patch(bd.Shape, "wrapped", property(wrapped_get, wrapped_set, original_wrapped.fdel,
                                                   original_wrapped.__doc__))
        self._patch(bd.Box, "__init__", box_init)
        self._patch(bd.Cylinder, "__init__", cylinder_init)
        self._patch(bd.Solid, "make_box", classmethod(make_box))
        self._patch(bd.Solid, "make_cylinder", classmethod(make_cylinder))
        self._patch(bd.Compound, "__init__", compound_init)
        self._patch(bd.Shape, "__add__", add)
        self._patch(bd.Shape, "__sub__", sub)
        self._patch(bd.Compound, "__add__", compound_add)
        self._patch(bd.Compound, "__sub__", compound_sub)
        self._patch(bd.Shape, "moved", moved)
        self._patch(bd.Shape, "located", located)
        self._patch(bd.Shape, "__rmul__", rmul)
        self._patch(bd.Location, "__mul__", location_mul)
        self._patch(bd.Shape, "edges", edges)
        self._patch(bd.Shape, "faces", faces)
        self._patch(bd.Shape, "vertices", vertices)
        self._patch(bd.Shape, "solids", solids)
        self._patch(bd.Shape, "bounding_box", bounding_box)
        self._patch(bd.Shape, "is_valid", property(is_valid_get, doc=original_is_valid.__doc__))
        self._patch(bd.Compound, "volume", property(volume_get, doc=original_volume.__doc__))
        self._patch(topology.Mixin3D, "fillet", fillet_method)
        self._patch(bd, "fillet", fillet_function)
        # The lazy proxy may already have cached this function before entry.
        import cadgen.build123d as proxy
        if "fillet" in vars(proxy):
            self._patch(proxy, "fillet", fillet_function)
        self._prepare_primitive_guards(original_box_init, original_cylinder_init,
                                       original_make_box, original_make_cylinder)

    def _prepare_primitive_guards(self, box, cylinder, make_box, make_cylinder):
        """Pin the small stock constructor path, including its native providers.

        The closed contract cannot be inferred from an empty geometry-input
        list. In particular, a replaced make_* or validation hook can read a
        mutable native global. Such calls always execute as ordinary Python.
        """
        from build123d import objects_part, build_common
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
        from OCP.TopoDS import TopoDS
        bd = self._bd
        originals = {(owner, name): value for owner, name, value in self._originals}
        common = (
            (objects_part.BasePartObject, "__init__", "build123d.objects_part", "BasePartObject.__init__"),
            (bd.Solid, "__init__", "build123d.topology.three_d", "Solid.__init__"),
            (bd.Shape, "__init__", "build123d.topology.shape_core", "Shape.__init__"),
            (bd.Compound, "__init__", "build123d.topology.composite", "Compound.__init__"),
            (bd.Shape, "bounding_box", "build123d.topology.shape_core", "Shape.bounding_box"),
            (bd.Shape, "move", "build123d.topology.shape_core", "Shape.move"),
            (bd.Shape, "moved", "build123d.topology.shape_core", "Shape.moved"),
            (bd.BuildPart, "_get_context", "build123d.build_common", "Builder._get_context"),
            (bd.Location, "__init__", "build123d.geometry", "Location.__init__"),
            (bd.Rotation, "__init__", "build123d.geometry", "Rotation.__init__"),
            (bd.Plane, "to_gp_ax2", "build123d.geometry", "Plane.to_gp_ax2"),
            (bd.BoundBox, "to_align_offset", "build123d.geometry", "BoundBox.to_align_offset"),
        )
        common_valid = _stock_function(objects_part.validate_inputs,
                                       "build123d.build_common", "validate_inputs")
        common_checks = []
        global_checks = []
        for owner, name, module, qualified in common:
            current = inspect.getattr_static(owner, name)
            original = originals.get((owner, name), current)
            common_valid &= _stock_function(original, module, qualified)
            common_checks.append((owner, name, current))
            fn = original.__func__ if isinstance(original, classmethod) else original
            if type(fn) is FunctionType:
                # Changes made during a model body must invalidate eligibility,
                # even when the enclosing stock function itself is unchanged.
                global_checks.extend((fn.__globals__, name, fn.__globals__[name])
                                     for name in fn.__code__.co_names if name in fn.__globals__)
        common_valid &= objects_part.Solid is bd.Solid and objects_part.BuildPart is bd.BuildPart
        common_valid &= objects_part.validate_inputs is build_common.validate_inputs
        self._primitive_guards = {}
        for kind, constructor, factory, kernel in (
                ("box", box, make_box, BRepPrimAPI_MakeBox),
                ("cylinder", cylinder, make_cylinder, BRepPrimAPI_MakeCylinder)):
            cls = bd.Box if kind == "box" else bd.Cylinder
            stock = (_stock_function(constructor, "build123d.objects_part", f"{cls.__name__}.__init__")
                     and _stock_function(factory, "build123d.topology.three_d", f"Solid.make_{kind}"))
            kernel_globals = factory.__func__.__globals__ if stock else {}
            native_name = "BRepPrimAPI_MakeBox" if kind == "box" else "BRepPrimAPI_MakeCylinder"
            kernel_valid = (stock and type(kernel).__module__ == "pybind11_builtins"
                            and kernel_globals.get(native_name) is kernel
                            and kernel_globals.get("TopoDS") is TopoDS
                            and (kind == "box" or kernel_globals.get("DEG2RAD") == math.pi / 180))
            native_checks = tuple((owner, name, inspect.getattr_static(owner, name, None))
                                  for owner, name in ((kernel, "__init__"), (kernel, "Shape"),
                                                      (TopoDS, "Solid")))
            kernel_valid &= all(
                type(value).__name__ in ("instancemethod", "builtin_function_or_method")
                and getattr(value, "__module__", "").startswith("OCP.")
                for _, _, value in native_checks)
            kernel_checks = tuple((kernel_globals, name, kernel_globals.get(name))
                                  for name in (native_name, "TopoDS", "DEG2RAD"))
            checks = ((bd.Solid, f"make_{kind}", inspect.getattr_static(bd.Solid, f"make_{kind}")),
                      (cls, "__init__", inspect.getattr_static(cls, "__init__")))
            globals_ = list(global_checks)
            if stock:
                globals_.extend((constructor.__globals__, name, constructor.__globals__[name])
                                for name in constructor.__code__.co_names if name in constructor.__globals__)
            globals_.extend(kernel_checks)
            valid = common_valid and kernel_valid and all(
                _stock_global(name, value) for _, name, value in globals_)
            self._primitive_guards[kind] = (valid, (*checks, *common_checks, *native_checks),
                                           tuple(globals_), factory)

    def _primitive_provider_matches(self, kind):
        valid, attributes, values, factory = self._primitive_guards[kind]
        if not valid:
            return False
        defaults = factory.__func__.__defaults__
        if (not defaults or type(defaults[0]) is not self._bd.Plane
                or "to_gp_ax2" in vars(defaults[0])):
            return False
        return (all(inspect.getattr_static(owner, name) is value for owner, name, value in attributes)
                and all(namespace.get(name) is value for namespace, name, value in values))

    def _primitive_context_key(self, kind, factory):
        # Plane.XY is a mutable factory default; numeric runtime globals such
        # as tolerance must not silently disappear from construction identity.
        values = self._primitive_guards[kind][2]
        return (_matrix(factory.__func__.__defaults__[0].location),
                tuple((namespace.get("__name__"), name, value)
                      for namespace, name, value in values
                      if type(value) in (bool, int, float)))

    def _closed_primitive(self, kind, shape, dimensions, rotation, align, mode):
        bd = self._bd
        try:
            bounded = all(type(value) in (int, float) and math.isfinite(value) and value > 0
                          for value in dimensions)
            bounded_rotation = (type(rotation) is tuple and len(rotation) == 3
                                and all(type(value) in (int, float) and math.isfinite(value)
                                        for value in rotation))
        except OverflowError:
            return False
        return (type(shape) is (bd.Box if kind == "box" else bd.Cylinder)
                and bounded
                and (kind != "cylinder" or dimensions[2] <= 360)
                and bounded_rotation
                and (type(align) is bd.Align or (type(align) is tuple and len(align) == 3
                                               and all(type(value) is bd.Align for value in align)))
                and type(mode) is bd.Mode
                and self._primitive_provider_matches(kind))

    def _inside_compute(self, fn, *args, **kwargs):
        self._compute_depth += 1
        try:
            return fn(*args, **kwargs)
        finally:
            self._compute_depth -= 1

    def _builder_constructor(self, kind, shape, context, original, args, kwargs,
                             kernel_constructor, dimensions) -> None:
        """Reuse only the native primitive, replay every builder effect privately.

        Builder lifecycle methods inspect author frames and remain untouched.
        A complete _add_to_context hit would also have to preserve LAST/NEW,
        obj_before/to_combine aliases and partial failure effects. This bounded
        adapter deliberately executes that method and its booleans every time.
        """
        if self._compute_depth:
            original(shape, *args, **kwargs)
            return
        bd = self._bd
        mode = kwargs.get("mode", bd.Mode.ADD)
        builtin_kernel = self._primitive_provider_matches(kind)
        try:
            bounded_dimensions = all(
                type(value) in (int, float) and math.isfinite(value) and value > 0
                for value in dimensions
            )
        except OverflowError:
            bounded_dimensions = False
        eligible = (
            type(context) is bd.BuildPart
            and type(shape) is (bd.Box if kind == "box" else bd.Cylinder)
            and type(mode) is bd.Mode
            and mode in (bd.Mode.ADD, bd.Mode.SUBTRACT, bd.Mode.REPLACE, bd.Mode.PRIVATE)
            and builtin_kernel
            and bounded_dimensions
            and (kind != "cylinder" or dimensions[2] <= 360)
        )
        self._record_fallback("builder-effects-replayed" if eligible else "builder-opaque-constructor")
        previous = self._builder_kernel
        self._builder_kernel = (kind, self._logical(f"builder-{kind}-kernel")) if eligible else None
        try:
            # Keep author callbacks under the normal frontend boundary. In
            # particular, do not suppress managed attribute/escape checks while
            # a customized validation or constructor hook executes.
            original(shape, *args, **kwargs)
        finally:
            self._builder_kernel = previous

    def _builder_solid(self, kind, cls, original, args, kwargs):
        pending = self._builder_kernel
        factory = original.__get__(None, cls) if hasattr(original, "__get__") else original
        if pending is None or pending[0] != kind or cls is not self._bd.Solid:
            return factory(*args, **kwargs)
        self._builder_kernel = None  # exactly one kernel call per constructor
        # Only the exact factory call made by the ordinary Box/Cylinder body is
        # covered. Forward customized calls without coercion or extra keywords.
        if (len(args) != (3 if kind == "box" else 2)
                or set(kwargs) != (set() if kind == "box" else {"angle"})
                or any(type(value) not in (int, float) for value in args)
                or (kind == "cylinder" and type(kwargs["angle"]) not in (int, float))
                or not self._primitive_provider_matches(kind)):
            return factory(*args, **kwargs)
        logical = pending[1]
        angle = kwargs.get("angle")
        parameters = (tuple(float(value) for value in args),
                      self._primitive_context_key(kind, original),
                      None if angle is None else float(angle))
        def compute(_inputs, _arena):
            solid = original.__func__(cls, *args, **kwargs)
            return NativeResult(self._native_originals["wrapped"].fget(solid))
        handle = self.transaction.evaluate(
            OperatorSpec(f"build123d.builder.make_{kind}", "1", Mutation.READ_ONLY,
                         closed_constructor=True),
            parameters, (), compute, logical_id=logical,
        )
        # Do not expose the cached root or activate the transaction-wide escape
        # arena: this primitive has no input aliases and receives a fresh private
        # allocation before alignment, placement, cleaning or context insertion.
        with self.transaction.document.admission.admit(
                ResourceRequest(), cancellation=self.transaction.cancellation):
            native = copy_shape(self.transaction._validate_handle(handle).shape)
        self.transaction.stats.native_copies += 1
        return cls(self._downcast_native(native))

    def _logical(self, kind: str) -> str:
        frame = inspect.currentframe()
        assert frame is not None
        frame = frame.f_back
        while frame is not None and frame.f_code.co_filename == __file__:
            frame = frame.f_back
        if frame is None:
            site = ("<unknown>", "<unknown>", 0)
        else:
            site = (frame.f_code.co_filename, frame.f_code.co_qualname, frame.f_lasti)
        key = (kind, *site)
        ordinal = self._logical_counts.get(key, 0)
        self._logical_counts[key] = ordinal + 1
        return f"{kind}:{site[0]}:{site[1]}:{site[2]}:{ordinal}"

    def _init_empty(self, shape: Any, logical: str, handle: GeometryHandle | None,
                    *, children: tuple[Any, ...] | None = None) -> Any:
        object.__setattr__(shape, "_wrapped", None)
        object.__setattr__(shape, "for_construction", False)
        object.__setattr__(shape, "label", "")
        object.__setattr__(shape, "_color", None)
        object.__setattr__(shape, "topo_parent", None)
        object.__setattr__(shape, "material", "")
        object.__setattr__(shape, "joints", {})
        object.__setattr__(shape, "_NodeMixin__children", [])
        state = _ManagedState(self, handle, logical, self._bd.Location(), _IDENTITY,
                              children, False)
        object.__setattr__(shape, "_cadgen_document_state", state)
        return shape

    def _capture_private(self, shape: Any, kind: str) -> Any:
        logical = self._logical(kind)
        wrapped = self._native_originals["wrapped"].fget(shape)
        handle = self.transaction.capture(wrapped, logical_id=logical)
        object.__setattr__(shape, "_cadgen_document_state",
                          _ManagedState(self, handle, logical, self._bd.Location(),
                                        _IDENTITY, None, True))
        return shape

    def _rotation_key(self, rotation: Any) -> tuple:
        if type(rotation) in (tuple, list):
            return (type(rotation).__name__, tuple(float(value) for value in rotation))
        return (type(rotation).__module__, type(rotation).__qualname__, tuple(rotation))

    def _align_key(self, align: Any) -> tuple:
        if isinstance(align, self._bd.Align):
            align = (align,) * 3
        return tuple(value.name for value in align)

    def _managed_operand(self, value: Any) -> bool:
        if _state(value) is not None:
            return True
        if type(value) in (list, tuple):
            return all(_state(item) is not None for item in value)
        return False

    def _operand_shapes(self, value: Any) -> tuple[Any, ...]:
        return (value,) if _state(value) is not None else tuple(value)

    def _geometry_handle(self, shape: Any) -> GeometryHandle:
        state = _state(shape)
        if state is None:
            return self.transaction.capture(self._native_originals["wrapped"].fget(shape))
        if state.children is not None:
            native = self._materialize_compound(shape)
            state.handle = self.transaction.capture(
                self._native_originals["wrapped"].fget(native), logical_id=state.logical_id
            )
            state.private = True
            state.children = None
            return state.handle
        if state.private:
            # Raw native aliases can mutate invisibly.  Snapshot again at every
            # later managed boundary and keep the evaluation volatile.
            wrapped = self._native_originals["wrapped"].fget(shape)
            state.handle = self.transaction.capture(wrapped, logical_id=None)
            return state.handle
        if state.handle is None:
            raise RuntimeError("managed shape has no geometry handle")
        if state.transform == _IDENTITY:
            return state.handle
        if state.geometry_view is not None:
            return state.geometry_view
        location, transform = state.location, state.transform
        def compute(inputs, _arena):
            moved_native = inputs[0].Moved(location.wrapped)
            return NativeResult(moved_native)
        state.geometry_view = self.transaction.evaluate(
            OperatorSpec("build123d.rigid_transform", "1", Mutation.READ_ONLY),
            transform, (state.handle,), compute, logical_id=state.logical_id,
        )
        # A located query/operation consumes a native view, while the authored
        # occurrence still owns its canonical prototype and separate placement.
        # Measuring a part must not force its future display mesh to include
        # that placement or turn a transform edit into a prototype change.
        return state.geometry_view

    def _placed(self, shape: Any, location: Any, *, absolute: bool) -> Any:
        if isinstance(location, self._bd.Plane):
            location = location.location
        state = _state(shape)
        assert state is not None
        if not self._can_copy_managed_wrapper(shape):
            return self._private_placement(shape, location, absolute=absolute)
        assert state.handle is not None
        logical = self._logical("located" if absolute else "moved")
        clone = self._copy_managed_wrapper(shape, logical, state.handle)
        clone_state = _state(clone)
        assert clone_state is not None
        clone_state.location = location if absolute else location * state.location
        clone_state.transform = _matrix(clone_state.location)
        return clone

    def _located(self, shape: Any, location: Any) -> Any:
        """Preserve build123d's deep-copying absolute placement semantics."""
        state = _state(shape)
        assert state is not None
        if not self._can_copy_managed_wrapper(shape):
            return self._private_placement(shape, location, absolute=True)
        assert state.handle is not None
        logical = self._logical("located")
        transform = _matrix(location)
        def compute(native_inputs, _arena):
            wrapper = self._wrap_native(native_inputs[0])
            result = self._inside_compute(
                self._native_originals["located"], wrapper, location
            )
            return NativeResult(self._native_originals["wrapped"].fget(result))
        handle = self.transaction.evaluate(
            OperatorSpec("build123d.located", "1", Mutation.READ_ONLY),
            transform, (state.handle,), compute, logical_id=logical,
        )
        return self._copy_managed_wrapper(shape, logical, handle)

    def _record_fallback(self, reason: str) -> None:
        self._fallback_counts[reason] = self._fallback_counts.get(reason, 0) + 1

    def _can_defer_hierarchy(self, parent: Any, children: tuple[Any, ...]) -> bool:
        if any(type(child) not in (self._bd.Box, self._bd.Cylinder, self._bd.Part)
               for child in children):
            return False
        # Direct node attachment is valid only for build123d's own hooks.
        # Subclass and instance hooks can validate or cause observable effects,
        # and must run through the ordinary constructor exactly once.
        for shape, names in (
            (parent, ("_pre_attach_children", "_post_attach_children",
                      "_pre_detach_children", "_post_detach_children")),
            *((child, ("_pre_attach", "_post_attach")) for child in children),
        ):
            for name in names:
                hook = inspect.getattr_static(shape, name)
                if (getattr(hook, "__module__", None),
                    getattr(hook, "__qualname__", None)) not in {
                        (self._bd.Compound.__module__, f"Compound.{name}"),
                        ("anytree.node.nodemixin", f"NodeMixin.{name}"),
                    }:
                    return False
        return True

    def _can_copy_managed_wrapper(self, shape: Any) -> bool:
        state = _state(shape)
        if state is None or state.handle is None or state.children is not None:
            return False
        attributes = object.__getattribute__(shape, "__dict__")
        supported = {
            "_wrapped", "_cadgen_document_state", "for_construction", "label",
            "_color", "topo_parent", "material", "joints",
            "_NodeMixin__children", "_NodeMixin__parent", "length", "width",
            "box_height", "radius", "cylinder_height", "arc_size", "align",
        }
        # Native references, arbitrary deepcopy hooks, parent relationships and
        # joints need build123d's full copy traversal. Decide before invoking
        # any user copying code so an opaque operation executes only once.
        if type(shape) not in (self._bd.Box, self._bd.Cylinder, self._bd.Part):
            return False
        if attributes.keys() - supported:
            return False
        if (type(attributes.get("joints")) is not dict
                or type(attributes.get("_NodeMixin__children")) is not list):
            return False
        if (attributes.get("topo_parent") is not None or attributes.get("joints")
                or attributes.get("_NodeMixin__children")
                or attributes.get("_NodeMixin__parent") is not None):
            return False
        scalar_types = (str, bool, int, float, type(None))
        for key, value in attributes.items():
            if key in {"_wrapped", "_cadgen_document_state", "joints",
                       "_NodeMixin__children", "_NodeMixin__parent", "topo_parent"}:
                continue
            if key == "_color" and type(value) in (self._bd.Color, type(None)):
                continue
            if key == "align" and (isinstance(value, self._bd.Align)
                    or type(value) in (tuple, list)
                    and all(isinstance(item, self._bd.Align) for item in value)):
                continue
            if type(value) not in scalar_types:
                return False
        return True

    def _copy_managed_wrapper(self, shape: Any, logical: str,
                              handle: GeometryHandle) -> Any:
        clone = object.__new__(type(shape))
        self._init_empty(clone, logical, handle)
        memo = {id(shape): clone}
        for key, value in object.__getattribute__(shape, "__dict__").items():
            if key not in {"_wrapped", "_cadgen_document_state"}:
                object.__setattr__(clone, key, copy.deepcopy(value, memo))
        return clone

    def _private_placement(self, shape: Any, location: Any, *, absolute: bool) -> Any:
        operation = "located" if absolute else "moved"
        self._record_fallback(f"{operation}-wrapper-copy")
        self._escape_shape(shape)
        result = self._native_originals[operation](shape, location)
        return self._capture_private(result, f"opaque-{operation}")

    def _boolean(self, operation: str, left: Any, right: Any) -> Any:
        operands = (left, *self._operand_shapes(right))
        handles = tuple(self._geometry_handle(value) for value in operands)
        private_reason = self._private_boolean_reason(operation, handles)
        if private_reason is not None:
            # Establish actual input ownership before a boolean can merge
            # independent or differently placed alias families. The authored
            # calls and native builder then each execute only once.
            self._record_fallback(private_reason)
            for value in operands:
                self._escape_shape(value)
            handles = tuple(self._geometry_handle(value) for value in operands)
        logical = self._logical(operation)
        clean = bool(self._bd.SkipClean.clean)
        if operation == "cut":
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
            builder_type = BRepAlgoAPI_Cut
            original = self._native_originals["sub"]
        else:
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
            builder_type = BRepAlgoAPI_Fuse
            original = self._native_originals["add"]
        def compute(native_inputs, _arena):
            wrappers = tuple(self._wrap_native(native) for native in native_inputs)
            builder = builder_type()
            builder.SetNonDestructive(True)
            previous_clean = self._bd.SkipClean.clean
            self._bd.SkipClean.clean = clean
            try:
                result = self._inside_compute(
                    self._native_originals.get("bool_op", self._bd.Shape._bool_op),
                    wrappers[0], [wrappers[0]], list(wrappers[1:]), builder,
                )
            finally:
                self._bd.SkipClean.clean = previous_clean
            wrapped = self._native_originals["wrapped"].fget(result)
            history = history_from_builder(builder, native_inputs, wrapped)
            if clean:
                history = replace(
                    history, complete=False,
                    reason="build123d boolean cleanup does not expose composed topology history",
                )
            return NativeResult(wrapped, history)
        handle = self.transaction.evaluate(
            OperatorSpec(f"build123d.{operation}", "1", Mutation.READ_ONLY),
            (clean,), handles, compute,
            logical_id=logical,
        )
        result = object.__new__(self._bd.Part)
        self._init_empty(result, logical, handle)
        result.label = left.label
        result._color = left._color
        return result

    def _private_boolean_reason(self, operation: str,
                                handles: tuple[GeometryHandle, ...]) -> str | None:
        if self.transaction.escape_arena.active or len(handles) < 2:
            return None
        native_inputs = tuple(self.transaction.document._get(handle).shape for handle in handles)
        partner_pairs = tuple(
            (first, second)
            for index, first in enumerate(handles)
            for other_index, second in enumerate(handles[index + 1:], index + 1)
            if first.allocation_id != second.allocation_id
            and native_inputs[index].IsPartner(native_inputs[other_index])
        )
        if not partner_pairs and operation != "fuse":
            return None
        owned = self.transaction._allocation_snapshot(handles)
        roots: dict[str, frozenset[str]] = {}

        def root_allocations(key: str) -> frozenset[str]:
            if key not in roots:
                parents = owned[key][1]
                roots[key] = (frozenset().union(*(root_allocations(parent)
                                                 for parent, _source in parents))
                              if parents else frozenset((key,)))
            return roots[key]

        for first, second in partner_pairs:
            if root_allocations(first.allocation_id) != root_allocations(second.allocation_id):
                return "boolean-independent-partners"
        # A fuse can preserve unchanged topology from each input placement.
        # The bounded arena cannot rewrite that mixed-location family safely;
        # run it on actual private inputs from the start. Root-only inputs stay
        # managed, including adjacent primitives placed by constructor align.
        if operation == "fuse" and any(
            shape.IsPartner(source) and not shape.IsSame(source)
            for shape, parents in owned.values() for _parent, source in parents
        ):
            return "boolean-placed-fuse"
        return None

    def _fillet(self, owner: Any, selection: ManagedSelection, radius: float) -> Any:
        handle = self._geometry_handle(owner)
        logical = self._logical("fillet")
        parameters = (float(radius), selection._parameters())
        def compute(native_inputs, _arena):
            from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
            source = native_inputs[0]
            edges = selection._apply(source)
            builder = BRepFilletAPI_MakeFillet(source)
            for edge in edges:
                builder.Add(float(radius), edge.wrapped)
            result = builder.Shape()
            wrapped = self._wrap_native(result)
            if not wrapped.is_valid:
                raise ValueError(f"Failed creating a fillet with radius of {radius}")
            return NativeResult(result, history_from_builder(builder, (source,), result))
        output = self.transaction.evaluate(
            OperatorSpec("build123d.fillet", "1", Mutation.READ_ONLY),
            parameters, (handle,), compute,
            logical_id=logical,
        )
        result = object.__new__(self._bd.Part)
        self._init_empty(result, logical, output)
        result.label = owner.label
        result._color = owner._color
        return result

    def _wrap_native(self, native: Any) -> Any:
        if isinstance(native, self._bd.Shape):
            return native
        return self._inside_compute(self._bd.Part.cast, native)

    def _downcast_native(self, native: Any) -> Any:
        return self._topology.downcast(native)

    def _native_for_wrapper(self, shape: Any, native: Any) -> Any:
        """Give build123d composite wrappers the compound they require."""
        from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_COMPSOLID

        if (isinstance(shape, self._bd.Compound)
                and native.ShapeType() not in (TopAbs_COMPOUND, TopAbs_COMPSOLID)):
            from OCP.BRep import BRep_Builder
            from OCP.TopoDS import TopoDS_Compound

            compound = TopoDS_Compound()
            builder = BRep_Builder()
            builder.MakeCompound(compound)
            builder.Add(compound, native)
            native = compound
        return self._downcast_native(native)

    def _native_call(self, name: str, shape: Any) -> Any:
        original = next(
            value for owner, attr, value in self._originals
            if owner is self._bd.Shape and attr == name
        )
        return original(shape)

    def _escape_shape(self, shape: Any) -> Any:
        state = _state(shape)
        if state is None or state.private:
            return shape
        if state.children is not None:
            return self._materialize_compound(shape)
        handle = self._geometry_handle(shape)
        native = self.transaction.escape_arena.native(handle)
        self._native_originals["wrapped"].fset(
            shape, self._native_for_wrapper(shape, native)
        )
        state.private = True
        return shape

    def _materialize_compound(self, shape: Any) -> Any:
        state = _state(shape)
        assert state is not None and state.children is not None
        native_children = []
        for child in state.children:
            child_state = _state(child)
            assert child_state is not None and child_state.handle is not None
            if child_state.private:
                # deepcopy/copy based build123d operations keep a managed
                # wrapper's bookkeeping but immediately replace its native
                # shape.  Capture that live private shape before assembling;
                # the older handle no longer describes the child.
                handle = self._geometry_handle(child)
                placed = self.transaction.escape_arena.native(handle)
            else:
                raw = self.transaction.escape_arena.native(child_state.handle)
                placed = raw
                if child_state.transform != _IDENTITY:
                    placed = raw.Moved(child_state.location.wrapped)
            self._native_originals["wrapped"].fset(
                child, self._native_for_wrapper(child, placed)
            )
            child_state.private = True
            native_children.append(child)
        native = object.__new__(self._bd.Compound)
        self._inside_compute(
            self._native_originals["compound_init"], native, obj=native_children,
            label=shape.label, color=shape._color, material=shape.material,
            joints=shape.joints,
        )
        self._native_originals["wrapped"].fset(
            shape,
            self._native_for_wrapper(
                shape, self._native_originals["wrapped"].fget(native)
            ),
        )
        # The Python hierarchy was attached at construction. Building from
        # obj= avoids temporarily reparenting those exact child wrappers and
        # invoking hierarchy mutation hooks while this group materializes.
        state.private = True
        state.children = None
        return shape

    def materialize(self, result: Any) -> Any:
        """Return a genuine private build123d Shape for existing exporters."""
        if not isinstance(result, self._bd.Shape):
            raise TypeError("a document-backed model must return a build123d Shape")
        state = _state(result)
        if state is None:
            # Unsupported constructors/build contexts remain ordinary Python,
            # but their final result is still published as an opaque volatile
            # document value rather than bypassing document ownership.
            self.transaction.capture(self._native_originals["wrapped"].fget(result))
            return result
        was_private = state.private
        native = self._escape_shape(result)
        state = _state(native)
        if was_private and state is not None and state.private:
            state.handle = self.transaction.capture(
                self._native_originals["wrapped"].fget(native)
            )
        self._detach(native)
        return native

    def _detach(self, shape: Any) -> None:
        """Drop frontend/session ownership from a completed native result."""
        try:
            children = tuple(object.__getattribute__(shape, "children"))
        except (AttributeError, TypeError):
            children = ()
        for child in children:
            if _state(child) is not None:
                self._detach(child)
        if _state(shape) is not None:
            object.__delattr__(shape, "_cadgen_document_state")


__all__ = ["FrontendSession", "ManagedSelection"]
