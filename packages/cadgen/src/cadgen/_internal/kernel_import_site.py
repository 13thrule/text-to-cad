"""Who imported the CAD kernel first, for the eager-import hint.

``@step`` wants a model's module body to stay kernel-free so a current build
can be skipped, or handed to the warm daemon, before OCP's ~2.5 s import is
paid. When the kernel IS loaded by the time the decorator runs, the useful
message is not "you imported it" but WHERE: a ``from build123d import ...``
at module top is one cause, and ``from cadgen import build123d as bd`` does
not prevent the other -- a module-level ``bd.Align.CENTER`` default or a
palette constant built from a kernel type resolves an attribute at import
time and triggers the real import through the lazy proxy.

A ``sys.meta_path`` finder that never finds anything: it only notes the first
request for ``build123d`` or ``OCP`` and the innermost frame outside cadgen's
own package -- the lazy proxy is one route in, but any other cadgen-internal
module that happens to import the kernel at its own top level (e.g. a module
under ``cadgen/_internal`` reached transitively from a model's own import) is
just as much cadgen's business, not the model author's; naming that internal
file instead of the causal project import leaves the hint with nothing
actionable to fix. Installed by ``cadgen``'s package ``__init__`` so it is in
place before any model module body runs.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

_KERNEL_TOP_LEVEL = ("build123d", "OCP")
_SITE: tuple[str, int, str] | None = None
_CADGEN_PACKAGE_DIR = Path(__file__).resolve().parent.parent


class _KernelImportRecorder:
    """Records the first kernel import request; finds nothing, ever."""

    def find_spec(self, fullname, path=None, target=None):
        global _SITE
        if _SITE is None and fullname.partition(".")[0] in _KERNEL_TOP_LEVEL and fullname.partition(".")[0] not in sys.modules:
            _SITE = _caller_site()
        return None


def _is_cadgen_internal(filename: str) -> bool:
    try:
        resolved = Path(filename).resolve()
    except OSError:
        return False
    return resolved == _CADGEN_PACKAGE_DIR or _CADGEN_PACKAGE_DIR in resolved.parents


def _caller_site() -> tuple[str, int, str] | None:
    for frame in reversed(traceback.extract_stack()):
        filename = frame.filename
        if "importlib" in filename or filename.startswith("<frozen") or _is_cadgen_internal(filename):
            continue
        return (filename, frame.lineno, frame.line or "")
    return None


def install() -> None:
    if not any(isinstance(finder, _KernelImportRecorder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _KernelImportRecorder())


def first_import_site() -> tuple[str, int, str] | None:
    """``(file, line, source)`` of the statement that first pulled the kernel
    in, or None when it is not loaded / was loaded before cadgen was imported."""
    return _SITE
