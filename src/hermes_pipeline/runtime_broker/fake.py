"""Deterministic Runtime Broker Adapter that never starts vendor CLIs.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from hermes_pipeline.runtime_broker.ports import (
    RuntimeHandle,
    RuntimeLaunchRequest,
    RuntimeOutcome,
    RuntimeSignalReceipt,
    RuntimeSnapshot,
)


class FakeRuntimeBroker:
    def __init__(self) -> None:
        self.launched: list[str] = []

    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        self.launched.append(request.runtime_id)
        return RuntimeHandle(runtime_id=request.runtime_id, status="FAKE")

    def signal(self, runtime_id: str) -> RuntimeSignalReceipt:
        return RuntimeSignalReceipt(ok=False, code="UNSUPPORTED")

    def inspect(self, runtime_id: str) -> RuntimeSnapshot:
        return RuntimeSnapshot(runtime_id=runtime_id, status="FAKE")

    def collect(self, runtime_id: str) -> RuntimeOutcome:
        return RuntimeOutcome(runtime_id=runtime_id, status="FAKE")


__all__ = ["FakeRuntimeBroker"]
