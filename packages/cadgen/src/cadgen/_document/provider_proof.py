"""Small live provider proofs for closed internal operations.

The document frontend establishes these proofs before author code executes and
checks them again at every admitted operation.  A proof is an inventory, not a
successful-check cache: any changed descriptor, global, function body/default,
closure cell, or bounded builtin container rejects that individual operation.
"""
from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Iterable

from .builder_effects import (
    _CallableGuard,
    _closed_runtime_value,
    _provider_plans_live,
)


_MISSING = object()
_CONTAINERS = (tuple, list, dict, set, frozenset)


def _functions(value: Any) -> tuple[Any, ...]:
    kind = type(value)
    if kind is property:
        return tuple(item for item in (value.fget, value.fset, value.fdel)
                     if item is not None)
    if kind in (classmethod, staticmethod):
        return (value.__func__,)
    return (value,) if inspect.isfunction(value) else ()


def _state(value: Any) -> Any:
    return (_closed_runtime_value(value)
            if any(type(value) is kind for kind in _CONTAINERS) else None)


@dataclass(frozen=True)
class OperationProviderProof:
    """Exact, callback-safe live proof for one stock operation family."""

    plan: Any
    descriptors: tuple[tuple[Any, str, Any, Any], ...]
    globals: tuple[tuple[dict, str, Any, Any], ...]
    callables: tuple[_CallableGuard, ...]

    @classmethod
    def capture(
        cls,
        plan: Any,
        entries: Iterable[Any],
        *,
        descriptors: Iterable[tuple[Any, str, Any]] = (),
        absent: Iterable[tuple[Any, str]] = (),
        callable_guards: Iterable[_CallableGuard] = (),
        global_baselines: Iterable[tuple[dict, str, Any, Any]] = (),
    ) -> "OperationProviderProof | None":
        """Capture a subset of an already authenticated canonical plan.

        ``entries`` and descriptor functions seed a bounded transitive walk of
        exact Python globals.  build123d and stdlib functions must already be
        callable members of the pre-author canonical plan.  Internal frontend
        closures are captured here because they are installed after that plan.
        """
        if not _provider_plans_live((plan,)):
            return None
        canonical = {id(guard.function): guard
                     for guard in (*plan.callables, *tuple(callable_guards))}
        canonical_globals = {}
        for namespace, name, value in plan.globals:
            key = (id(namespace), name)
            prior = canonical_globals.get(key, _MISSING)
            if prior is not _MISSING and prior[0] is not value:
                return None
            canonical_globals[key] = (value, None)
        for namespace, name, value, state in global_baselines:
            if type(namespace) is not dict or type(name) is not str:
                return None
            key = (id(namespace), name)
            prior = canonical_globals.get(key, _MISSING)
            if prior is not _MISSING and prior[0] is not value:
                return None
            canonical_globals[key] = (value, state)
        descriptor_rows: list[tuple[Any, str, Any, Any]] = []
        descriptor_seen = set()
        native_owners = set()
        pending = [function for entry in entries for function in _functions(entry)]
        try:
            for descriptor in descriptors:
                if len(descriptor) == 3:
                    owner, name, expected = descriptor
                    state = _state(expected)
                elif len(descriptor) == 4:
                    owner, name, expected, state = descriptor
                else:
                    return None
                if type(name) is not str or inspect.getattr_static(owner, name, _MISSING) is not expected:
                    return None
                key = (id(owner), name)
                if key not in descriptor_seen:
                    descriptor_seen.add(key)
                    descriptor_rows.append((owner, name, expected, state))
                if (inspect.isclass(owner)
                        and (owner.__module__ or "").startswith("OCP.")):
                    native_owners.add(owner)
                pending.extend(_functions(expected))
            for owner, name in absent:
                if (type(name) is not str
                        or inspect.getattr_static(owner, name, _MISSING) is not _MISSING):
                    return None
                key = (id(owner), name)
                if key not in descriptor_seen:
                    descriptor_seen.add(key)
                    descriptor_rows.append((owner, name, _MISSING, None))

            callable_rows: list[_CallableGuard] = []
            callable_seen = set()
            traversed = set()
            global_rows: list[tuple[dict, str, Any, Any]] = []
            global_seen = set()
            native_names = set()
            def remember(function):
                if id(function) in callable_seen:
                    return True
                module = function.__module__ or ""
                guard = canonical.get(id(function))
                if guard is None and module.startswith("cadgen._document."):
                    guard = _CallableGuard.capture(function)
                if guard is None or guard.function is not function:
                    return False
                callable_seen.add(id(function))
                callable_rows.append(guard)
                return True
            while pending:
                function = pending.pop()
                if not inspect.isfunction(function):
                    continue
                if not remember(function):
                    return None
                if id(function) in traversed:
                    continue
                traversed.add(id(function))
                if (function.__module__ or "").startswith("build123d."):
                    native_names.update(function.__code__.co_names)
                namespace = function.__globals__
                if type(namespace) is not dict:
                    return None
                internal = (function.__module__ or "").startswith("cadgen._document.")
                for name in function.__code__.co_names:
                    if name not in namespace:
                        continue
                    value = namespace[name]
                    key = (id(namespace), name)
                    baseline = canonical_globals.get(key, _MISSING)
                    if not internal and (baseline is _MISSING or baseline[0] is not value):
                        return None
                    if key not in global_seen:
                        global_seen.add(key)
                        global_rows.append((namespace, name, value,
                                            _state(value) if internal else baseline[1]))
                    if inspect.isfunction(value):
                        if not remember(value):
                            return None
                        if (value.__module__ or "").startswith(
                                ("build123d.", "cadgen._document.")):
                            pending.append(value)
                    if (inspect.isclass(value)
                            and (value.__module__ or "").startswith("OCP.")
                            and not issubclass(value, BaseException)):
                        native_owners.add(value)
                for cell in function.__closure__ or ():
                    captured = cell.cell_contents
                    if inspect.isfunction(captured):
                        if not remember(captured):
                            return None
                        if (captured.__module__ or "").startswith(
                                ("build123d.", "cadgen._document.")):
                            pending.append(captured)

            # Mirror the canonical auditor's callback boundary for native
            # classes reached through operation globals.  Returned helper types
            # such as gp_Circ are supplied explicitly by the operation owner.
            for owner in native_owners:
                if type(owner).__module__ != "pybind11_builtins":
                    return None
                lifecycle = {"__new__", "__init__", "__getattribute__", "__setattr__"}
                for name in {*lifecycle, *native_names}:
                    provider = inspect.getattr_static(owner, name, None)
                    if provider is None or not callable(provider):
                        continue
                    function = (provider.__func__
                                if isinstance(provider, staticmethod) else provider)
                    defining = next((base for base in owner.__mro__
                                     if name in vars(base)), None)
                    native_method = (
                        type(function).__name__ in
                        ("instancemethod", "builtin_function_or_method")
                        and (getattr(function, "__module__", "") or "").startswith("OCP.")
                    )
                    native_slot = (
                        type(function).__name__ == "wrapper_descriptor"
                        and type(function.__objclass__).__module__ == "pybind11_builtins"
                        and function.__objclass__.__module__.startswith("OCP.")
                    )
                    native_shared_new = (
                        name == "__new__" and defining is not None
                        and defining.__module__ == "pybind11_builtins"
                        and defining.__name__ == "pybind11_object"
                        and type(function).__name__ == "builtin_function_or_method"
                        and function is inspect.getattr_static(defining, "__new__")
                        and getattr(function, "__self__", None) is defining
                    )
                    builtin_slot = (
                        name in lifecycle and defining in (object, type)
                        and function is inspect.getattr_static(defining, name)
                    )
                    if not (native_method or native_slot or native_shared_new or builtin_slot):
                        return None
                    key = (id(owner), name)
                    if key not in descriptor_seen:
                        descriptor_seen.add(key)
                        descriptor_rows.append((owner, name, provider, None))
                meta = type(owner)
                for name in ("__call__", "__getattribute__", "__instancecheck__",
                             "__subclasscheck__"):
                    provider = inspect.getattr_static(meta, name, None)
                    if provider is None:
                        return None
                    function = (provider.__func__
                                if isinstance(provider, staticmethod) else provider)
                    defining = next((base for base in meta.__mro__
                                     if name in vars(base)), None)
                    native_method = (
                        type(function).__name__ in
                        ("instancemethod", "builtin_function_or_method")
                        and (getattr(function, "__module__", "") or "").startswith("OCP.")
                    )
                    native_slot = (
                        type(function).__name__ == "wrapper_descriptor"
                        and function.__objclass__ is meta
                        and meta.__module__ == "pybind11_builtins"
                    )
                    builtin_slot = (
                        defining in (object, type)
                        and function is inspect.getattr_static(defining, name)
                    )
                    if not (native_method or native_slot or builtin_slot):
                        return None
                    key = (id(meta), name)
                    if key not in descriptor_seen:
                        descriptor_seen.add(key)
                        descriptor_rows.append((meta, name, provider, None))
            return cls(plan, tuple(descriptor_rows), tuple(global_rows),
                       tuple(callable_rows))
        except Exception:
            return None

    def matches(self) -> bool:
        """Revalidate this operation now, without retaining success."""
        try:
            return (
                _provider_plans_live((self.plan,))
                and all(
                    inspect.getattr_static(owner, name, _MISSING) is expected
                    and (state is None or _closed_runtime_value(expected) == state)
                    for owner, name, expected, state in self.descriptors
                )
                and all(
                    namespace.get(name, _MISSING) is expected
                    and (state is None or _closed_runtime_value(expected) == state)
                    for namespace, name, expected, state in self.globals
                )
                and all(guard.matches() for guard in self.callables)
            )
        except Exception:
            return False
