"""Bridge loopback commands onto KernelController + intake."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from hermes_pipeline.artifacts.local_cas import LocalCasArtifacts
from hermes_pipeline.contracts.runtime import Actor
from hermes_pipeline.controller import KernelController
from hermes_pipeline.delivery.fake import FakeDelivery
from hermes_pipeline.delivery.ports import DeliveryRecord, DeliveryRequest
from hermes_pipeline.operations.projects import ProjectRegistry, RequirementIntake
from hermes_pipeline.persistence.kernel_memory import MemoryKernelStore
from hermes_pipeline.runtime_broker.binding import AgentBinding, BindingTable
from hermes_pipeline.stage_executor.architecture import (
    ArchitectureGate,
    ArchitectureStage,
)
from hermes_pipeline.stage_executor.prd import PrdGate, PrdStage

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
        self._delivery = self._load_delivery()
        self._prd = self._load_prd()
        self._arch = self._load_arch()

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
        if op == "deliver":
            sha = str(payload.get("sha") or payload.get("name") or "")
            event_id = str(payload.get("event_id", ""))
            project_id = str(payload.get("project_id", "prj_local"))
            pipeline_id = str(payload.get("pipeline_id", "pl_local"))
            if not sha and not event_id:
                return {"ok": False, "error": "missing sha"}
            published: DeliveryRecord | None = None
            if sha:
                published = self._delivery.publish(
                    DeliveryRequest(
                        name=sha,
                        project_id=project_id,
                        pipeline_id=pipeline_id,
                    )
                )
            if event_id:
                published = self._delivery.reconcile(
                    DeliveryRequest(
                        name=sha,
                        project_id=project_id,
                        pipeline_id=pipeline_id,
                        event_id=event_id,
                        check_status=str(payload.get("check_status", "")),
                        review_status=str(payload.get("review_status", "")),
                        queue_status=str(payload.get("queue_status", "")),
                    )
                )
            if published is None:
                return {"ok": False, "error": "missing sha"}
            self._save_delivery()
            return _record_view(published)
        if op == "read":
            workspace_id = str(payload.get("workspace_id", ""))
            pipeline_id = str(payload.get("pipeline_id", ""))
            view = self._intake.read(pipeline_id, workspace_id)
            stored = self._delivery.lookup(pipeline_id)
            result: dict[str, Any] = {
                "pipeline_id": view.pipeline_id,
                "revision": view.revision,
                "status": view.status,
            }
            if stored is not None:
                result.update(_record_view(stored))
            planning = self._prd.get(pipeline_id)
            if planning is not None:
                result.update(planning)
            design = self._arch.get(pipeline_id)
            if design is not None:
                result.update(design)
            return result
        text = payload.get("text")
        if isinstance(text, str):
            workspace_id = str(payload.get("workspace_id", "ws_local"))
            project_id = str(payload.get("project_id", "prj_local"))
            pipeline_id = str(payload.get("pipeline_id", "pl_local"))
            receipt = self._intake.confirm(
                workspace_id=workspace_id,
                project_id=project_id,
                pipeline_id=pipeline_id,
                actor=Actor(
                    principal_id=str(payload.get("principal_id", "operator")),
                    provider="CLI",
                    provider_actor_id=str(payload.get("principal_id", "operator")),
                ),
                text=text,
                command_id=command_id,
            )
            if receipt.status == "ACCEPTED":
                self._advance_prd(pipeline_id, workspace_id, project_id)
                self._advance_architecture(pipeline_id, workspace_id)
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

    def _load_delivery(self) -> FakeDelivery:
        path = self._dir / "delivery.json"
        if not path.is_file():
            return FakeDelivery()
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return FakeDelivery()
        if isinstance(document, dict):
            return FakeDelivery.load(cast(dict[str, Any], document))
        return FakeDelivery()

    def _save_delivery(self) -> None:
        (self._dir / "delivery.json").write_text(
            json.dumps(self._delivery.dump(), sort_keys=True),
            encoding="utf-8",
        )

    def _advance_prd(
        self, pipeline_id: str, workspace_id: str, project_id: str
    ) -> None:
        if pipeline_id in self._prd:
            return
        artifacts = LocalCasArtifacts(self._dir.parent / "cas")
        result = PrdStage(self._bindings, artifacts).run(
            pipeline_id, workspace_id, project_id
        )
        gate = "FAIL"
        if result.status == "COMPLETED":
            gate = (
                PrdGate(self._controller, artifacts)
                .evaluate(
                    pipeline_id=pipeline_id,
                    workspace_id=workspace_id,
                    artifact_id=result.artifact_id,
                )
                .status
            )
        self._prd[pipeline_id] = {
            "prd_id": result.artifact_id or "",
            "prd_status": result.status,
            "prd_gate": gate,
        }
        self._save_prd()

    def _advance_architecture(self, pipeline_id: str, workspace_id: str) -> None:
        if pipeline_id in self._arch:
            return
        planning = self._prd.get(pipeline_id)
        if planning is None or planning.get("prd_gate") != "PASS":
            return
        prd_id = planning.get("prd_id", "")
        artifacts = LocalCasArtifacts(self._dir.parent / "cas")
        result = ArchitectureStage(self._bindings, artifacts).run(
            prd_artifact_id=prd_id
        )
        gate = (
            ArchitectureGate(self._controller, artifacts)
            .evaluate(
                pipeline_id=pipeline_id,
                workspace_id=workspace_id,
                prd_artifact_id=prd_id,
                result=result,
            )
            .status
        )
        self._arch[pipeline_id] = {
            "design_id": result.design_id or "",
            "testplan_id": result.testplan_id or "",
            "arch_status": result.status,
            "arch_gate": gate,
        }
        self._save_arch()

    def _load_prd(self) -> dict[str, dict[str, str]]:
        path = self._dir / "prd.json"
        if not path.is_file():
            return {}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(document, dict):
            return {}
        loaded: dict[str, dict[str, str]] = {}
        typed = cast(dict[str, Any], document)
        for raw_key, item in typed.items():
            if not isinstance(item, dict):
                continue
            row = cast(dict[str, Any], item)
            loaded[str(raw_key)] = {
                "prd_id": str(row.get("prd_id", "")),
                "prd_status": str(row.get("prd_status", "")),
                "prd_gate": str(row.get("prd_gate", "")),
            }
        return loaded

    def _save_prd(self) -> None:
        (self._dir / "prd.json").write_text(
            json.dumps(self._prd, sort_keys=True),
            encoding="utf-8",
        )

    def _load_arch(self) -> dict[str, dict[str, str]]:
        path = self._dir / "architecture.json"
        if not path.is_file():
            return {}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(document, dict):
            return {}
        loaded: dict[str, dict[str, str]] = {}
        typed = cast(dict[str, Any], document)
        for raw_key, item in typed.items():
            if not isinstance(item, dict):
                continue
            row = cast(dict[str, Any], item)
            loaded[str(raw_key)] = {
                "design_id": str(row.get("design_id", "")),
                "testplan_id": str(row.get("testplan_id", "")),
                "arch_status": str(row.get("arch_status", "")),
                "arch_gate": str(row.get("arch_gate", "")),
            }
        return loaded

    def _save_arch(self) -> None:
        (self._dir / "architecture.json").write_text(
            json.dumps(self._arch, sort_keys=True),
            encoding="utf-8",
        )


def _record_view(record: DeliveryRecord) -> dict[str, Any]:
    return {
        "ok": record.ok,
        "action": record.action,
        "branch": record.branch,
        "pr_number": record.pr_number,
        "head_sha": record.head_sha,
        "check_status": record.check_status,
        "review_status": record.review_status,
        "queue_status": record.queue_status,
    }


__all__ = ["KernelBridge"]
