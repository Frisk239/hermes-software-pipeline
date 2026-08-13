"""Public Operations Interface adopted by Slice 00-07.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class HealthReport:
    ok: bool
    checks: tuple[str, ...]


@dataclass(frozen=True)
class OperationsRequest:
    name: str


@dataclass(frozen=True)
class OperationsResult:
    name: str
    status: Literal["OK", "UNSUPPORTED"]


@runtime_checkable
class OperationsPort(Protocol):
    def health(self) -> HealthReport:
        """Return a bounded health report."""
        ...

    def reconcile(self, request: OperationsRequest) -> OperationsResult:
        """Reconcile a named operational target."""
        ...

    def backup(self, request: OperationsRequest) -> OperationsResult:
        """Backup a named operational target."""
        ...

    def restore(self, request: OperationsRequest) -> OperationsResult:
        """Restore a named operational target."""
        ...


__all__ = [
    "HealthReport",
    "OperationsPort",
    "OperationsRequest",
    "OperationsResult",
]
