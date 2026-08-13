"""Deterministic Operations Adapter used by doctor/health.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from hermes_pipeline.operations.ports import (
    HealthReport,
    OperationsRequest,
    OperationsResult,
)


class FakeOperations:
    def __init__(self, *, writer_active: bool = False) -> None:
        self.writer_active = writer_active

    def health(self) -> HealthReport:
        return HealthReport(ok=not self.writer_active, checks=("state-root", "runtime"))

    def reconcile(self, request: OperationsRequest) -> OperationsResult:
        return self._gated(request)

    def backup(self, request: OperationsRequest) -> OperationsResult:
        return self._gated(request)

    def restore(self, request: OperationsRequest) -> OperationsResult:
        return self._gated(request)

    def _gated(self, request: OperationsRequest) -> OperationsResult:
        status = "UNSUPPORTED" if self.writer_active else "OK"
        return OperationsResult(name=request.name, status=status)


__all__ = ["FakeOperations"]
