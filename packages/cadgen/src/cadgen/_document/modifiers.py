"""Bounded ordinary-list 3D edge modifiers with exact projection ancestry.

Stock generic operations perform their normal validation, conversion and error
handling. Temporary native wrappers belong solely to the proven computation;
authored wrappers continue to own separate execution allocations.
"""
from __future__ import annotations

from collections import OrderedDict
import inspect
from math import isfinite

from .builder_effects import StockBuilderEffects, _provider_plans_live
from .core import Mutation, OperatorSpec
from .native import NativeResult


_PROOFS = OrderedDict()


class EdgeModifiers:
    def __init__(self, frontend):
        import contextvars
        import build123d.operations_generic as generic
        self.frontend, self.bd = frontend, frontend._bd
        self.generic = generic
        self.stock = None
        self.proof = None
        self.extra = (
            (generic, "fillet"), (generic, "chamfer"),
            (generic, "flatten_sequence"), (generic, "validate_inputs"),
            (frontend._topology.Mixin3D, "fillet"),
            (frontend._topology.Mixin3D, "chamfer"),
            (frontend._topology.Mixin3D, "_make_3d_result"),
            (self.bd.Builder, "_get_context"),
            *((owner, "_dim") for owner in (self.bd.Part, self.bd.Solid, self.bd.Box,
                                            self.bd.Cone, self.bd.Cylinder, self.bd.Edge)),
        )
        self.original = {"fillet": generic.fillet, "chamfer": generic.chamfer}
        self.public = {"fillet": frontend._native_originals["fillet_function"],
                       "chamfer": self.bd.chamfer}
        self.context = inspect.getattr_static(self.bd.Builder, "_current")
        self.context_get = self.context.get if type(self.context) is contextvars.ContextVar else None

    def prepare(self):
        key = (*self.frontend._effect_proof_key(), id(self.generic))
        self._proof_key = key
        prior = _PROOFS.get(key)
        if prior is not None and _provider_plans_live((prior,)):
            self.proof = prior
            return
        self.stock = StockBuilderEffects(self.frontend, extra_providers=self.extra,
                                        require_cached=bool(_PROOFS))

    def finalize(self):
        if self.stock is None:
            return
        self.stock._adopt_frontend_interceptors()
        self.stock.finalize_frontend_guards()
        if self.stock.providers_match() and self.stock._canonical_plan is not None:
            self.proof = self.stock._canonical_plan
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
        import contextvars
        return (type(self.context) is contextvars.ContextVar
                and all(self.public[name] is self.original[name] for name in ("fillet", "chamfer"))
                and inspect.getattr_static(self.bd.Builder, "_current") is self.context
                and all(inspect.getattr_static(self.bd.ShapeList, name) is inspect.getattr_static(list, name)
                        for name in ("append", "extend"))
                and self.stock.providers_match()
                and self.frontend._selection.providers_match())

    def attempt(self, operation, objects, size, *, length2=None, angle=None, reference=None):
        from .frontend import _state, _IDENTITY
        frontend, bd, tx = self.frontend, self.bd, self.frontend.transaction
        try:
            finite = type(size) in (int, float) and isfinite(size) and size > 0
        except OverflowError:
            finite = False
        if (frontend._compute_depth or tx.escape_arena.active
                or type(objects) not in (list, tuple, bd.ShapeList)
                or not finite
                or length2 is not None or angle is not None or reference is not None
                or not self.providers_match() or self.context_get(None) is not None):
            return None
        if not (tuple.__len__(objects) if type(objects) is tuple else list.__len__(objects)):
            return None
        # Inspect exact builtin storage only after provider proof. No custom
        # iterables, nested containers or index callbacks execute in this path.
        edges = tuple(objects)
        if any(type(edge) is not bd.Edge for edge in edges):
            return None
        parent = object.__getattribute__(edges[0], "__dict__").get("topo_parent")
        state = _state(parent)
        if (type(parent) not in (bd.Part, bd.Solid, bd.Box, bd.Cone, bd.Cylinder)
                or state is None or state.private or state.children is not None
                or state.handle is None
                or any(object.__getattribute__(edge, "__dict__").get("topo_parent") is not parent
                       for edge in edges)):
            return None
        parent_handle = frontend._geometry_handle(parent)
        handles = []
        for edge in edges:
            selected = _state(edge)
            if (selected is None or selected.private or selected.handle is None
                    or selected.transform != _IDENTITY):
                return None
            origin = frontend._selection.origin(selected.handle)
            if origin is None or origin[1] != parent_handle or origin[2] != "edges":
                # Equal prototype geometry or a reassigned topo_parent is not
                # evidence of source membership in this execution allocation.
                return None
            handles.append(selected.handle)
        container = type(objects)
        def compute(inputs, _arena):
            def execute():
                # Preserve BasePartObject target conversion in the generic body.
                # These stock fields are private adapter scaffolding, not copies
                # of authored metadata or pointers published to source Python.
                target = object.__new__(type(parent))
                for name, value in (("_wrapped", inputs[0]), ("for_construction", False),
                                    ("label", ""), ("_color", None), ("topo_parent", None),
                                    ("material", ""), ("joints", {})):
                    object.__setattr__(target, name, value)
                selected = []
                for native in inputs[1:]:
                    edge = bd.Edge(frontend._downcast_native(native))
                    edge.topo_parent = target
                    selected.append(edge)
                result = self.original[operation](container(selected), size)
                return NativeResult(frontend._native_originals["wrapped"].fget(result))
            return frontend._inside_compute(execute)
        output = tx.evaluate(
            OperatorSpec("build123d.generic." + operation, "1", Mutation.READ_ONLY),
            (size, container.__name__, self.stock._context_key),
            (parent_handle, *handles), compute,
        )
        result = object.__new__(bd.Part)
        frontend._init_empty(result, frontend._logical(operation), output)
        return result

    def private_inputs(self, objects):
        """Materialize known wrappers before ordinary validation callbacks.

        Arbitrary iterables are left to the stock function; inspecting them here
        would duplicate authored iteration or consume a generator prematurely.
        """
        from .frontend import _state
        if type(objects) not in (list, tuple, self.bd.ShapeList):
            return
        values = tuple.__iter__(objects) if type(objects) is tuple else list.__iter__(objects)
        for shape in values:
            state = _state(shape)
            if state is not None:
                parent = object.__getattribute__(shape, "__dict__").get("topo_parent")
                if _state(parent) is not None:
                    self.frontend._escape_shape(parent)
                self.frontend._escape_shape(shape)
