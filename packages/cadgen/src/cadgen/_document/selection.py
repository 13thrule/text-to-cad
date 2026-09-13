"""Stock ordered subshape projections and bounded analytic Edge queries.

Only exact installed providers execute on resident topology. Returned wrappers
are ordinary build123d classes whose native boundary uses the document's alias
arena. The local carrier cache holds immutable topology only for this execution.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import inspect

from .builder_effects import (
    StockBuilderEffects, _CallableGuard, _closed_runtime_value, _provider_plans_live,
)
from .core import Mutation, OperatorSpec
from .native import NativeResult


_PROOFS = OrderedDict()
_MISSING = object()
_TABLES = ("geom_LUT_EDGE", "geom_LUT_FACE", "inverse_shape_LUT", "downcast_LUT")


@dataclass(frozen=True)
class _Proof:
    plan: object
    tables: tuple
    native: tuple
    fields: tuple
    bindings: tuple
    callables: tuple


class SelectionAdapter:
    def __init__(self, frontend):
        self.frontend = frontend
        self.bd = bd = frontend._bd
        self.stock = None
        self.proof = None
        self._carrier = None
        self._kind = None
        self._members = ()
        mixin = frontend._topology.Mixin1D
        self.extra = (
            (bd.Shape, "geom_type"), (bd.Edge, "arc_center"),
            (mixin, "radius"), (mixin, "normal"), (bd.Edge, "geom_adaptor"),
            (bd.Shape, "__bool__"),
            *((bd.Vector, name) for name in ("__init__", "__getattribute__",
                                            "__setattr__", "wrapped")),
        )
        self.original = {
            name: inspect.getattr_static(owner, name)
            for owner, name in self.extra[:4]
        }
        self.installed = {}
        for owner, name in self.extra[:3]:
            original = self.original[name]
            if type(original) is not property or original.fget is None:
                continue
            def query_property(shape, _name=name, _original=original):
                return self.query(shape, _name, _original.fget)
            replacement = property(query_property, original.fset, original.fdel,
                                   original.__doc__)
            frontend._patch(owner, name, replacement)
            self.installed[name] = replacement
        original_normal = self.original["normal"]
        def normal(shape):
            return self.query(shape, "normal", original_normal)
        if inspect.isfunction(original_normal):
            frontend._patch(mixin, "normal", normal)
            self.installed["normal"] = normal

    def prepare(self):
        key = (*self.frontend._effect_proof_key(), id(self.bd.Edge),
               id(self.frontend._topology.Mixin1D))
        self._proof_key = key
        prior = _PROOFS.get(key)
        if prior is not None and _provider_plans_live((prior.plan,)):
            self.proof = prior
            return
        # Establish the canonical inventory before author execution. Once a
        # runtime has been proven, an unknown/reloaded generation stays private.
        self.stock = StockBuilderEffects(self.frontend, extra_providers=self.extra,
                                        require_cached=bool(_PROOFS))
        if prior is not None:
            self.proof = prior

    def finalize(self):
        if self.stock is None:
            return
        self.stock._adopt_frontend_interceptors()
        self.stock.finalize_frontend_guards()
        if self.proof is not None:
            return
        if not self.stock.providers_match() or self.stock._canonical_plan is None:
            return
        from OCP import GeomAbs, TopAbs, gp
        from .frontend import _stock_function
        native = tuple(
            (owner, name, inspect.getattr_static(owner, name))
            for owner, names in (
                (gp.gp_Circ, ("Radius", "Axis", "Position")),
                (gp.gp_Elips, ("Axis", "Position")),
                (gp.gp_Ax1, ("Direction",)), (gp.gp_Ax2, ("Location",)),
                (gp.gp_Pnt, ("XYZ",)), (gp.gp_Dir, ("XYZ",)),
            ) for name in names
        )
        if not all(type(provider).__name__ == "instancemethod"
                   and type(owner).__module__ == "pybind11_builtins"
                   for owner, _name, provider in native):
            return
        tables = tuple((name, _closed_runtime_value(inspect.getattr_static(self.bd.Shape, name)))
                       for name in _TABLES)
        fields = tuple((owner, name) for owner, names in (
            *((owner, ("_wrapped",)) for owner in (
                self.bd.Shape, self.bd.Vertex, self.bd.Edge, self.bd.Face,
                self.bd.Solid, self.bd.Vector)),
            (self.bd.Vertex, ("X", "Y", "Z")), (self.bd.Face, ("created_on",)),
            (self.bd.Vector, ("vector_index",)),
        ) for name in names)
        if any(inspect.getattr_static(owner, name, _MISSING) is not _MISSING
               for owner, name in fields):
            return
        # Stock methods also compare/format enums and dynamically dereference
        # module constants. Those operations can invoke authored Python just as
        # a replaced geometry descriptor can; object identity alone is not a
        # proof for a Python function whose code can change in place.
        bindings = tuple((owner, name, inspect.getattr_static(owner, name, _MISSING))
                         for owner, names in (
            (self.bd, ("GeomType",)),
            (self.bd.GeomType, ("__eq__", "__ne__", "__hash__", "__str__", "__format__",
                                "__getattribute__", "CIRCLE", "ELLIPSE")),
            (type(self.bd.GeomType), ("__getattribute__", "__getattr__")),
            *((owner, ("__eq__", "__ne__", "__hash__")) for owner in (
                TopAbs.TopAbs_ShapeEnum, GeomAbs.GeomAbs_CurveType, GeomAbs.GeomAbs_SurfaceType)),
            (TopAbs, tuple("TopAbs_" + name for name in (
                "VERTEX", "EDGE", "WIRE", "FACE", "SHELL", "SOLID",
                "COMPSOLID", "COMPOUND", "SHAPE"))),
        ) for name in names)
        callables = []
        for _owner, _name, provider in bindings:
            if inspect.isfunction(provider):
                if not _stock_function(provider, "enum", provider.__qualname__):
                    return
                guard = _CallableGuard.capture(provider)
                if guard is None:
                    return
                callables.append(guard)
        self.proof = _Proof(self.stock._canonical_plan, tables, native, fields,
                            bindings, tuple(callables))
        _PROOFS[self._proof_key] = self.proof
        while len(_PROOFS) > 8:
            _PROOFS.popitem(last=False)

    def providers_match(self):
        if self.proof is None:
            return False
        if self.stock is None:
            self.stock = StockBuilderEffects(self.frontend, extra_providers=self.extra,
                                            require_cached=True)
            self.stock.finalize_frontend_guards()
        try:
            return (self.stock.providers_match()
                    and all(_closed_runtime_value(inspect.getattr_static(self.bd.Shape, name)) == value
                            for name, value in self.proof.tables)
                    and all(inspect.getattr_static(owner, name, _MISSING) is provider
                            for owner, name, provider in self.proof.native)
                    and all(inspect.getattr_static(owner, name, _MISSING) is _MISSING
                            for owner, name in self.proof.fields)
                    and all(inspect.getattr_static(owner, name, _MISSING) is expected
                            for owner, name, expected in self.proof.bindings)
                    and all(guard.matches() for guard in self.proof.callables))
        except (AttributeError, ValueError):
            return False

    def allows_access(self, shape, name):
        # A shadowing authored callable must see a private native wrapper even
        # before it invokes anything. The installed closure verifies the full
        # provider proof again at actual invocation (including captured methods).
        expected = self.installed.get(name)
        return (expected is not None and type(shape) is self.bd.Edge
                and inspect.getattr_static(shape, name, _MISSING) is expected)

    def clear(self):
        self._carrier, self._kind, self._members = None, None, ()

    def _slots(self, native, kind):
        private = self.frontend.transaction.escape_arena.active
        if private:
            self.clear()
        if native is not self._carrier or kind != self._kind:
            wrapper = self.frontend._wrap_native(native)
            members = self.frontend._inside_compute(self.frontend._native_call, kind, wrapper)
            self._members = tuple(members)
            self._carrier, self._kind = native, kind
        result = self._members
        if private:
            self.clear()
        return result

    @staticmethod
    def exact_index(index):
        return (type(index) in (int, bool)
                or type(index) is slice and all(type(value) in (int, bool, type(None))
                                                for value in (index.start, index.stop, index.step)))

    def selected(self, selection, index=None, *, indexed=False):
        from .frontend import ManagedSelection, _state
        owner = selection._owner
        state = _state(owner)
        tx, frontend = self.frontend.transaction, self.frontend
        if (type(selection) is not ManagedSelection or selection._filters
                or state is None or state.private or state.children is not None
                or tx.escape_arena.active or (indexed and not self.exact_index(index))
                or not self.providers_match()):
            self.clear()
            values = selection._private_value()
            return values[index] if indexed else values
        handle = frontend._geometry_handle(owner)
        kind = selection._kind
        count = tx.query(handle, lambda native: len(self._slots(native, kind)))
        # Use Python's own list operation for negative indices, slice steps and
        # exception spelling. No author __index__ is invoked in trusted scope.
        ordinals = list(range(count))
        chosen = ordinals[index] if indexed else ordinals
        scalar = type(chosen) is int
        chosen = [chosen] if scalar else chosen
        parent = object.__getattribute__(owner, "topo_parent")
        parent = owner if parent is None else parent
        values = []
        for ordinal in chosen:
            def compute(inputs, _arena, _ordinal=ordinal):
                member = self._slots(inputs[0], kind)[_ordinal]
                return NativeResult(object.__getattribute__(member, "_wrapped"))
            output = tx.evaluate(
                OperatorSpec("build123d.selection.member", "1", Mutation.READ_ONLY),
                (kind, ordinal, self.stock._context_key), (handle,), compute,
            )
            def metadata(native, _ordinal=ordinal):
                member = self._slots(native, kind)[_ordinal]
                if type(member) is self.bd.Vertex:
                    raw = object.__getattribute__(member, "__dict__")
                    return (raw["X"], raw["Y"], raw["Z"])
                return None
            coordinates = tx.query(handle, metadata) if kind == "vertices" else None
            cls = {"vertices": self.bd.Vertex, "edges": self.bd.Edge,
                   "faces": self.bd.Face, "solids": self.bd.Solid}[kind]
            wrapper = object.__new__(cls)
            frontend._init_empty(wrapper, frontend._logical("selection"), output)
            # Selection constructors have fewer fields than Part wrappers.
            # Preserve absent stock metadata instead of inventing attributes.
            raw = object.__getattribute__(wrapper, "__dict__")
            del raw["_NodeMixin__children"]
            if cls is not self.bd.Solid:
                del raw["material"], raw["joints"]
            object.__setattr__(wrapper, "topo_parent", parent)
            if coordinates is not None:
                for name, value in zip(("X", "Y", "Z"), coordinates):
                    object.__setattr__(wrapper, name, value)
            if cls is self.bd.Face:
                object.__setattr__(wrapper, "created_on", None)
            values.append(wrapper)
        return values[0] if scalar else self.bd.ShapeList(values)

    def query(self, shape, name, original):
        from .frontend import _state
        frontend, tx = self.frontend, self.frontend.transaction
        state = _state(shape)
        if state is None or frontend._compute_depth:
            return original(shape)
        if (state.private or type(shape) is not self.bd.Edge
                or not frontend.active or not self.providers_match()):
            return original(frontend._escape_shape(shape))
        handle = frontend._geometry_handle(shape)
        if name == "normal":
            geom_type = tx.query(handle, lambda native: frontend._inside_compute(
                self.original["geom_type"].fget, frontend._wrap_native(native)))
            if geom_type not in (self.bd.GeomType.CIRCLE, self.bd.GeomType.ELLIPSE):
                return original(frontend._escape_shape(shape))
        return tx.query(handle, lambda native: frontend._inside_compute(
            original, frontend._wrap_native(native)))
