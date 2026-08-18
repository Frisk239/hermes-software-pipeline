"""Project registry and requirement intake (slice 03-01)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import (
    Actor,
    CommandError,
    CommandReceipt,
    ControllerCommand,
)
from hermes_pipeline.controller.ports import ControllerPort, PipelineQuery, PipelineView

ProjectRole = Literal["ADMIN", "CONTRIBUTOR", "VIEWER"]
_INTAKE_ROLES = frozenset({"ADMIN", "CONTRIBUTOR"})
_RECEIPT = "https://schemas.hermes-pipeline.dev/runtime/command-receipt/v1"


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    name: str


class ProjectRegistry:
    def __init__(self) -> None:
        self._projects: dict[str, ProjectRecord] = {}
        self._members: dict[tuple[str, str], ProjectRole] = {}

    def register(self, project_id: str, name: str) -> ProjectRecord:
        record = ProjectRecord(project_id=project_id, name=name)
        self._projects[project_id] = record
        return record

    def admit(self, project_id: str, principal_id: str, role: ProjectRole) -> None:
        if project_id not in self._projects:
            raise KeyError(project_id)
        self._members[(project_id, principal_id)] = role

    def exists(self, project_id: str) -> bool:
        return project_id in self._projects

    def role_of(self, project_id: str, principal_id: str) -> ProjectRole | None:
        if not self.exists(project_id):
            return None
        return self._members.get((project_id, principal_id))

    def dump(self) -> dict[str, Any]:
        return {
            "projects": [
                {"project_id": item.project_id, "name": item.name}
                for item in self._projects.values()
            ],
            "members": [
                {
                    "project_id": project_id,
                    "principal_id": principal_id,
                    "role": role,
                }
                for (project_id, principal_id), role in self._members.items()
            ],
        }

    @classmethod
    def load(cls, document: dict[str, Any]) -> ProjectRegistry:
        registry = cls()
        projects = document.get("projects", [])
        if isinstance(projects, list):
            for raw in cast(list[object], projects):
                if not isinstance(raw, dict):
                    continue
                row = cast(dict[str, Any], raw)
                project_id = str(row.get("project_id", ""))
                name = str(row.get("name", ""))
                if project_id:
                    registry.register(project_id, name)
        members = document.get("members", [])
        if isinstance(members, list):
            for raw in cast(list[object], members):
                if not isinstance(raw, dict):
                    continue
                row = cast(dict[str, Any], raw)
                role = str(row.get("role", ""))
                if role not in {"ADMIN", "CONTRIBUTOR", "VIEWER"}:
                    continue
                registry.admit(
                    str(row.get("project_id", "")),
                    str(row.get("principal_id", "")),
                    cast(ProjectRole, role),
                )
        return registry


class RequirementIntake:
    def __init__(
        self, registry: ProjectRegistry, controller: ControllerPort, *, recorded_at: str
    ) -> None:
        self._registry = registry
        self._controller = controller
        self._recorded_at = recorded_at

    def confirm(
        self,
        *,
        workspace_id: str,
        project_id: str,
        pipeline_id: str,
        actor: Actor,
        text: str,
        command_id: str,
    ) -> CommandReceipt:
        if not self._registry.exists(project_id):
            return self._reject(
                command_id, pipeline_id, actor, "NOT_FOUND", "project not found"
            )
        if self._registry.role_of(project_id, actor.principal_id) is None:
            return self._reject(
                command_id,
                pipeline_id,
                actor,
                "AUTHORIZATION_DENIED",
                "not a project member",
            )
        role = self._registry.role_of(project_id, actor.principal_id)
        if role not in _INTAKE_ROLES:
            return self._reject(
                command_id,
                pipeline_id,
                actor,
                "AUTHORIZATION_DENIED",
                "intake requires contributor",
            )
        command = ControllerCommand(
            schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
            schema_version=FixedV1Integer(1),
            command_id=command_id,
            idempotency_key=f"intake-{command_id}-key000",
            workspace_id=workspace_id,
            project_id=project_id,
            pipeline_id=pipeline_id,
            expected_revision=0,
            actor=actor,
            ingress="CLI",
            command_type="CONFIRM_REQUIREMENT",
            payload={"text": text},
            correlation_id=f"corr-{command_id}",
            submitted_at=UtcTimestampRef(self._recorded_at),
        )
        return self._controller.submit(command)

    def read(self, pipeline_id: str, workspace_id: str) -> PipelineView:
        return self._controller.read(
            PipelineQuery(pipeline_id=pipeline_id, workspace_id=workspace_id)
        )

    def _reject(
        self,
        command_id: str,
        pipeline_id: str,
        actor: Actor,
        code: Literal["NOT_FOUND", "AUTHORIZATION_DENIED"],
        message: str,
    ) -> CommandReceipt:
        del actor
        return CommandReceipt(
            schema_id=_RECEIPT,
            schema_version=FixedV1Integer(1),
            command_id=command_id,
            status="REJECTED",
            pipeline_id=pipeline_id,
            observed_revision=0,
            event_ids=[],
            error=CommandError(code=code, message=message, retryable=False),
            recorded_at=UtcTimestampRef(self._recorded_at),
            correlation_id=f"corr-{command_id}",
        )


__all__ = [
    "ProjectRecord",
    "ProjectRegistry",
    "ProjectRole",
    "RequirementIntake",
]
