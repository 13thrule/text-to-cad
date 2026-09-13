"""Cached builder-provider discovery preserves live hook validation."""
from __future__ import annotations

from importlib.machinery import SourceFileLoader
from types import ModuleType
import sys
import unittest
from unittest.mock import patch

from cadgen import build123d as bd
from cadgen._document import Document
from cadgen._document import builder_effects
from cadgen._document import modifiers, selection
from cadgen._document.builder_effects import StockBuilderEffects
from cadgen._document.frontend import (
    FrontendSession, _EFFECT_PROOFS, _HIERARCHY_CODE_PROOFS,
)
from cadgen._document.sketch_effects import SketchNativeEffects


class BuilderProviderCacheTest(unittest.TestCase):
    def setUp(self):
        caches = (
            builder_effects._PROVIDER_PLANS,
            _EFFECT_PROOFS,
            _HIERARCHY_CODE_PROOFS,
            selection._PROOFS,
            modifiers._PROOFS,
        )
        snapshots = tuple(tuple(cache.items()) for cache in caches)
        for cache in caches:
            cache.clear()

        def restore():
            for cache, snapshot in zip(caches, snapshots):
                cache.clear()
                cache.update(snapshot)

        self.addCleanup(restore)

    def test_warm_hierarchy_reuses_pre_author_code_inventory_with_live_hooks(self):
        original = SourceFileLoader.get_code
        calls = []

        def counted(loader, fullname):
            calls.append(fullname)
            return original(loader, fullname)

        document = Document("hierarchy-code-inventory")
        # Establish the independent builder/sketch proof first so this test
        # counts only hierarchy inventory discovery.
        with document.begin() as transaction:
            with FrontendSession(transaction):
                pass
            transaction.commit()
        _HIERARCHY_CODE_PROOFS.clear()
        with patch.object(SourceFileLoader, "get_code", counted):
            with document.begin() as transaction:
                with FrontendSession(transaction):
                    pass
                transaction.commit()
            discovered = tuple(calls)
            self.assertEqual(3, sum(name in {
                "build123d.topology.composite",
                "build123d.topology.shape_core",
                "anytree.node.nodemixin",
            } for name in discovered))

            with document.begin() as transaction:
                with FrontendSession(transaction) as frontend:
                    parent = object.__new__(bd.Compound)
                    self.assertTrue(frontend._can_defer_hierarchy(parent, ()))
                    original_hook = bd.Compound._pre_attach_children
                    with patch.object(bd.Compound, "_pre_attach_children", lambda shape, children: None):
                        self.assertFalse(frontend._can_defer_hierarchy(parent, ()))
                    self.assertIs(original_hook, bd.Compound._pre_attach_children)
                transaction.commit()
        self.assertEqual(discovered, tuple(calls))

    def test_warm_algebra_installs_interceptors_without_constructing_unused_auditors(self):
        document = Document("provider-lazy-unused")
        with document.begin() as transaction:
            with FrontendSession(transaction) as frontend:
                self.assertIsNotNone(frontend._builder_effects.stock)
                self.assertIsNotNone(frontend._sketch_effects.stock)
            transaction.commit()

        with patch.object(builder_effects, "_remember_provider_plan",
                          side_effect=AssertionError("warm rediscovery")):
            with document.begin() as transaction:
                with FrontendSession(transaction) as frontend:
                    first, second = bd.Box(2, 3, 4), bd.Box(1, 1, 1)
                    combined = first + bd.Pos(5, 0, 0) * second
                    self.assertAlmostEqual(25., combined.volume)
                    self.assertIsNone(frontend._builder_effects.stock)
                    self.assertIsNone(frontend._sketch_effects.stock)
                transaction.commit()

    def test_post_entry_provider_mutation_deopts_without_warm_rediscovery(self):
        document = Document("provider-lazy-mutated")
        with document.begin() as transaction:
            with FrontendSession(transaction):
                pass
            transaction.commit()

        callbacks = []
        original_cut = bd.Shape.cut
        def cut(shape, *others):
            callbacks.append(len(others))
            return original_cut(shape, *others)
        with document.begin() as transaction:
            with FrontendSession(transaction) as frontend:
                self.assertIsNone(frontend._builder_effects.stock)
                with patch.object(builder_effects, "_remember_provider_plan",
                                  side_effect=AssertionError("warm rediscovery")), \
                     patch.object(bd.Shape, "cut", cut):
                    with bd.BuildPart() as builder:
                        bd.Box(4, 4, 4)
                        bd.Box(1, 1, 6, mode=bd.Mode.SUBTRACT)
                self.assertAlmostEqual(60., builder.part.volume)
                self.assertEqual([1], callbacks)
                self.assertFalse(frontend._builder_effects.stock.providers_match())
                self.assertEqual(0, frontend._fallback_counts.get("builder-effects-retained", 0))
            transaction.commit()

    def test_warm_discovery_reuses_code_plan_with_independent_live_lists(self):
        original = SourceFileLoader.get_code
        calls = []

        def counted(loader, fullname):
            calls.append(fullname)
            return original(loader, fullname)

        with patch.object(SourceFileLoader, "get_code", counted):
            first = StockBuilderEffects()
            discovered = len(calls)
            second = StockBuilderEffects()
        self.assertTrue(first.providers_match())
        self.assertTrue(second.providers_match())
        self.assertGreater(discovered, 0)
        self.assertEqual(discovered, len(calls))
        self.assertIsNot(first._guards, second._guards)
        self.assertIsNot(first._globals, second._globals)
        self.assertIsNot(first._cells, second._cells)

    def test_extra_provider_inventory_has_its_own_reusable_plan(self):
        original = SourceFileLoader.get_code
        calls = []

        def counted(loader, fullname):
            calls.append(fullname)
            return original(loader, fullname)

        extra = ((bd.Shape, "clean"),)
        with patch.object(SourceFileLoader, "get_code", counted):
            StockBuilderEffects()
            normal = len(calls)
            first_extra = StockBuilderEffects(extra_providers=extra)
            extra_discovery = len(calls)
            second_extra = StockBuilderEffects(extra_providers=extra)
        self.assertTrue(first_extra.providers_match())
        self.assertTrue(second_extra.providers_match())
        self.assertGreater(extra_discovery, normal)
        self.assertEqual(extra_discovery, len(calls))
        self.assertEqual(2, len(builder_effects._PROVIDER_PLANS))

    def test_cached_plan_rejects_descriptor_code_default_closure_and_global_changes(self):
        first = StockBuilderEffects()
        self.assertTrue(first.providers_match())

        original_clean = bd.Shape.clean
        with patch.object(bd.Shape, "clean", lambda shape: original_clean(shape)):
            self.assertFalse(StockBuilderEffects().providers_match())

        code_guard = next(guard for guard in first._callable_guards
                          if guard.function.__module__.startswith("build123d."))
        function = code_guard.function
        original_code = function.__code__
        function.__code__ = (lambda *args, **kwargs: None).__code__
        try:
            self.assertFalse(StockBuilderEffects().providers_match())
        finally:
            function.__code__ = original_code

        default_guard = next(guard for guard in first._callable_guards
                             if guard.function.__defaults__ is not None)
        function = default_guard.function
        original_defaults = function.__defaults__
        function.__defaults__ = (*original_defaults, None)
        try:
            self.assertFalse(StockBuilderEffects().providers_match())
        finally:
            function.__defaults__ = original_defaults

        namespace, name, original_global = next(
            row for row in first._globals if row[0].get(row[1]) is row[2])
        namespace[name] = object()
        try:
            self.assertFalse(StockBuilderEffects().providers_match())
        finally:
            namespace[name] = original_global

        closure_guard = next(guard for guard in first._callable_guards if guard.closure)
        cell = closure_guard.closure[0]
        original_cell = cell.cell_contents
        cell.cell_contents = object()
        try:
            self.assertFalse(StockBuilderEffects().providers_match())
        finally:
            cell.cell_contents = original_cell

    def test_same_module_name_with_replaced_module_deopts_cached_plan(self):
        first = StockBuilderEffects()
        guard = next(value for value in first._callable_guards
                     if value.module.startswith("build123d."))
        replacement = ModuleType(guard.module)
        replacement.__file__ = sys.modules[guard.module].__file__
        with patch.dict(sys.modules, {guard.module: replacement}):
            self.assertFalse(StockBuilderEffects().providers_match())

    def test_build123d_wrapper_alias_change_during_body_deopts(self):
        import build123d as runtime

        effects = StockBuilderEffects()
        original = runtime.Solid
        runtime.Solid = object()
        try:
            self.assertFalse(effects.providers_match())
        finally:
            runtime.Solid = original

    def test_default_snapshot_is_bounded_cycle_safe_and_calls_no_author_protocols(self):
        calls = []

        class Meta(type):
            def __getattribute__(cls, name):
                if name not in {"__class__"}:
                    calls.append(("getattribute", name))
                return super().__getattribute__(name)

            def __eq__(cls, other):
                calls.append(("eq", other))
                return False

            def __hash__(cls):
                calls.append(("hash", None))
                return id(cls)

        class Authored(metaclass=Meta):
            def __eq__(self, other):
                calls.append(("instance-eq", other))
                return False

            def __hash__(self):
                calls.append(("instance-hash", None))
                return id(self)

        cycle = []
        cycle.append(cycle)
        value = [Authored(), cycle]
        calls.clear()
        first = builder_effects._closed_runtime_value(value)
        second = builder_effects._closed_runtime_value(value)
        self.assertEqual(first, second)
        self.assertEqual([], calls)
        too_deep = []
        cursor = too_deep
        for _ in range(builder_effects._RUNTIME_VALUE_DEPTH + 1):
            child = []
            cursor.append(child)
            cursor = child
        with self.assertRaisesRegex(ValueError, "depth limit"):
            builder_effects._closed_runtime_value(too_deep)

    def test_compiled_class_lookup_rechecks_mro_cells_without_descriptors(self):
        calls = []

        def read_dict(cls):
            calls.append(("dict", cls))
            raise AssertionError("metaclass __dict__ callback entered")

        class ShadowMeta(type):
            __dict__ = property(read_dict)

        class Meta(type):
            pass

        provider = object()
        class Base:
            value = provider
        class Other:
            value = provider
        class Child(Base, metaclass=Meta):
            pass

        guard = builder_effects._StaticProviderGuard.capture(
            Child, "value", provider)
        self.assertIsNotNone(guard)
        self.assertTrue(guard.matches())
        self.assertEqual([], calls)

        class AlternateMeta(type):
            pass
        Child.__class__ = AlternateMeta
        try:
            self.assertFalse(guard.matches())
            self.assertEqual([], calls)
        finally:
            Child.__class__ = Meta
        self.assertTrue(guard.matches())

        Meta.__bases__ = (ShadowMeta,)
        try:
            self.assertFalse(guard.matches())
            self.assertEqual([], calls)
        finally:
            Meta.__bases__ = (type,)
        self.assertTrue(guard.matches())

        Child.value = object()
        try:
            self.assertFalse(guard.matches())
            self.assertEqual([], calls)
        finally:
            del Child.value
        self.assertTrue(guard.matches())

        Child.__bases__ = (Other,)
        try:
            self.assertFalse(guard.matches())
            self.assertEqual([], calls)
        finally:
            Child.__bases__ = (Base,)
        self.assertTrue(guard.matches())

        Meta.value = object()
        try:
            self.assertFalse(guard.matches())
            self.assertEqual([], calls)
        finally:
            del Meta.value

    def test_callable_guard_rechecks_only_mutable_descendants(self):
        mutable_default = [["default"]]
        mutable_closure = [["closure"]]

        def provider(value=(mutable_default,)):
            return value, mutable_closure

        guard = builder_effects._CallableGuard.capture(provider)
        self.assertIsNotNone(guard)
        self.assertTrue(guard.matches())
        mutable_default[0].append("changed")
        self.assertFalse(guard.matches())
        mutable_default[0].pop()
        self.assertTrue(guard.matches())
        mutable_closure[0].append("changed")
        self.assertFalse(guard.matches())
        mutable_closure[0].pop()
        self.assertTrue(guard.matches())

        def immutable_provider(value=(1, ("fixed", frozenset({2})))):
            return value

        immutable = builder_effects._CallableGuard.capture(immutable_provider)
        self.assertIsNotNone(immutable)
        with patch.object(
                builder_effects, "_closed_runtime_value",
                side_effect=AssertionError("immutable state was traversed")):
            self.assertTrue(immutable.matches())

        oversized = "x" * (builder_effects._RUNTIME_VALUE_LIMIT + 1)
        def oversized_provider(value=oversized):
            return value
        self.assertIsNone(
            builder_effects._CallableGuard.capture(oversized_provider))

    def test_noncanonical_inventory_is_not_retained_and_cache_is_bounded(self):
        class Foreign:
            def provider(self):
                return None

        StockBuilderEffects(extra_providers=((Foreign, "provider"),))
        self.assertEqual(0, len(builder_effects._PROVIDER_PLANS))
        for count in range(builder_effects._PROVIDER_PLAN_LIMIT + 2):
            extra = ((bd.Shape, "clean"),) * count
            StockBuilderEffects(extra_providers=extra)
        self.assertLessEqual(len(builder_effects._PROVIDER_PLANS),
                             builder_effects._PROVIDER_PLAN_LIMIT)

    def test_noncanonical_transitive_value_is_not_retained(self):
        import build123d as runtime

        StockBuilderEffects()
        builder_effects._PROVIDER_PLANS.clear()

        class Foreign:
            pass

        original = runtime.Align
        runtime.Align = Foreign()
        try:
            StockBuilderEffects()
            self.assertEqual(0, len(builder_effects._PROVIDER_PLANS))
        finally:
            runtime.Align = original

    def test_exact_object_new_builtin_is_admitted_for_extra_inventory(self):
        effects = StockBuilderEffects(extra_providers=((bd.Shape, "__new__"),))
        self.assertTrue(effects.providers_match())

    def test_added_field_descriptors_deopt_without_entering_author_callbacks(self):
        effects = StockBuilderEffects()
        self.assertTrue(effects.providers_match())
        calls = []

        class Trap:
            def __get__(self, instance, owner=None):
                calls.append(("get", instance, owner))
                raise AssertionError("descriptor callback entered")

            def __set__(self, instance, value):
                calls.append(("set", instance, value))
                raise AssertionError("descriptor callback entered")

        for owner, name in ((bd.Shape, "label"), (bd.Part, "topo_parent"),
                            (bd.BuildPart, "lasts"), (bd.BuildSketch, "pending_faces")):
            with self.subTest(owner=owner.__name__, name=name):
                setattr(owner, name, Trap())
                try:
                    self.assertFalse(effects.providers_match())
                    self.assertFalse(StockBuilderEffects().providers_match())
                    self.assertEqual([], calls)
                finally:
                    delattr(owner, name)

    def test_frontend_interceptor_code_defaults_and_closures_are_frozen(self):
        document = Document("provider-interceptor-guards")
        with document.begin() as transaction:
            with FrontendSession(transaction) as frontend:
                stock = frontend._builder_effects.stock
                internal = [guard for guard in stock._callable_guards
                            if guard.module.startswith("cadgen._document.")]
                self.assertTrue(internal)
                self.assertTrue(stock.providers_match())

                code_guard = internal[0]
                function = code_guard.function
                original_code = function.__code__
                function.__code__ = original_code.replace(
                    co_firstlineno=original_code.co_firstlineno + 1
                )
                try:
                    self.assertFalse(stock.providers_match())
                finally:
                    function.__code__ = original_code
                self.assertTrue(stock.providers_match())

                default_guard = next(guard for guard in internal
                                     if guard.function.__defaults__ is not None)
                function = default_guard.function
                original_defaults = function.__defaults__
                function.__defaults__ = (*original_defaults, object())
                try:
                    self.assertFalse(stock.providers_match())
                finally:
                    function.__defaults__ = original_defaults
                self.assertTrue(stock.providers_match())

                closure_guard = next(guard for guard in internal if guard.closure)
                cell = closure_guard.closure[0]
                original_cell = cell.cell_contents
                cell.cell_contents = object()
                try:
                    self.assertFalse(stock.providers_match())
                finally:
                    cell.cell_contents = original_cell
                self.assertTrue(stock.providers_match())

    def test_frontend_restore_keeps_cached_descriptor_provider_plan_reusable(self):
        document = Document("provider-descriptor-restore")
        with document.begin() as transaction:
            with FrontendSession(transaction):
                pass
        effects = SketchNativeEffects()
        self.assertTrue(effects.stock.providers_match())


if __name__ == "__main__":
    unittest.main()
