"""One admission protocol for native, derivation, export and future consumers.

Reservations are declared estimates, not a measurement of OCCT allocations.
This synchronous owner fails admission explicitly instead of creating pools or
blocking indefinitely. A service scheduler can queue and retry the same request.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from threading import Event, RLock
from typing import Iterator


class AdmissionDenied(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


def _counts(*values: int) -> None:
    if any(type(value) is not int for value in values):
        raise TypeError("resource counts must be nonnegative integers")
    if any(value < 0 for value in values):
        raise ValueError("resource counts must be nonnegative integers")


@dataclass(frozen=True)
class ResourceRequest:
    kind: str = "native"
    cpu_slots: int = 1
    native_bytes: int = 0
    derived_bytes: int = 0

    def __post_init__(self) -> None:
        if self.kind not in {"native", "mesh", "export", "query", "escape", "checkpoint"}:
            raise ValueError(f"unknown document resource kind: {self.kind}")
        _counts(self.cpu_slots, self.native_bytes, self.derived_bytes)


class ResourceAdmission:
    def __init__(self, *, cpu_slots: int = 1, native_bytes: int = 512 * 1024**2,
                 derived_bytes: int = 256 * 1024**2) -> None:
        _counts(cpu_slots, native_bytes, derived_bytes)
        self.capacity = (cpu_slots, native_bytes, derived_bytes)
        self._used = [0, 0, 0]
        self._lock = RLock()

    @property
    def used(self) -> tuple[int, int, int]:
        with self._lock:
            return tuple(self._used)

    @contextmanager
    def admit(self, request: ResourceRequest, *, cancellation: Event | None = None
              ) -> Iterator[None]:
        demand = (request.cpu_slots, request.native_bytes, request.derived_bytes)
        with self._lock:
            if cancellation is not None and cancellation.is_set():
                raise Cancelled("document computation was cancelled")
            if any(u + d > c for u, d, c in zip(self._used, demand, self.capacity)):
                raise AdmissionDenied(f"insufficient resources for {request.kind}: {demand}")
            self._used = [u + d for u, d in zip(self._used, demand)]
        try:
            yield
            if cancellation is not None and cancellation.is_set():
                raise Cancelled("document computation was cancelled")
        finally:
            with self._lock:
                self._used = [u - d for u, d in zip(self._used, demand)]
