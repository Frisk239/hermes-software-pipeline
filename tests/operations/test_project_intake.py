from __future__ import annotations

from hermes_pipeline.contracts.runtime import Actor
from hermes_pipeline.controller import KernelController
from hermes_pipeline.operations.projects import ProjectRegistry, RequirementIntake
from hermes_pipeline.persistence.kernel_memory import MemoryKernelStore

_RECORDED = "2026-01-01T00:00:00Z"


def _actor(principal_id: str) -> Actor:
    return Actor(
        principal_id=principal_id,
        provider="CLI",
        provider_actor_id=principal_id,
    )


def _intake() -> tuple[RequirementIntake, MemoryKernelStore]:
    store = MemoryKernelStore()
    controller = KernelController(store, recorded_at=_RECORDED)
    registry = ProjectRegistry()
    registry.register("prj_demo", "Demo")
    registry.admit("prj_demo", "alice", "CONTRIBUTOR")
    registry.admit("prj_demo", "viewer", "VIEWER")
    return RequirementIntake(registry, controller, recorded_at=_RECORDED), store


def test_contributor_intake_opens_pipeline() -> None:
    intake, store = _intake()
    receipt = intake.confirm(
        workspace_id="ws_demo",
        project_id="prj_demo",
        pipeline_id="pl_demo",
        actor=_actor("alice"),
        text="need a login page",
        command_id="cmd_intake_alice",
    )
    assert receipt.status == "ACCEPTED"
    view = intake.read("pl_demo", "ws_demo")
    assert view.status == "OPEN"
    assert view.revision == 1
    assert store.counts().events == 1


def test_unknown_member_is_denied_without_event() -> None:
    intake, store = _intake()
    receipt = intake.confirm(
        workspace_id="ws_demo",
        project_id="prj_demo",
        pipeline_id="pl_demo",
        actor=_actor("bob"),
        text="need a login page",
        command_id="cmd_intake_bob",
    )
    assert receipt.status == "REJECTED"
    assert receipt.error.code == "AUTHORIZATION_DENIED"
    assert store.counts().events == 0


def test_viewer_cannot_intake() -> None:
    intake, store = _intake()
    receipt = intake.confirm(
        workspace_id="ws_demo",
        project_id="prj_demo",
        pipeline_id="pl_demo",
        actor=_actor("viewer"),
        text="need a login page",
        command_id="cmd_intake_viewer",
    )
    assert receipt.status == "REJECTED"
    assert receipt.error.code == "AUTHORIZATION_DENIED"
    assert store.counts().events == 0


def test_missing_project_is_not_found() -> None:
    intake, store = _intake()
    receipt = intake.confirm(
        workspace_id="ws_demo",
        project_id="prj_missing",
        pipeline_id="pl_demo",
        actor=_actor("alice"),
        text="need a login page",
        command_id="cmd_intake_missing",
    )
    assert receipt.status == "REJECTED"
    assert receipt.error.code == "NOT_FOUND"
    assert store.counts().events == 0


def test_empty_text_after_auth_is_validation() -> None:
    intake, store = _intake()
    receipt = intake.confirm(
        workspace_id="ws_demo",
        project_id="prj_demo",
        pipeline_id="pl_demo",
        actor=_actor("alice"),
        text="   ",
        command_id="cmd_intake_empty",
    )
    assert receipt.status == "REJECTED"
    assert receipt.error.code == "VALIDATION_ERROR"
    assert receipt.error.message == "empty requirement"
    assert store.counts().events == 0
