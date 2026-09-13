"""Typed, structurally shared native effects for bounded stock solid builders.

This module is an internal proof boundary. It does not intercept author code.
The frontend must establish constructor provenance before supplying inputs and
must revoke that provenance before any authored native access. A result retains
all observable effect outputs, including topology absent from its final Part.
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import nullcontext
from dataclasses import dataclass, field
import inspect
import sys
import threading
from typing import Any

from .core import GeometryHandle, Mutation, OperatorSpec, RevisionTransaction
from .native import NativeResult, topology_map


class UnsupportedBuilderEffect(ValueError):
    pass


_MISSING = object()
_PROVIDER_PLAN_LIMIT = 8
_PROVIDER_PLAN_LOCK = threading.RLock()
_PROVIDER_PLANS = OrderedDict()
_RUNTIME_VALUE_LIMIT = 4096
_RUNTIME_VALUE_DEPTH = 32
_BD_PROVIDER_NAMES = (
    "Align", "Box", "BuildPart", "BuildSketch", "Builder", "Color", "Compound",
    "Cylinder", "Edge", "Face", "LocationList", "Mode", "Part", "Plane", "Polygon",
    "Shape", "ShapeList", "Shell", "Sketch", "SkipClean", "Solid", "Vertex", "Vector",
    "Wire", "WorkplaneList",
)
_WRAPPER_FIELD_NAMES = (
    "label", "material", "_color", "for_construction", "topo_parent",
)
_BUILDER_FIELD_NAMES = (
    "_part", "lasts", "pending_edges", "pending_faces", "pending_face_planes",
    "pending_planes", "obj_before", "to_combine",
)
_TYPE_DICT_GET = type.__dict__["__dict__"].__get__
_TYPE_MRO_GET = type.__dict__["__mro__"].__get__


def _closed_runtime_value(value, *, _seen=None, _budget=None, _depth=0):
    """Snapshot bounded builtin default state without invoking author methods."""
    if _depth > _RUNTIME_VALUE_DEPTH:
        raise ValueError("provider default state exceeds the depth limit")
    if _seen is None:
        _seen, _budget = {}, [0]
    _budget[0] += 1
    if _budget[0] > _RUNTIME_VALUE_LIMIT:
        raise ValueError("provider default state exceeds the item limit")
    kind = type(value)
    scalar = (kind is bool or kind is int or kind is float
              or kind is str or kind is bytes)
    if value is None or scalar:
        if (kind is str or kind is bytes) and len(value) > _RUNTIME_VALUE_LIMIT:
            raise ValueError("provider default scalar exceeds the size limit")
        return ("value", id(kind), value)
    container = (kind is tuple or kind is list or kind is dict
                 or kind is set or kind is frozenset)
    if not container:
        # Identity is deliberately plain numeric data. Looking up attributes on
        # an arbitrary class or comparing the object could call author code.
        return ("identity", id(kind), id(value))
    marker = _seen.get(id(value))
    if marker is not None:
        return ("reference", marker)
    marker = len(_seen)
    _seen[id(value)] = marker
    if kind is tuple or kind is list:
        children = tuple(_closed_runtime_value(item, _seen=_seen, _budget=_budget,
                                               _depth=_depth + 1) for item in value)
    elif kind is dict:
        children = tuple((_closed_runtime_value(key, _seen=_seen, _budget=_budget,
                                                _depth=_depth + 1),
                          _closed_runtime_value(item, _seen=_seen, _budget=_budget,
                                                _depth=_depth + 1))
                         for key, item in value.items())
    else:
        # Preserve native iteration order rather than sorting or hashing values;
        # the encoded children contain only builtin tuples/scalars/integers.
        children = tuple(_closed_runtime_value(item, _seen=_seen, _budget=_budget,
                                               _depth=_depth + 1) for item in value)
    return ("container", id(kind), marker, children)


def _mutable_runtime_state(value, *, _seen=None, _budget=None, _depth=0):
    """Snapshot only graphs that can change without replacing their root."""
    if _depth > _RUNTIME_VALUE_DEPTH:
        raise ValueError("provider default state exceeds the depth limit")
    if _seen is None:
        _seen, _budget = set(), [0]
    _budget[0] += 1
    if _budget[0] > _RUNTIME_VALUE_LIMIT:
        raise ValueError("provider default state exceeds the item limit")
    kind = type(value)
    if (value is None or kind is bool or kind is int or kind is float
            or kind is str or kind is bytes):
        if ((kind is str or kind is bytes)
                and len(value) > _RUNTIME_VALUE_LIMIT):
            raise ValueError("provider default scalar exceeds the size limit")
        return None
    if kind is not tuple and kind is not frozenset:
        return (_closed_runtime_value(value)
                if kind is list or kind is dict or kind is set else None)
    marker = id(value)
    if marker in _seen:
        return None
    _seen.add(marker)
    for item in value:
        state = _mutable_runtime_state(item, _seen=_seen, _budget=_budget,
                                       _depth=_depth + 1)
        if state is not None:
            return _closed_runtime_value(value)
    return None


def _same_identity_tuple(actual, expected):
    return (actual is expected
            or (len(actual) == len(expected)
                and all(left is right for left, right in zip(actual, expected))))


@dataclass(frozen=True)
class _StaticProviderGuard:
    """Callback-free exact lookup for class providers, generic fallback otherwise."""

    owner: Any
    name: str
    expected: Any
    mros: tuple
    cells: tuple
    shadow_cells: tuple

    @classmethod
    def capture(cls, owner, name, expected, *, missing=False):
        missing = missing or expected is _MISSING
        if (inspect.getattr_static(owner, name, _MISSING) is not
                (_MISSING if missing else expected)):
            return None
        if missing:
            expected = _MISSING
        if not inspect.isclass(owner):
            return cls(owner, name, expected, (), (), ())
        mros, cells, shadow_cells = [], [], []
        mro_values, cell_seen = {}, set()
        def exact_mro(target):
            prior = mro_values.get(id(target))
            if prior is not None:
                return prior
            mro = _TYPE_MRO_GET(target)
            if type(mro) is not tuple:
                raise TypeError("provider owner has no exact MRO")
            mro_values[id(target)] = mro
            mros.append((target, type(target), mro))
            return mro
        shadow_targets = []
        for target in (owner, type(owner)):
            mro = exact_mro(target)
            for base in mro:
                namespace = _TYPE_DICT_GET(base)
                if not all(type(key) is str for key in namespace):
                    return None
                cell_key = (id(base), name)
                if cell_key not in cell_seen:
                    cell_seen.add(cell_key)
                    cells.append((base, namespace, name,
                                  namespace.get(name, _MISSING)))
                shadow_targets.append(type(base))
        for target in shadow_targets:
            for base in exact_mro(target):
                namespace = _TYPE_DICT_GET(base)
                if not all(type(key) is str for key in namespace):
                    return None
                shadow_key = (id(base), "__dict__")
                if shadow_key not in cell_seen:
                    cell_seen.add(shadow_key)
                    shadow_cells.append(
                        (base, namespace, "__dict__",
                         namespace.get("__dict__", _MISSING)))
        return cls(owner, name, expected, tuple(mros), tuple(cells),
                   tuple(shadow_cells))

    def matches(self, common=None):
        if not self.mros:
            return inspect.getattr_static(self.owner, self.name, _MISSING) is self.expected
        try:
            shared = _MISSING if common is None else common.get(id(self.owner), _MISSING)
            if shared is _MISSING:
                shared = (
                    all(type(target) is expected_type
                        and _same_identity_tuple(_TYPE_MRO_GET(target), expected_mro)
                    for target, expected_type, expected_mro in self.mros)
                    and all(namespace.get(name, _MISSING) is expected
                            for _base, namespace, name, expected in self.shadow_cells)
                )
                if common is not None:
                    common[id(self.owner)] = shared
            return (shared and all(namespace.get(name, _MISSING) is expected
                                   for _base, namespace, name, expected in self.cells))
        except Exception:
            return False


@dataclass(frozen=True)
class _StaticProviderSet:
    """One invocation's exact provider inventory, flattened for live checks."""

    mros: tuple
    cells: tuple
    generic: tuple

    @classmethod
    def from_guards(cls, guards):
        mros, cells, generic = {}, {}, {}
        for guard in guards:
            if not guard.mros:
                key = (id(guard.owner), guard.name)
                prior = generic.get(key)
                if prior is not None and prior.expected is not guard.expected:
                    return None
                generic[key] = guard
                continue
            for target, expected_type, expected_mro in guard.mros:
                prior = mros.get(id(target))
                if (prior is not None
                        and (prior[1] is not expected_type
                             or not _same_identity_tuple(prior[2], expected_mro))):
                    return None
                mros[id(target)] = (target, expected_type, expected_mro)
            for base, namespace, name, expected in (*guard.shadow_cells, *guard.cells):
                key = (id(base), name)
                prior = cells.get(key)
                if prior is not None and prior[2] is not expected:
                    return None
                cells[key] = (namespace, name, expected)
        return cls(tuple(mros.values()), tuple(cells.values()),
                   tuple(generic.values()))

    def matches(self):
        try:
            return (
                all(type(target) is expected_type
                    and _same_identity_tuple(_TYPE_MRO_GET(target), expected_mro)
                    for target, expected_type, expected_mro in self.mros)
                and all(namespace.get(name, _MISSING) is expected
                        for namespace, name, expected in self.cells)
                and all(guard.matches() for guard in self.generic)
            )
        except Exception:
            return False


def _canonical_cache_value(value, *, _seen=None, _budget=None):
    """Admit only installed runtime objects to a process-retained proof plan."""
    if _seen is None:
        _seen, _budget = set(), [0]
    _budget[0] += 1
    if _budget[0] > _RUNTIME_VALUE_LIMIT:
        return False
    kind = type(value)
    if value is None or any(kind is allowed for allowed in (bool, int, float, str, bytes)):
        return True
    if any(kind is allowed for allowed in (tuple, list, dict, set, frozenset)):
        if id(value) in _seen:
            return True
        _seen.add(id(value))
        values = tuple(value.items()) if kind is dict else tuple(value)
        return all(_canonical_cache_value(item, _seen=_seen, _budget=_budget)
                   for row in values for item in (row if kind is dict else (row,)))
    if inspect.ismodule(value):
        module = object.__getattribute__(value, "__name__")
    elif inspect.isclass(value):
        module = type.__getattribute__(value, "__module__")
    else:
        module = type.__getattribute__(kind, "__module__")
    root = (module or "").partition(".")[0]
    return root in ("build123d", "OCP", "builtins") or root in sys.stdlib_module_names


@dataclass(frozen=True)
class _CallableGuard:
    function: Any
    module: str
    namespace: Any
    code: Any
    defaults: Any
    defaults_state: Any
    kwdefaults: Any
    kwdefaults_state: Any
    wrapped: Any
    closure: Any
    closure_values: Any

    @classmethod
    def capture(cls, function):
        try:
            defaults = function.__defaults__
            kwdefaults = function.__kwdefaults__
            wrapped = getattr(function, "__wrapped__", _MISSING)
            closure = function.__closure__
            closure_values = tuple((cell, cell.cell_contents,
                                    _mutable_runtime_state(cell.cell_contents))
                                   for cell in closure or ())
            return cls(function, function.__module__, function.__globals__, function.__code__, defaults,
                       _mutable_runtime_state(defaults), kwdefaults,
                       _mutable_runtime_state(kwdefaults), wrapped, closure, closure_values)
        except Exception:
            return None

    def matches(self):
        try:
            function = self.function
            module = sys.modules.get(self.module)
            return (inspect.isfunction(function)
                    and module is not None and function.__globals__ is vars(module)
                    and function.__globals__ is self.namespace
                    and function.__code__ is self.code
                    and function.__defaults__ is self.defaults
                    and (self.defaults_state is None
                         or _closed_runtime_value(function.__defaults__) == self.defaults_state)
                    and function.__kwdefaults__ is self.kwdefaults
                    and (self.kwdefaults_state is None
                         or _closed_runtime_value(function.__kwdefaults__) == self.kwdefaults_state)
                    and getattr(function, "__wrapped__", _MISSING) is self.wrapped
                    and function.__closure__ is self.closure
                    and all(cell.cell_contents is value
                            and (state is None
                                 or _closed_runtime_value(cell.cell_contents) == state)
                            for cell, value, state in self.closure_values))
        except Exception:
            return False


@dataclass(frozen=True)
class _ProviderPlan:
    entry_providers: tuple
    guards: tuple
    globals: tuple
    cells: tuple
    callables: tuple
    provider_codes: tuple
    context_key: tuple
    workplane_current: Any
    loggers: tuple


def _provider_cache_key(bd, extra):
    """Return a bounded key only for canonical installed provider owners."""
    inventory = []
    for item in extra:
        if type(item) is not tuple or len(item) != 2:
            return None
        owner, name = item
        if type(name) is not str:
            return None
        module = ((getattr(owner, "__name__", "") or "") if inspect.ismodule(owner)
                  else (getattr(owner, "__module__", "") or ""))
        if module != "build123d" and not module.startswith("build123d."):
            return None
        inventory.append((owner, name))
    return bd, tuple(inventory)


def _entry_provider_token(provider):
    """Stable callable identity across our own descriptor restore cycle."""
    kind = type(provider)
    if kind is property:
        return ("property", provider.fget, provider.fset, provider.fdel)
    if kind is classmethod:
        return ("classmethod", provider.__func__)
    if kind is staticmethod:
        return ("staticmethod", provider.__func__)
    return ("value", provider)


def _same_entry_provider(left, right):
    return (len(left) == len(right) and left[0] == right[0]
            and all(actual is expected for actual, expected in zip(left[1:], right[1:])))


def _cached_provider_plan(key):
    if key is None:
        return None
    with _PROVIDER_PLAN_LOCK:
        plan = _PROVIDER_PLANS.get(key)
        if plan is not None:
            _PROVIDER_PLANS.move_to_end(key)
        return plan


def _remember_provider_plan(key, plan):
    if key is None:
        return
    with _PROVIDER_PLAN_LOCK:
        _PROVIDER_PLANS[key] = plan
        _PROVIDER_PLANS.move_to_end(key)
        while len(_PROVIDER_PLANS) > _PROVIDER_PLAN_LIMIT:
            _PROVIDER_PLANS.popitem(last=False)


def _provider_plans_live(plans):
    """Whether exact immutable plans retained by a frontend proof still exist."""
    with _PROVIDER_PLAN_LOCK:
        retained = tuple(_PROVIDER_PLANS.values())
        return bool(plans) and all(any(plan is value for value in retained) for plan in plans)


def _provider_plan_cacheable(globals_, callables):
    if not all(_canonical_cache_value(value) for _namespace, _name, value in globals_):
        return False
    for guard in callables:
        if (not _canonical_cache_value(guard.defaults)
                or not _canonical_cache_value(guard.kwdefaults)
                or any(not _canonical_cache_value(value)
                       for _cell, value, _state in guard.closure_values)):
            return False
    return True


@dataclass(frozen=True)
class WrapperRef:
    """A Python wrapper role, independent of its native allocation address."""
    role: str
    index: int = 0


@dataclass(frozen=True)
class WrapperRecord:
    native_slot: int
    kind: str
    label: str
    material: str | None
    color: tuple[float, ...] | None
    for_construction: bool
    topo_parent: WrapperRef | None


@dataclass(frozen=True)
class EffectLayout:
    input_count: int
    prior_slot: int | None
    tools: tuple[WrapperRecord, ...]
    created: tuple[WrapperRecord, ...]
    result: WrapperRef | None
    lasts: tuple[tuple[WrapperRef, ...], ...]
    slot_count: int


@dataclass(frozen=True)
class EffectBundle:
    handle: GeometryHandle
    layout: EffectLayout
    previous: EffectBundle | None
    inputs: tuple[GeometryHandle, ...]


@dataclass(frozen=True)
class EffectView:
    result: Any
    obj_before: Any
    to_combine: tuple[Any, ...]
    lasts: tuple[tuple[Any, ...], ...]


def _encode_layout(layout: EffectLayout) -> tuple:
    def ref(value):
        return None if value is None else (value.role, value.index)
    def record(value):
        return (value.native_slot, value.kind, value.label, value.material,
                value.color, value.for_construction, ref(value.topo_parent))
    return ("build123d.builder.effects", 1, layout.input_count, layout.prior_slot,
            tuple(map(record, layout.tools)), tuple(map(record, layout.created)),
            ref(layout.result), tuple(tuple(map(ref, row)) for row in layout.lasts),
            layout.slot_count)


def _decode_layout(value: Any, native: Any, *, expected_root: str | None = "Part") -> EffectLayout:
    """Decode a complete typed result; missing/corrupt metadata is an error."""
    def require(condition):
        if not condition:
            raise ValueError("invalid builder effect auxiliary layout")
    require(type(value) is tuple and len(value) == 9)
    tag, version, count, prior, tools, created, result, lasts, slot_count = value
    require(tag == "build123d.builder.effects" and type(version) is int and version == 1)
    require(type(count) is int and count > 0 and type(slot_count) is int and slot_count >= count)
    require(prior is None or (type(prior) is int and prior == 0 and count > 1))
    require(type(tools) is tuple and len(tools) == count - int(prior is not None))
    require(type(created) is tuple and bool(created))
    require(type(lasts) is tuple and len(lasts) == 4 and all(type(row) is tuple for row in lasts))
    def ref(item, *, optional=False):
        if optional and item is None:
            return None
        require(type(item) is tuple and len(item) == 2)
        role, index = item
        require(type(role) is str and type(index) is int and index >= 0)
        require((role == "prior" and prior == 0 and index == 0)
                or (role == "tool" and index < len(tools))
                or (role == "created" and index < len(created)))
        return WrapperRef(role, index)
    used = set()
    def record(item):
        require(type(item) is tuple and len(item) == 7)
        slot, kind, label, material, color, construction, parent = item
        require(type(slot) is int and count <= slot < slot_count and slot not in used)
        used.add(slot)
        require(kind in ("Vertex", "Edge", "Wire", "Face", "Shell", "Solid", "Compound", "Part", "Sketch"))
        require(type(label) is str and (material is None or type(material) is str))
        require(color is None or (type(color) is tuple and len(color) == 4
                                  and all(type(v) is float and 0 <= v <= 1 for v in color)))
        require(type(construction) is bool)
        return WrapperRecord(slot, kind, label, material, color, construction,
                             ref(parent, optional=True))
    layout = EffectLayout(count, prior, tuple(map(record, tools)), tuple(map(record, created)),
                          ref(result, optional=expected_root is None), tuple(tuple(map(ref, row)) for row in lasts), slot_count)
    require(len(used) == slot_count - count)
    require(layout.result is None if expected_root is None else
            layout.result.role == "created" and layout.created[layout.result.index].kind == expected_root)
    # Only parent chains are traversed while instantiating wrappers. Reject a
    # cycle before constructing anything from independently restored metadata.
    visiting, done = set(), set()
    def visit(item):
        if item is None or item.role == "prior" or item in done:
            return
        require(item not in visiting)
        visiting.add(item)
        rows = layout.tools if item.role == "tool" else layout.created
        visit(rows[item.index].topo_parent)
        visiting.remove(item)
        done.add(item)
    for role, rows in (("tool", layout.tools), ("created", layout.created)):
        for index in range(len(rows)):
            visit(WrapperRef(role, index))
    native_slots = _slots(native)
    require(len(native_slots) == slot_count)
    for row in (*layout.tools, *layout.created):
        expected = "COMPOUND" if row.kind in ("Part", "Sketch") else row.kind.upper()
        require(native_slots[row.native_slot].ShapeType().name == f"TopAbs_{expected}")
    return layout


def _pack(shapes):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    builder = BRep_Builder()
    root = TopoDS_Compound()
    builder.MakeCompound(root)
    # Distinct holders preserve ordinal slots even when two wrapper objects
    # refer to the exact same native shape. They share that native shape.
    for shape in shapes:
        holder = TopoDS_Compound()
        builder.MakeCompound(holder)
        builder.Add(holder, shape)
        builder.Add(root, holder)
    return root


def _children(shape):
    from OCP.TopoDS import TopoDS_Iterator
    iterator = TopoDS_Iterator(shape)
    result = []
    while iterator.More():
        result.append(iterator.Value())
        iterator.Next()
    return tuple(result)


def _slots(shape):
    values = []
    for holder in _children(shape):
        children = _children(holder)
        if holder.ShapeType().name != "TopAbs_COMPOUND" or len(children) != 1:
            raise ValueError("invalid builder effect native slot holder")
        values.append(children[0])
    return tuple(values)


def _single_solid(shape):
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    iterator = TopExp_Explorer(shape, TopAbs_SOLID)
    if not iterator.More():
        raise UnsupportedBuilderEffect("a stock primitive input must contain one solid")
    solid = iterator.Current()
    iterator.Next()
    if iterator.More():
        raise UnsupportedBuilderEffect("multiple located primitive instances need an alias proof")
    return solid


def _location(values):
    from OCP.gp import gp_Trsf
    from OCP.TopLoc import TopLoc_Location
    transform = gp_Trsf()
    transform.SetValues(*values[:12])
    return TopLoc_Location(transform)


class StockBuilderEffects:
    """Evaluate the stock solid effect function and retain its complete outputs.

    Each carrier references prior carriers and inputs through immutable native
    DAG edges. No historical geometry is copied or encoded at an effect hit.
    The document arena materializes the connected family on native escape.
    """

    def __init__(self, frontend=None, *, extra_providers=(), require_cached=False):
        import build123d as bd
        from .frontend import _stock_function, _stock_global
        extra_providers = tuple(extra_providers)
        self.bd = bd
        self.frontend = frontend
        # One immutable carrier view, local to this adapter. Projecting every
        # vertex/edge from a builder's lasts must not rescan all its slot holders
        # for each output. Native escape never uses this retained view.
        self._projection_carrier = None
        self._projection_slots = ()
        original = {} if frontend is None else {
            (owner, name): value for owner, name, value in frontend._originals}
        def original_provider(owner, name, current):
            if not inspect.isclass(owner):
                return original.get((owner, name), current)
            defining = next(base for base in owner.__mro__ if name in vars(base))
            return original.get((defining, name), current)
        declarations = (
            (bd.Builder, "_add_to_context", "build123d.build_common", "Builder._add_to_context"),
            (bd.Builder, "_shapes", "build123d.build_common", "Builder._shapes"),
            (bd.BuildPart, "_add_to_pending", "build123d.build_part", "BuildPart._add_to_pending"),
            (bd.Shape, "_bool_op", "build123d.topology.shape_core", "Shape._bool_op"),
            (bd.Shape, "clean", "build123d.topology.shape_core", "Shape.clean"),
            (bd.Shape, "cut", "build123d.topology.shape_core", "Shape.cut"),
            (bd.Shape, "fuse", "build123d.topology.shape_core", "Shape.fuse"),
            (bd.Shape, "copy_attributes_to", "build123d.topology.shape_core", "Shape.copy_attributes_to"),
            (bd.Shape, "__init__", "build123d.topology.shape_core", "Shape.__init__"),
            (bd.Solid, "__init__", "build123d.topology.three_d", "Solid.__init__"),
            (bd.Compound, "__init__", "build123d.topology.composite", "Compound.__init__"),
            (bd.Vertex, "__init__", "build123d.topology.zero_d", "Vertex.__init__"),
            (bd.Edge, "__init__", "build123d.topology.one_d", "Edge.__init__"),
            (bd.Face, "__init__", "build123d.topology.two_d", "Face.__init__"),
            *((bd.Shape, kind, "build123d.topology.shape_core", f"Shape.{kind}")
              for kind in ("vertices", "edges", "faces", "solids")),
        )
        self._guards = []
        self._globals = []
        self._cells = []
        self._callable_guards = []
        self._callable_ids = set()
        self._provider_codes = {}
        self._binding_guards = None
        self._global_bindings = ()
        self._cell_bindings = ()
        self._canonical_plan = None
        self._stock = True
        provider_functions = []
        entry_providers = []
        for owner, name, module, qualified in declarations:
            current = inspect.getattr_static(owner, name)
            provider = original_provider(owner, name, current)
            entry_providers.append(_entry_provider_token(provider))
            self._stock &= _stock_function(provider, module, qualified)
            self._guards.append((owner, name, current))
            if inspect.isfunction(provider):
                provider_functions.append(provider)
                self._globals.extend((provider.__globals__, key, provider.__globals__[key])
                                     for key in provider.__code__.co_names if key in provider.__globals__)
        # These are called transitively by the stock body. A user replacing a
        # selector, equality method, property or native kernel method must not
        # inherit the private adapter's trusted scope, even on a warm hit.
        extra = (
            (bd.BuildPart, "_obj"), (bd.BuildPart, "part"),
            *((bd.Shape, name) for name in ("__hash__", "__eq__", "is_same", "entities",
                                           "get_shape_list", "make_composite", "wrapped")),
            (bd.Compound, "cast"), (bd.Solid, "cast"),
            *((bd.ShapeList, name) for name in ("filter_by", "__init__", "__iter__", "__len__", "__getitem__")),
            *((owner, name) for owner in (bd.Part, bd.Compound, bd.Solid, bd.Vertex, bd.Edge, bd.Face)
              for name in ("__init__", "__getattribute__", "__setattr__", "__hash__", "__eq__",
                           "is_same", "entities", "get_shape_list", "wrapped", "cast",
                           "cut", "fuse", "clean", "_bool_op", "copy_attributes_to",
                           "vertices", "edges", "faces", "solids")),
            (bd.BuildPart, "__getattribute__"), (bd.BuildPart, "__setattr__"),
            *((bd.WorkplaneList, name) for name in ("_get_context", "__init__", "__enter__",
                                                   "__exit__", "_convert_to_planes",
                                                   "__getattribute__", "__setattr__")),
            *extra_providers,
        )
        for owner, name in extra:
            current = inspect.getattr_static(owner, name)
            provider = original_provider(owner, name, current)
            entry_providers.append(_entry_provider_token(provider))
            self._guards.append((owner, name, current))
            provider_functions.extend(
                fn for fn in ((provider.fget, provider.fset) if isinstance(provider, property)
                              else (provider.__func__,) if isinstance(provider, (classmethod, staticmethod))
                              else (provider,)) if fn is not None)
        # Adapter code resolves these classes and enums through build123d's
        # module namespace. Pin those bindings independently of descriptors on
        # the classes themselves so an alias replacement always deopts.
        bd_namespace = vars(bd)
        self._globals.extend((bd_namespace, name, bd_namespace[name])
                             for name in _BD_PROVIDER_NAMES if name in bd_namespace)
        dynamic_guards = tuple(self._guards)
        initial_globals = tuple(self._globals)
        entry_stock = self._stock
        cache_key = _provider_cache_key(bd, extra_providers)
        plan = _cached_provider_plan(cache_key)
        if plan is not None and len(plan.entry_providers) == len(entry_providers):
            self._canonical_plan = plan
            self._guards.extend(plan.guards)
            self._globals = list(plan.globals)
            self._cells = list(plan.cells)
            self._callable_guards = list(plan.callables)
            self._callable_ids = {id(value.function) for value in plan.callables}
            self._provider_codes = dict(plan.provider_codes)
            self._context_key = plan.context_key
            self._workplane_current = plan.workplane_current
            self._loggers = plan.loggers
            self._adopt_frontend_interceptors()
            self._stock &= all(_same_entry_provider(actual, expected) for actual, expected in
                               zip(entry_providers, plan.entry_providers))
            # A mismatch deopts this execution against the canonical plan. Do
            # not relearn a plan from a possibly authored mutation. A replaced
            # build123d module gets a distinct cache key; an in-place reload is
            # conservatively ineligible for the rest of this owner process.
            if not self._stock or not self._provider_bindings_match():
                self._stock = False
        else:
            plan = None

        if plan is None and require_cached:
            # This path can run after authored Python has begun.  Dynamic entry
            # bindings are inspected only to reject the old proof; never build a
            # new transitive inventory from process state that author code could
            # have changed.
            self._guards = list(dynamic_guards)
            self._globals = list(initial_globals)
            self._cells = []
            self._callable_guards = []
            self._callable_ids = set()
            self._provider_codes = {}
            self._context_key = ()
            self._workplane_current = None
            self._loggers = ()
            self._stock = False
        elif plan is None:
            self._guards = list(dynamic_guards)
            self._globals = list(initial_globals)
            self._cells = []
            self._callable_guards = []
            self._callable_ids = set()
            self._provider_codes = {}
            self._stock = entry_stock
            # These fields are ordinary per-instance state in the audited
            # build123d runtime. An authored descriptor added to any concrete
            # wrapper or builder could otherwise run from our trusted reads and
            # writes. Preserve absence as part of the reusable provider plan.
            field_owners = (
                bd.Shape, bd.Vertex, bd.Edge, bd.Wire, bd.Face, bd.Shell,
                bd.Solid, bd.Compound, bd.Part, bd.Sketch,
            )
            builder_owners = (bd.BuildPart, bd.BuildSketch)
            field_guards = tuple(
                (owner, name, inspect.getattr_static(owner, name, _MISSING))
                for owner, names in (
                    *((owner, _WRAPPER_FIELD_NAMES) for owner in field_owners),
                    *((owner, _BUILDER_FIELD_NAMES) for owner in builder_owners),
                )
                for name in names
            )
            self._stock &= all(value is _MISSING for _owner, _name, value in field_guards)
            self._guards.extend(field_guards)
            seen, native_names = set(), set()
            while provider_functions:
                fn = provider_functions.pop()
                if id(fn) in seen:
                    continue
                seen.add(id(fn))
                if any(fn is builtin for builtin in (
                        object.__new__, object.__getattribute__, object.__setattr__,
                        list.__init__, list.__iter__, list.__len__)):
                    continue
                self._stock &= self._stock_wrapped(fn)
                if not inspect.isfunction(fn):
                    continue
                native_names.update(fn.__code__.co_names)
                for name in fn.__code__.co_names:
                    if name not in fn.__globals__:
                        continue
                    value = fn.__globals__[name]
                    self._globals.append((fn.__globals__, name, value))
                    if (inspect.isfunction(value)
                            and (value.__module__ or "").startswith("build123d.")):
                        provider_functions.append(value)
            native_providers = {value for _, _, value in self._globals
                                if inspect.isclass(value)
                                and (value.__module__ or "").startswith("OCP.")
                                and not issubclass(value, BaseException)}
            for owner in native_providers:
                self._stock &= type(owner).__module__ == "pybind11_builtins"
                for name in {"__init__", *native_names}:
                    member = inspect.getattr_static(owner, name, None)
                    if member is None or not callable(member):
                        continue
                    function = member.__func__ if isinstance(member, staticmethod) else member
                    native_method = (type(function).__name__ in
                                     ("instancemethod", "builtin_function_or_method")
                                     and (getattr(function, "__module__", "") or "").startswith("OCP."))
                    defining = next((base for base in owner.__mro__ if name in vars(base)), None)
                    native_shared_new = (
                        name == "__new__" and defining is not None
                        and defining.__module__ == "pybind11_builtins"
                        and defining.__name__ == "pybind11_object"
                        and type(function).__name__ == "builtin_function_or_method"
                        and function is inspect.getattr_static(defining, "__new__")
                        and getattr(function, "__self__", None) is defining
                    )
                    # Abstract OCCT classes expose a native slot descriptor for
                    # __init__, even though constructing them is not permitted.
                    native_slot = (type(function).__name__ == "wrapper_descriptor"
                                   and type(function.__objclass__).__module__ == "pybind11_builtins"
                                   and function.__objclass__.__module__.startswith("OCP."))
                    self._stock &= native_method or native_slot or native_shared_new
                    self._guards.append((owner, name, member))
            # Shared numeric tolerances are serialization inputs too. Capture
            # their current values in the evaluation key, and pin them during it.
            self._context_key = tuple(sorted({(namespace.get("__name__"), name, value)
                                             for namespace, name, value in self._globals
                                             if type(value) in (bool, int, float, str)}))
            self._stock &= (bd.BuildPart._tag == "BuildPart" and bd.BuildPart._shape is bd.Solid
                            and bd.BuildPart._sub_class is bd.Part and bd.Part.order == 4)
            self._guards.extend((owner, name, inspect.getattr_static(owner, name))
                                for owner, names in ((bd.BuildPart, ("_tag", "_shape", "_sub_class")),
                                                     (bd.Part, ("order",)), (bd.Solid, ("order",)))
                                for name in names)
            import contextvars
            self._workplane_current = inspect.getattr_static(bd.WorkplaneList, "_current")
            self._stock &= type(self._workplane_current) is contextvars.ContextVar
            self._guards.append((bd.WorkplaneList, "_current", self._workplane_current))
            for _, name, value in self._globals:
                admitted = _stock_global(name, value)
                if admitted and inspect.isfunction(value):
                    admitted = self._remember_callable(value)
                if not admitted:
                    admitted = self._stock_wrapped(value)
                self._stock &= admitted
            import logging
            self._loggers = tuple({value for _, name, value in self._globals if name == "logger"})
            for logger in self._loggers:
                self._stock &= type(logger) is logging.Logger
                for name in ("info", "debug", "isEnabledFor"):
                    provider = inspect.getattr_static(logger, name)
                    self._stock &= _stock_function(provider, "logging", f"Logger.{name}")
                    if inspect.isfunction(provider):
                        self._stock &= self._remember_callable(provider)
                    self._guards.append((logger, name, provider))
            self._stock &= self._provider_bindings_match()
            if self._stock and _provider_plan_cacheable(self._globals,
                                                        self._callable_guards):
                static_guards = tuple(self._guards[len(dynamic_guards):])
                plan = _ProviderPlan(
                    tuple(entry_providers), static_guards, tuple(self._globals),
                    tuple(self._cells), tuple(self._callable_guards),
                    tuple((name, frozenset(codes)) for name, codes in self._provider_codes.items()),
                    self._context_key, self._workplane_current, self._loggers,
                )
                _remember_provider_plan(cache_key, plan)
                self._canonical_plan = plan
        self._add = original.get((bd.Builder, "_add_to_context"), bd.Builder._add_to_context)
        self._bool = original.get((bd.Shape, "_bool_op"), bd.Shape._bool_op)
        self._wrapped = original.get((bd.Shape, "wrapped"), inspect.getattr_static(bd.Shape, "wrapped"))

    def _provider_bindings_match(self):
        if self._binding_guards is None:
            self._compile_provider_bindings()
        return (self._binding_guards is not None
                and self._binding_guards.matches()
                and all(namespace.get(name) is value
                        for namespace, name, value in self._global_bindings)
                and all(cell.cell_contents is value for cell, value in self._cell_bindings)
                and all(guard.matches() for guard in self._callable_guards))

    def _compile_provider_bindings(self):
        """Compile exact live checks; never retain a successful check result."""
        providers = {}
        compiled = []
        for owner, name, expected in self._guards:
            key = (id(owner), name)
            prior = providers.get(key, _MISSING)
            if prior is not _MISSING:
                if prior is not expected:
                    self._binding_guards = None
                    self._stock = False
                    return
                continue
            providers[key] = expected
            guard = _StaticProviderGuard.capture(owner, name, expected)
            if guard is None:
                self._binding_guards = None
                self._stock = False
                return
            compiled.append(guard)
        globals_ = {}
        for namespace, name, expected in self._globals:
            key = (id(namespace), name)
            prior = globals_.get(key, _MISSING)
            if prior is not _MISSING and prior is not expected:
                self._binding_guards = None
                self._stock = False
                return
            globals_[key] = expected
        cells = {}
        for cell, expected in self._cells:
            prior = cells.get(id(cell), _MISSING)
            if prior is not _MISSING and prior is not expected:
                self._binding_guards = None
                self._stock = False
                return
            cells[id(cell)] = expected
        self._binding_guards = _StaticProviderSet.from_guards(compiled)
        if self._binding_guards is None:
            self._stock = False
            return
        seen = set()
        self._global_bindings = tuple(
            row for row in self._globals
            if (id(row[0]), row[1]) not in seen
            and not seen.add((id(row[0]), row[1]))
        )
        seen = set()
        self._cell_bindings = tuple(
            row for row in self._cells
            if id(row[0]) not in seen and not seen.add(id(row[0]))
        )

    def _adopt_frontend_interceptors(self):
        """Translate a cold plan to exact closures installed before this replay.

        The frontend records each successful patch before authored code begins.
        A later authored replacement never equals that recorded closure and is
        therefore left to fail the normal identity guard.
        """
        if self.frontend is None:
            return
        self._binding_guards = None
        for patched_owner, patched_name, original, replacement in self.frontend._installed:
            self._guards = [
                (owner, name, replacement)
                if (name == patched_name and expected is original
                    and inspect.getattr_static(owner, name, _MISSING) is replacement)
                else (owner, name, expected)
                for owner, name, expected in self._guards
            ]
            if not inspect.isclass(patched_owner):
                namespace = vars(patched_owner)
                if namespace.get(patched_name) is replacement:
                    self._globals = [
                        (values, name, replacement)
                        if values is namespace and name == patched_name and expected is original
                        else (values, name, expected)
                        for values, name, expected in self._globals
                    ]

    def finalize_frontend_guards(self):
        """Freeze installed internal interceptors after all frontend patches."""
        self._binding_guards = None
        for owner, name, expected in self._guards:
            provider = inspect.getattr_static(owner, name, _MISSING)
            if provider is not expected:
                self._stock = False
                continue
            kind = type(provider)
            functions = ((provider.fget, provider.fset, provider.fdel)
                         if kind is property else
                         (provider.__func__,) if kind in (classmethod, staticmethod) else
                         (provider,))
            for function in functions:
                if (inspect.isfunction(function)
                        and (function.__module__ or "").startswith("cadgen._document.")):
                    self._stock &= self._remember_callable(function)
        self._stock &= self._provider_bindings_match()

    def providers_match(self):
        return (self._stock and type(inspect.getattr_static(self.bd.SkipClean, "clean")) is bool
                and self._quiet_loggers() and self._workplanes_match()
                and self._provider_bindings_match())

    def _workplanes_match(self):
        if inspect.getattr_static(self.bd.WorkplaneList, "workplanes", None) is not None:
            return False
        context = self._workplane_current.get(None)
        if context is None:
            return True
        if type(context) is not self.bd.WorkplaneList:
            return False
        workplanes = object.__getattribute__(context, "__dict__").get("workplanes")
        return (type(workplanes) in (list, tuple)
                and all(type(plane) is self.bd.Plane for plane in workplanes))

    def _quiet_loggers(self):
        # Stock effects emit DEBUG/INFO records. If those records can reach an
        # authored handler, execute the stock body ordinarily on every action.
        import logging
        for logger in self._loggers:
            current = logger
            while current is not None:
                if type(current) not in (logging.Logger, logging.RootLogger):
                    return False
                raw = object.__getattribute__(current, "__dict__")
                level = raw.get("level")
                if type(level) is not int:
                    return False
                if level:
                    if level <= logging.INFO:
                        return False
                    break
                current = raw.get("parent")
            else:
                return False
        return True

    def _stock_wrapped(self, value):
        """Admit build123d's own context decorators, not author-decorated hooks."""
        from importlib.machinery import SourceFileLoader
        if (not inspect.isfunction(value)
                or not (value.__module__ or "").startswith("build123d.")):
            return False
        module = sys.modules[value.__module__]
        if value.__globals__ is not vars(module) or type(module.__loader__) is not SourceFileLoader:
            return False
        if value.__module__ not in self._provider_codes:
            pending = [module.__loader__.get_code(value.__module__)]
            codes = set()
            while pending:
                code = pending.pop()
                if inspect.iscode(code):
                    codes.add(code)
                    pending.extend(item for item in code.co_consts if inspect.iscode(item))
            self._provider_codes[value.__module__] = codes
        if value.__code__ not in self._provider_codes[value.__module__]:
            return False
        if not self._remember_callable(value):
            return False
        wrapped = getattr(value, "__wrapped__", None)
        if wrapped is not None and not self._stock_wrapped(wrapped):
            return False
        for cell in value.__closure__ or ():
            captured = cell.cell_contents
            if inspect.isfunction(captured) and not self._stock_wrapped(captured):
                return False
            self._cells.append((cell, captured))
        return True

    def _remember_callable(self, value):
        if id(value) in self._callable_ids:
            return True
        guard = _CallableGuard.capture(value)
        if guard is None:
            return False
        self._callable_ids.add(id(value))
        self._callable_guards.append(guard)
        return True

    def _execute(self, fn, *args):
        return (fn(*args) if self.frontend is None
                else self.frontend._inside_compute(fn, *args))

    def aligned_input(self, tx: RevisionTransaction, seed: GeometryHandle,
                      transform: tuple[float, ...]) -> GeometryHandle:
        """Instantiate one private primitive, with placement intrinsic to a root.

        Only this new input is copied. Effects can subsequently borrow that
        immutable root without flattening or copying the preceding builder DAG.
        """
        def compute(inputs, arena):
            solid = _single_solid(inputs[0]).Located(_location(transform))
            return NativeResult(_pack((solid,)))
        return tx.evaluate(OperatorSpec("build123d.builder.input", "1"),
                           transform, (seed,), compute)

    def evaluate(self, tx: RevisionTransaction, previous: EffectBundle | None,
                 inputs: tuple[GeometryHandle, ...], *, mode: Any,
                 clean: bool = True) -> EffectBundle:
        bd = self.bd
        if not self.providers_match():
            raise UnsupportedBuilderEffect("stock builder providers changed")
        if (type(mode) is not bd.Mode or mode not in (bd.Mode.ADD, bd.Mode.SUBTRACT, bd.Mode.REPLACE)
                or type(clean) is not bool or not inputs):
            raise UnsupportedBuilderEffect("the bounded effect accepts solid ADD/SUBTRACT/REPLACE")
        if previous is None and mode is bd.Mode.SUBTRACT:
            raise UnsupportedBuilderEffect("a failing first subtraction executes ordinarily")
        if tx.escape_arena.active:
            raise UnsupportedBuilderEffect("input-dependent reuse after native escape is not established")
        arguments = (() if previous is None else (previous.handle,)) + tuple(inputs)
        # Equal immutable prototypes may represent independent authored input
        # allocations. They must not collapse to one native tool in this scope.
        natives = tuple(tx._validate_handle(handle).shape for handle in inputs)
        all_solids = tuple(_single_solid(native) for native in natives)
        if any(a.IsPartner(b) for index, a in enumerate(all_solids)
               for b in all_solids[index + 1:]):
            raise UnsupportedBuilderEffect("independent coincident inputs need private execution")
        if previous is not None:
            prior = topology_map(tx._validate_handle(previous.handle).shape)
            if any(prior.Contains(solid) for solid in all_solids):
                raise UnsupportedBuilderEffect("a repeated native prototype needs allocation separation")
        skip_clean = inspect.getattr_static(bd.SkipClean, "clean")
        def compute(native_inputs, arena):
            shape, layout = self._execute(self._capture, previous, native_inputs, mode, clean,
                                          skip_clean)
            return NativeResult(shape, auxiliary=_encode_layout(layout))
        handle = tx.evaluate(
            OperatorSpec("build123d.builder.solid-effects", "1", Mutation.READ_ONLY),
            (mode.name, clean, skip_clean, self._context_key), arguments, compute)
        prototype = tx.document._get(handle)
        decoded_key = (handle.prototype_id, "builder-effects-decoded-layout")
        layout = tx.document._derivations.get(decoded_key)
        if layout is None:
            layout = _decode_layout(prototype.auxiliary, prototype.shape)
            tx.document._derivations[decoded_key] = layout
        return EffectBundle(handle, layout, previous, tuple(inputs))

    def project(self, tx, bundle, ref):
        if ref.role == "prior":
            return self.project(tx, bundle.previous, bundle.previous.layout.result)
        record = (bundle.layout.tools if ref.role == "tool" else bundle.layout.created)[ref.index]
        def compute(inputs, arena):
            carrier = inputs[0]
            if arena.active:
                self._projection_carrier, self._projection_slots = None, ()
                slots = _slots(carrier)
            else:
                if carrier is not self._projection_carrier:
                    slots = _slots(carrier)
                    self._projection_carrier, self._projection_slots = carrier, slots
                slots = self._projection_slots
            return NativeResult(slots[record.native_slot])
        return tx.evaluate(
            OperatorSpec("build123d.builder.effect-output", "1", Mutation.READ_ONLY),
            record.native_slot, (bundle.handle,), compute)

    def _capture(self, previous, native_inputs, mode, clean, skip_clean, *,
                 builder_type=None, tool_factory=None, include_pending=False):
        bd = self.bd
        prior_count = int(previous is not None)
        slots = list(native_inputs)  # shared DAG edges, not expanded prior slots
        before = None if previous is None else self._root_wrapper(previous, native_inputs[0])
        tools = ([bd.Solid(bd.Solid.cast(_single_solid(shape)).wrapped)
                  for shape in native_inputs[prior_count:]] if tool_factory is None else
                 [tool_factory(shape) for shape in native_inputs[prior_count:]])
        builder = object.__new__(bd.BuildPart if builder_type is None else builder_type)
        builder._obj = before
        builder.lasts = {kind: [] for kind in (bd.Vertex, bd.Edge, bd.Face, bd.Solid)}
        builder.pending_edges = []
        builder.pending_faces = []
        builder.pending_face_planes = []
        builder.pending_planes = []
        # No lifecycle or source callback runs in this native adapter. Its
        # providers are checked before it starts; normal frontend callbacks
        # never inherit this scope.
        original_bool = bd.Shape._bool_op
        def readonly(shape, args, cutters, operation):
            operation.SetNonDestructive(True)
            return self._bool(shape, args, cutters, operation)
        old_clean = bd.SkipClean.clean
        bd.SkipClean.clean = skip_clean
        bd.Shape._bool_op = readonly
        context = (nullcontext() if bd.WorkplaneList._get_context() is not None
                   else bd.WorkplaneList(bd.Plane.XY))
        try:
            with context:
                self._add(builder, *tools, mode=mode, clean=clean)
        finally:
            bd.Shape._bool_op = original_bool
            bd.SkipClean.clean = old_clean
        native, layout, extras = self._record(native_inputs, before, tools, builder._obj,
                                              builder.lasts, builder.pending_faces if include_pending else ())
        return (native, layout, extras) if include_pending else (native, layout)

    def _record(self, native_inputs, before, tools, result, lasts, extra_outputs=()):
        bd = self.bd
        slots = list(native_inputs)
        created = []
        refs = {id(tool): WrapperRef("tool", index) for index, tool in enumerate(tools)}
        if before is not None:
            refs[id(before)] = WrapperRef("prior")
        def record(shape):
            raw = vars(shape)
            if raw.get("joints") or raw.get("_NodeMixin__children") or raw.get("_NodeMixin__parent"):
                raise UnsupportedBuilderEffect("native effect wrapper has unsupported hierarchy or joints")
            parent = raw.get("topo_parent")
            parent_ref = None if parent is None else reference(parent)
            color = raw.get("_color")
            native_slot = len(slots)
            slots.append(self._wrapped.fget(shape))
            return WrapperRecord(native_slot, type(shape).__name__, shape.label,
                                 raw.get("material"), None if color is None else tuple(color),
                                 bool(shape.for_construction), parent_ref)
        def reference(shape):
            existing = refs.get(id(shape))
            if existing is not None:
                return existing
            ref = WrapperRef("created", len(created))
            refs[id(shape)] = ref
            created.append(None)
            created[ref.index] = record(shape)
            return ref
        result_ref = None if result is None else reference(result)
        last_refs = tuple(tuple(reference(shape) for shape in lasts[kind])
                          for kind in (bd.Vertex, bd.Edge, bd.Face, bd.Solid))
        extras = tuple(reference(shape) for shape in extra_outputs)
        tool_records = tuple(record(tool) for tool in tools)
        layout = EffectLayout(len(native_inputs), 0 if before is not None else None,
                              tool_records, tuple(created), result_ref, last_refs, len(slots))
        return _pack(slots), layout, extras

    def _instantiate(self, record, native):
        bd = self.bd
        cls = getattr(bd, record.kind)
        shape = cls(bd.Part.cast(native).wrapped)
        shape.label = record.label
        if record.material is not None:
            shape.material = record.material
        shape._color = None if record.color is None else bd.Color(*record.color)
        shape.for_construction = record.for_construction
        return shape

    def _root_wrapper(self, bundle, native):
        # The stock final cast always creates a fresh Part wrapper. Resolving
        # it does not rebuild any earlier effect lists or wrapper histories.
        ref = bundle.layout.result
        if ref.role != "created":
            raise UnsupportedBuilderEffect("stock result wrapper has an unexpected role")
        record = bundle.layout.created[ref.index]
        return self._instantiate(record, _slots(native)[record.native_slot])

    def _view(self, bundle: EffectBundle, native) -> EffectView:
        bd = self.bd
        slots = _slots(native)
        layout = bundle.layout
        before = (None if bundle.previous is None else
                  self._root_wrapper(bundle.previous, slots[layout.prior_slot]))
        made = {}
        def wrapper(ref):
            if ref.role == "prior":
                return before
            if ref in made:
                return made[ref]
            record = (layout.tools if ref.role == "tool" else layout.created)[ref.index]
            shape = self._instantiate(record, slots[record.native_slot])
            made[ref] = shape
            shape.topo_parent = None if record.topo_parent is None else wrapper(record.topo_parent)
            return shape
        return EffectView(None if layout.result is None else wrapper(layout.result), before,
                          tuple(wrapper(WrapperRef("tool", i)) for i in range(len(layout.tools))),
                          tuple(tuple(wrapper(ref) for ref in row) for row in layout.lasts))

    def materialize(self, tx: RevisionTransaction, bundle: EffectBundle) -> EffectView:
        """One owned native family supplies all wrappers, including input aliases."""
        native = tx.escape_arena.native(bundle.handle)
        return self._execute(self._view, bundle, native)


@dataclass
class _Constructor:
    shape: Any
    builder: Any
    seed: GeometryHandle | None = None
    native_seed: Any = None
    source_native: Any = None
    output: GeometryHandle | None = None
    pending: list[tuple[Any, GeometryHandle]] = field(default_factory=list)
    wrappers: list[Any] = field(default_factory=list)


@dataclass
class _BuilderState:
    bundle: EffectBundle
    part: Any
    eligible: bool = True


class BuilderEffectsFrontend:
    """Constructor provenance and ordinary Python wrapper/effect publication."""

    def __init__(self, frontend, *, deferred=False):
        self.frontend = frontend
        self.stock = None
        self.current = None
        self.builders = {}
        self.owners = {}
        bd = frontend._bd
        originals = {(owner, name): value for owner, name, value in frontend._originals}
        original = originals.get((bd.Builder, "_add_to_context"), bd.Builder._add_to_context)
        self._add_original = original
        def add(builder, *objects, **kwargs):
            sketch = getattr(frontend, "_sketch_effects", None)
            if sketch is not None and sketch.stock is not None and sketch.add(builder, objects, kwargs):
                return None
            if self.stock is None:
                self.activate(require_cached=True)
            if self.stock is not None and self._add(builder, objects, kwargs):
                return None
            if self.stock is not None:
                self.revoke(builder)
                if sketch is not None and sketch.stock is not None:
                    sketch.revoke(builder)
            return original(builder, *objects, **kwargs)
        frontend._patch(bd.Builder, "_add_to_context", add)
        self._installed_add = add

    def activate(self, *, require_cached=True, finalize=True):
        if self.stock is not None:
            return self
        self.stock = StockBuilderEffects(self.frontend, require_cached=require_cached)
        add = self._installed_add
        self.stock._guards = [(owner, name, add if owner is self.frontend._bd.Builder
                               and name == "_add_to_context" else value)
                              for owner, name, value in self.stock._guards]
        if finalize:
            self.frontend._finalize_effect_guards()
        return self

    def finalize_guards(self):
        """Freeze the final solid and sketch interceptor implementations."""
        audits = (self.stock, self.frontend._sketch_effects.stock)
        for audit in audits:
            if audit is not None:
                audit.finalize_frontend_guards()

    def begin(self, kind, shape, builder, dimensions, kwargs):
        if self.stock is None:
            self.activate(require_cached=True)
        f = self.frontend
        previous = self.current
        align = kwargs.get("align", (f._bd.Align.CENTER,) * 3)
        mode = kwargs.get("mode", f._bd.Mode.ADD)
        eligible = (type(builder) is f._bd.BuildPart
                    and f._closed_primitive(kind, shape, dimensions,
                                           kwargs.get("rotation", (0, 0, 0)), align, mode)
                    and self.stock.providers_match())
        self.current = _Constructor(shape, builder) if eligible else None
        return previous, self.current

    def seed(self, shape, handle):
        frame = self.current
        if frame is not None:
            frame.seed = handle
            frame.native_seed = self.frontend._native_originals["wrapped"].fget(shape)

    def capture(self, shape):
        if self.stock is None:
            return False
        frame = self.current
        if frame is None or frame.output is None or frame.source_native is None:
            return False
        native = self.frontend._native_originals["wrapped"].fget(shape)
        try:
            matches = _single_solid(native).IsSame(frame.source_native)
        except UnsupportedBuilderEffect:
            matches = False
        if matches:
            frame.wrappers.append(shape)
        return matches

    def finish(self, token, succeeded):
        previous, frame = token
        self.current = previous
        if frame is None:
            return
        if not succeeded or frame.output is None:
            self.revoke(frame.builder)
            return
        for shape, handle in frame.pending:
            self._manage(shape, handle, frame.builder)
        for shape in (*frame.wrappers, frame.shape):
            self._manage(shape, frame.output, frame.builder)

    def revoke(self, builder):
        if self.stock is None:
            return
        state = self.builders.get(id(builder))
        if state is not None:
            state.eligible = False

    def revoke_shape(self, shape):
        if self.stock is None:
            return
        builder = self.owners.get(id(shape))
        if builder is not None:
            self.revoke(builder)

    def _manage(self, shape, handle, builder):
        f = self.frontend
        raw = dict(object.__getattribute__(shape, "__dict__"))
        f._init_empty(shape, f._logical("builder-view"), handle)
        state = object.__getattribute__(shape, "_cadgen_document_state")
        attributes = object.__getattribute__(shape, "__dict__")
        attributes.clear()
        attributes.update(raw)
        attributes["_wrapped"] = None
        attributes["_cadgen_document_state"] = state
        self.owners[id(shape)] = builder

    def _part_unchanged(self, state):
        from .frontend import _state
        f = self.frontend
        shape = state.part
        record = state.bundle.layout.created[state.bundle.layout.result.index]
        managed = _state(shape)
        raw = object.__getattribute__(shape, "__dict__")
        color = raw.get("_color")
        return (managed is not None and not managed.private
                and f._can_copy_managed_wrapper(shape)
                and raw.get("label") == record.label
                and raw.get("material") == record.material
                and raw.get("for_construction") == record.for_construction
                and (None if color is None else tuple(color)) == record.color)

    def _add(self, builder, objects, kwargs):
        from .frontend import _matrix
        f, frame, bd = self.frontend, self.current, self.frontend._bd
        tx = f.transaction
        if (f._compute_depth or frame is None or frame.builder is not builder or frame.seed is None
                or type(builder) is not bd.BuildPart or len(objects) != 1
                or type(objects[0]) is not bd.Solid or tx.escape_arena.active
                or not self.stock.providers_match()
                or not f._can_defer_hierarchy(frame.shape, ())):
            return False
        if set(kwargs) - {"mode", "clean", "faces_to_pending"}:
            return False
        mode, clean = kwargs.get("mode", bd.Mode.ADD), kwargs.get("clean", True)
        if (type(mode) is not bd.Mode or mode not in (bd.Mode.ADD, bd.Mode.SUBTRACT, bd.Mode.REPLACE)
                or type(clean) is not bool or kwargs.get("faces_to_pending", True) is not True):
            return False
        # Instance hooks must run ordinarily; no ambient builder context can
        # grant a callback the stock effect adapter's native privileges.
        if any(name in vars(builder) for name in ("_add_to_context", "_add_to_pending", "_shapes", "_obj")):
            return False
        if (builder._tag != "BuildPart" or builder._shape is not bd.Solid
                or builder._sub_class is not bd.Part or type(builder.lasts) is not dict):
            return False
        previous = self.builders.get(id(builder))
        if previous is not None:
            if not previous.eligible or builder._part is not previous.part or not self._part_unchanged(previous):
                return False
        elif builder._part is not None or mode is bd.Mode.SUBTRACT:
            return False
        source = objects[0]
        raw = object.__getattribute__(source, "__dict__")
        if (raw.get("joints") or raw.get("_NodeMixin__children") or raw.get("_NodeMixin__parent")
                or raw.get("label") or raw.get("_color") is not None or raw.get("material")):
            return False
        native = f._native_originals["wrapped"].fget(source)
        if not native.IsPartner(frame.native_seed):
            return False
        shape_input = self.stock.aligned_input(tx, frame.seed, _matrix(bd.Location(native.Location())))
        # Admission is complete before native computation begins. An error
        # after this point is propagated; no authored action is replayed.
        try:
            if previous is not None and topology_map(tx.document._get(previous.bundle.handle).shape).Contains(
                    _single_solid(tx.document._get(shape_input).shape)):
                return False
        except UnsupportedBuilderEffect:
            return False
        return self._publish(builder, objects, shape_input, mode, clean, previous, frame, native)

    def _publish(self, builder, objects, shape_input, mode, clean, previous, frame, native):
        f, bd = self.frontend, self.frontend._bd
        tx = f.transaction
        source = objects[0]
        builder.obj_before = builder._part
        builder.to_combine = list(objects)
        bundle = self.stock.evaluate(tx, None if previous is None else previous.bundle,
                                     (shape_input,), mode=mode, clean=clean)
        made = {WrapperRef("tool", 0): source}
        if previous is not None:
            made[WrapperRef("prior")] = previous.part
        projected = {}
        def wrapper(ref):
            if ref in made:
                return made[ref]
            record = bundle.layout.created[ref.index]
            handle = self.stock.project(tx, bundle, ref)
            projected[ref] = handle
            shape = self.stock._execute(self.stock._instantiate, record, tx.document._get(handle).shape)
            made[ref] = shape
            shape.topo_parent = None if record.topo_parent is None else wrapper(record.topo_parent)
            self._manage(shape, handle, builder)
            return shape
        result = wrapper(bundle.layout.result)
        builder._part = result
        for kind, row in zip((bd.Vertex, bd.Edge, bd.Face, bd.Solid), bundle.layout.lasts):
            builder.lasts[kind] = bd.ShapeList(wrapper(ref) for ref in row)
        frame.output = self.stock.project(tx, bundle, WrapperRef("tool", 0))
        frame.source_native = native
        frame.pending.append((source, frame.output))
        self.builders[id(builder)] = _BuilderState(bundle, result)
        f._record_fallback("builder-effects-retained")
        return True
