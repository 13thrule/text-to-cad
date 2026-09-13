"""Exact, session-scoped source and managed-data capture.

Authored modules execute from the bytes read for this session.  Imports below
the entry/package roots use the same rule and never fall back to bytecode-only
first-party modules.  The process import table is restored when the session
ends; returned modules are therefore useful only while their session is live.
Each helper or data file is captured when it is actually read; this module does
not claim an atomic snapshot of a whole project tree.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import threading
from types import CodeType, FunctionType, ModuleType
from typing import Iterable


_IMPORT_LOCK = threading.RLock()
_PROTECTED_TOP_LEVEL = frozenset({"cadgen", "build123d", "OCP", *sys.builtin_module_names})


@dataclass(frozen=True)
class CapturedInput:
    """One immutable path buffer and the digest of those exact bytes."""

    path: Path
    data: bytes
    digest: str

    def __post_init__(self) -> None:
        path = Path(self.path).resolve()
        data = bytes(self.data)
        digest = hashlib.sha256(data).hexdigest()
        if self.digest != digest:
            raise ValueError("captured input digest does not match its bytes")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "data", data)

    @classmethod
    def read(cls, path: Path) -> CapturedInput:
        resolved = Path(path).resolve()
        data = resolved.read_bytes()
        return cls(resolved, data, hashlib.sha256(data).hexdigest())


class _SourceLoader(importlib.abc.Loader):
    def __init__(self, session: SourceSession, path: Path, captured: CapturedInput | None = None):
        self._session = session
        self._path = path
        self._captured = captured

    def create_module(self, spec):
        self._session._claim_module(spec.name)
        return None

    def exec_module(self, module: ModuleType) -> None:
        captured = self._captured or CapturedInput.read(self._path)
        self._session._record(captured)
        code = compile(captured.data, str(captured.path), "exec", dont_inherit=True)
        self._session._record_code_tree(code, captured)
        exec(code, module.__dict__)


class _SourceFinder(importlib.abc.MetaPathFinder):
    def __init__(self, session: SourceSession):
        self._session = session

    def find_spec(self, fullname: str, path=None, target=None):
        if fullname.partition(".")[0] in _PROTECTED_TOP_LEVEL:
            return None
        return self._session._find_spec(fullname, path)


class SourceSession:
    """Execute one captured entry and its first-party imports exactly once.

    ``read_data`` returns the bytes read at that call and records the matching
    :class:`CapturedInput` in ``inputs``. Relative data paths are resolved from
    the entry's directory and must remain below a managed source root.
    """

    def __init__(self, entry: CapturedInput, search_paths: Iterable[Path] = ()):
        if not isinstance(entry, CapturedInput):
            raise TypeError("entry must be a CapturedInput")
        self.entry = entry
        self._entry_name, entry_root = self._entry_identity(entry.path)
        supplied = tuple(Path(path).resolve() for path in search_paths)
        for path in supplied:
            if not path.is_dir():
                raise ValueError(f"source search path is not a directory: {path}")
        self._roots = tuple(dict.fromkeys((entry_root, entry.path.parent, *supplied)))
        if self._entry_name.partition(".")[0] in _PROTECTED_TOP_LEVEL:
            raise ValueError("entry cannot replace an installed engine package")
        self._inputs: list[CapturedInput] = []
        self._input_keys: set[tuple[Path, str]] = set()
        self._module: ModuleType | None = None
        self._active = False
        self._owner: int | None = None
        self._owned_top_levels: set[str] = set()
        self._owned_module_prefixes: set[str] = set()
        self._initial_modules: dict[str, ModuleType] | None = None
        self._modules_before: dict[str, ModuleType] | None = None
        self._path_before: list[str] | None = None
        self._meta_path_before: list[object] | None = None
        self._finder = _SourceFinder(self)
        self._code_inputs: dict[int, tuple[CodeType, CapturedInput]] = {}

    @property
    def inputs(self) -> tuple[CapturedInput, ...]:
        return tuple(self._inputs)

    @staticmethod
    def _entry_identity(path: Path) -> tuple[str, Path]:
        path = path.resolve()
        packages: list[str] = []
        cursor = path.parent
        while (cursor / "__init__.py").is_file():
            if not cursor.name.isidentifier():
                raise ValueError(f"invalid package directory: {cursor.name}")
            packages.insert(0, cursor.name)
            cursor = cursor.parent
        if path.name == "__init__.py":
            if not packages:
                raise ValueError("a top-level __init__.py has no importable package name")
            return ".".join(packages), cursor
        if packages and not path.stem.isidentifier():
            raise ValueError(f"package source filename is not importable: {path.name}")
        name = path.stem if path.stem.isidentifier() else (
            f"_cadgen_source_{hashlib.sha256(str(path).encode()).hexdigest()[:20]}"
        )
        return ".".join((*packages, name)), cursor if packages else path.parent

    def _check_active(self) -> None:
        if not self._active:
            raise RuntimeError("source session is not active")
        if threading.get_ident() != self._owner:
            raise RuntimeError("source session must run in its owning thread")

    def __enter__(self) -> SourceSession:
        if self._active:
            raise RuntimeError("source session is already active")
        _IMPORT_LOCK.acquire()
        try:
            self._owner = threading.get_ident()
            importlib.invalidate_caches()
            self._initial_modules = dict(sys.modules)
            relevant = self._first_party_top_levels()
            self._owned_top_levels = relevant
            self._modules_before = {
                name: module for name, module in sys.modules.items()
                if name.partition(".")[0] in relevant
            }
            self._path_before = list(sys.path)
            self._meta_path_before = list(sys.meta_path)
            # The captured table already identifies every managed module;
            # do not scan all installed packages a second time to remove them.
            for name in self._modules_before:
                sys.modules.pop(name, None)
            sys.meta_path.insert(0, self._finder)
            self._active = True
            return self
        except BaseException:
            self._restore()
            _IMPORT_LOCK.release()
            raise

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            self._restore()
        finally:
            _IMPORT_LOCK.release()

    def _restore(self) -> None:
        if self._modules_before is not None:
            prefixes = tuple(prefix + "." for prefix in self._owned_module_prefixes)
            for name in tuple(sys.modules):
                if (name.partition(".")[0] in self._owned_top_levels
                        or name in self._owned_module_prefixes
                        or prefixes and name.startswith(prefixes)):
                    sys.modules.pop(name, None)
            sys.modules.update(self._modules_before)
        if self._path_before is not None:
            sys.path[:] = self._path_before
        if self._meta_path_before is not None:
            sys.meta_path[:] = self._meta_path_before
        importlib.invalidate_caches()
        self._initial_modules = None
        self._code_inputs.clear()
        self._active = False
        self._owner = None

    def _first_party_top_levels(self) -> set[str]:
        names = {self._entry_name.partition(".")[0]}
        for root in self._roots:
            if not root.is_dir():
                continue
            for child in root.iterdir():
                if child.name.startswith("."):
                    continue
                if child.is_file() and child.suffix == ".py" and child.stem.isidentifier():
                    names.add(child.stem)
                elif child.is_file() and child.suffix == ".pyc" and child.stem.isidentifier():
                    names.add(child.stem)
                elif child.is_dir() and child.name.isidentifier():
                    if child.name == "__pycache__":
                        for cached in child.glob("*.pyc"):
                            stem = cached.name.partition(".")[0]
                            if stem.isidentifier():
                                names.add(stem)
                    else:
                        names.add(child.name)
        return {
            name for name in names - _PROTECTED_TOP_LEVEL
            if name == self._entry_name.partition(".")[0]
            or self._resolution_is_managed(name)
        }

    def _managed(self, path: Path) -> bool:
        resolved = path.resolve()
        return any(resolved == root or resolved.is_relative_to(root) for root in self._roots)

    @staticmethod
    def _bytecode_exists(directory: Path, name: str) -> bool:
        if (directory / f"{name}.pyc").is_file():
            return True
        cache = directory / "__pycache__"
        return cache.is_dir() and any(cache.glob(f"{name}.*.pyc"))

    def _search_path(self, path) -> list[str]:
        if path is not None:
            return [str(value) for value in path]
        result: list[str] = []
        for value in (*self._roots, *sys.path):
            text = str(value)
            if text not in result:
                result.append(text)
        return result

    @staticmethod
    def _spec_origin_path(spec) -> Path | None:
        origin = getattr(spec, "origin", None)
        if not origin or origin in {"built-in", "frozen"}:
            return None
        try:
            return Path(origin).resolve()
        except (OSError, TypeError, ValueError):
            return None

    def _namespace_is_managed(self, spec) -> bool:
        locations = getattr(spec, "submodule_search_locations", None)
        return locations is not None and any(
            self._managed(Path(location)) for location in locations
        )

    def _resolution_is_managed(self, fullname: str) -> bool:
        spec = importlib.machinery.PathFinder.find_spec(fullname, self._search_path(None))
        origin = self._spec_origin_path(spec) if spec is not None else None
        if origin is not None:
            return self._managed(origin)
        if spec is not None and self._namespace_is_managed(spec):
            return True
        return spec is None and self._managed_bytecode_exists(fullname, None)

    def _managed_bytecode_exists(self, fullname: str, path) -> bool:
        leaf = fullname.rpartition(".")[2]
        if path is None:
            locations = [(root, tuple(fullname.split("."))) for root in self._roots]
        else:
            locations = [(Path(base).resolve(), (leaf,)) for base in path
                         if self._managed(Path(base))]
        for base, parts in locations:
            target = base.joinpath(*parts)
            if (self._bytecode_exists(target.parent, target.name)
                    or self._bytecode_exists(target, "__init__")):
                return True
        return False

    def _find_spec(self, fullname: str, path):
        self._check_active()
        spec = importlib.machinery.PathFinder.find_spec(fullname, self._search_path(path))
        origin = self._spec_origin_path(spec) if spec is not None else None
        if origin is not None and self._managed(origin):
            if origin.suffix != ".py":
                raise ModuleNotFoundError(
                    f"first-party bytecode ignored without captured source: {fullname}"
                )
            is_package = spec.submodule_search_locations is not None
            loader = _SourceLoader(self, origin)
            return importlib.util.spec_from_file_location(
                fullname, origin, loader=loader,
                submodule_search_locations=[str(origin.parent)] if is_package else None,
            )
        if spec is not None:
            if self._namespace_is_managed(spec):
                if self._managed_bytecode_exists(fullname, path):
                    raise ModuleNotFoundError(
                        f"first-party bytecode ignored without captured source: {fullname}"
                    )
                self._claim_module(fullname)
            return spec
        if self._managed_bytecode_exists(fullname, path):
            raise ModuleNotFoundError(
                f"first-party bytecode ignored without captured source: {fullname}"
            )
        return None

    def _claim_module(self, name: str) -> None:
        self._check_active()
        if self._modules_before is None or self._initial_modules is None:
            raise RuntimeError("source session import state is not initialized")
        # Entry captured the entire top-level subtree, including modules not
        # imported again this time. Both restoration and removal are already
        # covered; only a newly discovered managed subtree needs another claim.
        if name.partition(".")[0] in self._owned_top_levels:
            return
        if name not in self._owned_module_prefixes:
            self._owned_module_prefixes.add(name)
            prefix = name + "."
            for existing, module in self._initial_modules.items():
                if existing == name or existing.startswith(prefix):
                    self._modules_before.setdefault(existing, module)

    def _record(self, captured: CapturedInput) -> None:
        self._check_active()
        if not self._managed(captured.path):
            raise ValueError(f"captured input is outside managed source roots: {captured.path}")
        key = (captured.path, captured.digest)
        if key not in self._input_keys:
            self._input_keys.add(key)
            self._inputs.append(captured)

    def _record_code_tree(self, code: CodeType, captured: CapturedInput) -> None:
        self._check_active()
        self._code_inputs[id(code)] = (code, captured)
        for value in code.co_consts:
            if isinstance(value, CodeType):
                self._record_code_tree(value, captured)

    def input_for_function(self, function: FunctionType) -> CapturedInput:
        """Return the exact source buffer from which ``function`` was compiled."""
        self._check_active()
        code = getattr(function, "__code__", None)
        if not isinstance(code, CodeType):
            raise ValueError("function was not compiled from captured source")
        found = self._code_inputs.get(id(code))
        if found is None or found[0] is not code:
            raise ValueError("function was not compiled from captured source")
        return found[1]

    def load_entry(self) -> ModuleType:
        self._check_active()
        if self._module is not None:
            return self._module
        spec = importlib.util.spec_from_file_location(
            self._entry_name, self.entry.path,
            loader=_SourceLoader(self, self.entry.path, self.entry),
            submodule_search_locations=[str(self.entry.path.parent)]
            if self.entry.path.name == "__init__.py" else None,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot create source module for {self.entry.path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[self._entry_name] = module
        parent = self._entry_name.rpartition(".")[0]
        try:
            if parent:
                importlib.import_module(parent)
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(self._entry_name, None)
            raise
        self._module = module
        return module

    def read_data(self, path: Path) -> bytes:
        self._check_active()
        value = Path(path)
        resolved = (self.entry.path.parent / value).resolve() if not value.is_absolute() else value.resolve()
        if not self._managed(resolved):
            raise ValueError(f"managed data path is outside source roots: {resolved}")
        captured = CapturedInput.read(resolved)
        self._record(captured)
        return captured.data
