"""Bridge loopback commands onto KernelController + intake."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from hermes_pipeline.contracts.runtime import Actor
from hermes_pipeline.controller import KernelController
from hermes_pipeline.operations.projects import ProjectRegistry, RequirementIntake
from hermes_pipeline.persistence.kernel_memory import MemoryKernelStore
from hermes_pipeline.runtime_broker.binding import AgentBinding, BindingTable

_RECORDED = "2026-01-01T00:00:00Z"
_ROLES = {"ADMIN", "CONTRIBUTOR", "VIEWER"}
_STAGE_ROLES = {"planner", "executor", "reviewer", "e2e"}
_RUNTIMES = {"codex", "opencode", "fake"}


class KernelBridge:
    def __init__(self, state_root: Path, inner: Any) -> None:
        self._inner = inner
        self._dir = state_root / "descriptor"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._store = MemoryKernelStore()
        self._controller = KernelController(self._store, recorded_at=_RECORDED)
        self._registry = self._load_registry()
        self._bindings = self._load_bindings()
        self._intake = RequirementIntake(
            self._registry, self._controller, recorded_at=_RECORDED
        )

    def process(self, command_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        op = payload.get("op")
        if op == "register":
            record = self._registry.register(
                str(payload.get("project_id", "")), str(payload.get("name", ""))
            )
            self._save_registry()
            return {"ok": True, "project_id": record.project_id}
        if op == "admit":
            role = str(payload.get("role", ""))
            if role not in _ROLES:
                return {"ok": False, "error": "invalid role"}
            try:
                self._registry.admit(
                    str(payload.get("project_id", "")),
                    str(payload.get("principal_id", "")),
                    role,  # type: ignore[arg-type]
                )
            except KeyError:
                return {"ok": False, "error": "project not found"}
            self._save_registry()
            return {"ok": True}
        if op == "bind":
            stage = str(payload.get("role", ""))
            runtime = str(payload.get("runtime", ""))
            model = str(payload.get("model", ""))
            if stage not in _STAGE_ROLES or runtime not in _RUNTIMES or not model:
                return {"ok": False, "error": "invalid binding"}
            self._bindings.bind(
                AgentBinding(stage, runtime, model)  # type: ignore[arg-type]
            )
            self._save_bindings()
            return {"ok": True, "role": stage, "runtime": runtime, "model": model}
        if op == "bindings":
            return {"ok": True, "bindings": self._bindings.dump()}
        if op == "read":
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
            receipt = self._intake.confirm(
                workspace_id=str(payload.get("workspace_id", "ws_local")),
                project_id=str(payload.get("project_id", "prj_local")),
                pipeline_id=str(payload.get("pipeline_id", "pl_local")),
                actor=Actor(
                    principal_id=str(payload.get("principal_id", "operator")),
                    provider="CLI",
                    provider_actor_id=str(payload.get("principal_id", "operator")),
                ),
                text=text,
                command_id=command_id,
            )
            return receipt.model_dump(mode="json")
        return self._inner.process(command_id, payload)

    def _load_registry(self) -> ProjectRegistry:
        path = self._dir / "projects.json"
        if not path.is_file():
            return ProjectRegistry()
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ProjectRegistry()
        if isinstance(document, dict):
            return ProjectRegistry.load(cast(dict[str, Any], document))
        return ProjectRegistry()

    def _save_registry(self) -> None:
        (self._dir / "projects.json").write_text(
            json.dumps(self._registry.dump(), sort_keys=True),
            encoding="utf-8",
        )

    def _load_bindings(self) -> BindingTable:
        path = self._dir / "bindings.json"
        if not path.is_file():
            return BindingTable({})
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return BindingTable({})
        if isinstance(document, dict):
            return BindingTable.load(cast(dict[str, Any], document))
        return BindingTable({})

    def _save_bindings(self) -> None:
        (self._dir / "bindings.json").write_text(
            json.dumps(self._bindings.dump(), sort_keys=True),
            encoding="utf-8",
        )


__all__ = ["KernelBridge"]
