"""Bridge loopback commands onto KernelController + intake."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hermes_pipeline.contracts.runtime import Actor
from hermes_pipeline.controller import KernelController
from hermes_pipeline.operations.projects import ProjectRegistry, RequirementIntake
from hermes_pipeline.persistence.kernel_memory import MemoryKernelStore

_RECORDED = "2026-01-01T00:00:00Z"


class KernelBridge:
    def __init__(self, state_root: Path, inner: Any) -> None:
        del state_root
        self._inner = inner
        self._store = MemoryKernelStore()
        self._controller = KernelController(self._store, recorded_at=_RECORDED)
        self._registry = ProjectRegistry()
        self._intake = RequirementIntake(
            self._registry, self._controller, recorded_at=_RECORDED
        )

    def process(self, command_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("op") == "read":
            workspace_id = str(payload.get("workspace_id", ""))
            pipeline_id = str(payload.get("pipeline_id", ""))
            view = self._intake.read(pipeline_id, workspace_id)
            return {
                "pipeline_id": view.pipeline_id,
                "revision": view.revision,
                "status": view.status,
            }
        text = payload.get("text")
        if isinstance(text, str):
            workspace_id = str(payload.get("workspace_id", "ws_local"))
            project_id = str(payload.get("project_id", "prj_local"))
            pipeline_id = str(payload.get("pipeline_id", "pl_local"))
            principal = str(payload.get("principal_id", "operator"))
            if not self._registry.exists(project_id):
                self._registry.register(project_id, project_id)
            if self._registry.role_of(project_id, principal) is None:
                self._registry.admit(project_id, principal, "CONTRIBUTOR")
            receipt = self._intake.confirm(
                workspace_id=workspace_id,
                project_id=project_id,
                pipeline_id=pipeline_id,
                actor=Actor(
                    principal_id=principal,
                    provider="CLI",
                    provider_actor_id=principal,
                ),
                text=text,
                command_id=command_id,
            )
            return receipt.model_dump(mode="json")
        return self._inner.process(command_id, payload)


__all__ = ["KernelBridge"]
