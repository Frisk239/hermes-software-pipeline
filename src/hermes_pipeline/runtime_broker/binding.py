"""Stage role → runtime family + model bindings (ADR-0032)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from hermes_pipeline.runtime_broker.ports import (
    RuntimeBrokerPort,
    RuntimeHandle,
    RuntimeLaunchRequest,
    RuntimeOutcome,
    RuntimeSignalReceipt,
    RuntimeSnapshot,
)

StageRole = Literal["planner", "executor", "reviewer", "e2e"]
RuntimeFamily = Literal["codex", "opencode", "fake"]


class BindingNotFound(Exception):
    pass


@dataclass(frozen=True)
class AgentBinding:
    role: StageRole
    runtime: RuntimeFamily
    model: str


class BindingTable:
    def __init__(self, bindings: Mapping[StageRole, AgentBinding]) -> None:
        self._bindings = dict(bindings)

    def resolve(self, role: StageRole) -> AgentBinding:
        binding = self._bindings.get(role)
        if binding is None:
            raise BindingNotFound(role)
        return binding


class BoundRuntimeBroker:
    def __init__(
        self,
        table: BindingTable,
        adapters: Mapping[RuntimeFamily, RuntimeBrokerPort],
    ) -> None:
        self._table = table
        self._adapters = dict(adapters)
        self._owners: dict[str, RuntimeBrokerPort] = {}

    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        role = request.role
        if role not in {"planner", "executor", "reviewer", "e2e"}:
            return RuntimeHandle(runtime_id=request.runtime_id, status="UNSUPPORTED")
        try:
            binding = self._table.resolve(cast(StageRole, role))
        except BindingNotFound:
            return RuntimeHandle(runtime_id=request.runtime_id, status="UNSUPPORTED")
        adapter = self._adapters.get(binding.runtime)
        if adapter is None:
            return RuntimeHandle(runtime_id=request.runtime_id, status="UNSUPPORTED")
        bound = RuntimeLaunchRequest(
            runtime_id=request.runtime_id,
            role=binding.role,
            model=binding.model,
        )
        handle = adapter.launch(bound)
        self._owners[request.runtime_id] = adapter
        return handle

    def signal(self, runtime_id: str) -> RuntimeSignalReceipt:
        adapter = self._owners.get(runtime_id)
        if adapter is None:
            return RuntimeSignalReceipt(ok=False, code="UNSUPPORTED")
        return adapter.signal(runtime_id)

    def inspect(self, runtime_id: str) -> RuntimeSnapshot:
        adapter = self._owners.get(runtime_id)
        if adapter is None:
            return RuntimeSnapshot(runtime_id=runtime_id, status="UNSUPPORTED")
        return adapter.inspect(runtime_id)

    def collect(self, runtime_id: str) -> RuntimeOutcome:
        adapter = self._owners.get(runtime_id)
        if adapter is None:
            return RuntimeOutcome(runtime_id=runtime_id, status="UNSUPPORTED")
        return adapter.collect(runtime_id)


__all__ = [
    "AgentBinding",
    "BindingNotFound",
    "BindingTable",
    "BoundRuntimeBroker",
    "RuntimeFamily",
    "StageRole",
]
