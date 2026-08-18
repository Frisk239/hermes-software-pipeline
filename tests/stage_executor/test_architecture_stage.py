from __future__ import annotations

from pathlib import Path

from hermes_pipeline.artifacts import LocalCasArtifacts
from hermes_pipeline.contracts.runtime import Actor
from hermes_pipeline.controller import KernelController
from hermes_pipeline.operations.projects import ProjectRegistry, RequirementIntake
from hermes_pipeline.persistence.kernel_memory import MemoryKernelStore
from hermes_pipeline.runtime_broker.binding import AgentBinding, BindingTable
from hermes_pipeline.runtime_broker.ports import (
    RuntimeHandle,
    RuntimeLaunchRequest,
    RuntimeOutcome,
    RuntimeSignalReceipt,
    RuntimeSnapshot,
)
from hermes_pipeline.stage_executor.architecture import (
    ARCH_BYTES,
    TESTPLAN_BYTES,
    ArchitectureGate,
    ArchitectureStage,
)
from hermes_pipeline.stage_executor.prd import PRD_BYTES, PrdStage

_RECORDED = "2026-01-01T00:00:00Z"


def _actor() -> Actor:
    return Actor(principal_id="alice", provider="CLI", provider_actor_id="alice")


def _open_with_prd(tmp_path: Path) -> tuple[KernelController, LocalCasArtifacts, str]:
    store = MemoryKernelStore()
    controller = KernelController(store, recorded_at=_RECORDED)
    registry = ProjectRegistry()
    registry.register("prj_demo", "Demo")
    registry.admit("prj_demo", "alice", "CONTRIBUTOR")
    intake = RequirementIntake(registry, controller, recorded_at=_RECORDED)
    assert (
        intake.confirm(
            workspace_id="ws_demo",
            project_id="prj_demo",
            pipeline_id="pl_demo",
            actor=_actor(),
            text="need a login page",
            command_id="cmd_intake_alice",
        ).status
        == "ACCEPTED"
    )
    artifacts = LocalCasArtifacts(tmp_path)
    bindings = BindingTable({"planner": AgentBinding("planner", "fake", "fake-plan")})
    prd = PrdStage(bindings, artifacts).run("pl_demo", "ws_demo", "prj_demo")
    assert prd.status == "COMPLETED"
    assert prd.artifact_id is not None
    return controller, artifacts, prd.artifact_id


def test_architecture_writes_design_and_testplan(tmp_path: Path) -> None:
    controller, artifacts, prd_id = _open_with_prd(tmp_path)
    bindings = BindingTable({"planner": AgentBinding("planner", "fake", "fake-plan")})
    stage = ArchitectureStage(bindings, artifacts)
    result = stage.run(prd_artifact_id=prd_id)
    assert result.status == "COMPLETED"
    assert result.design_id is not None
    assert result.testplan_id is not None
    assert artifacts.open(result.design_id) == ARCH_BYTES
    assert artifacts.open(result.testplan_id) == TESTPLAN_BYTES
    assert artifacts.open(prd_id) == PRD_BYTES
    verdict = ArchitectureGate(controller, artifacts).evaluate(
        pipeline_id="pl_demo",
        workspace_id="ws_demo",
        prd_artifact_id=prd_id,
        result=result,
    )
    assert verdict.status == "PASS"


def test_requirement_question_does_not_rewrite_prd(tmp_path: Path) -> None:
    controller, artifacts, prd_id = _open_with_prd(tmp_path)
    bindings = BindingTable({"planner": AgentBinding("planner", "fake", "fake-plan")})
    result = ArchitectureStage(bindings, artifacts).run(
        prd_artifact_id=prd_id, question="which auth provider?"
    )
    assert result.status == "QUESTION"
    assert result.question == "which auth provider?"
    assert result.design_id is None
    assert artifacts.open(prd_id) == PRD_BYTES
    verdict = ArchitectureGate(controller, artifacts).evaluate(
        pipeline_id="pl_demo",
        workspace_id="ws_demo",
        prd_artifact_id=prd_id,
        result=result,
    )
    assert verdict.status == "FAIL"


class _TextPlanner:
    def __init__(self, text: str) -> None:
        self.text = text

    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        return RuntimeHandle(runtime_id=request.runtime_id, status="COMPLETED")

    def signal(self, runtime_id: str) -> RuntimeSignalReceipt:
        del runtime_id
        return RuntimeSignalReceipt(ok=False, code="UNSUPPORTED")

    def inspect(self, runtime_id: str) -> RuntimeSnapshot:
        return RuntimeSnapshot(runtime_id=runtime_id, status="COMPLETED")

    def collect(self, runtime_id: str) -> RuntimeOutcome:
        return RuntimeOutcome(
            runtime_id=runtime_id, status="COMPLETED", final_text=self.text
        )


def test_bound_planner_stdout_becomes_design(tmp_path: Path) -> None:
    _controller, artifacts, prd_id = _open_with_prd(tmp_path)
    bindings = BindingTable(
        {"planner": AgentBinding("planner", "opencode", "grok-4.6")}
    )
    result = ArchitectureStage(bindings, artifacts, _TextPlanner("real design")).run(
        prd_artifact_id=prd_id, pipeline_id="pl_demo", prompt="Write architecture"
    )
    assert result.status == "COMPLETED"
    assert result.design_id is not None
    assert result.testplan_id is not None
    assert artifacts.open(result.design_id) == b"real design"
    assert artifacts.open(result.testplan_id) == b"real design"


def test_missing_prd_or_binding_is_denied(tmp_path: Path) -> None:
    artifacts = LocalCasArtifacts(tmp_path)
    empty = ArchitectureStage(BindingTable({}), artifacts)
    assert empty.run(prd_artifact_id="art_missing").status == "DENIED"
    bindings = BindingTable({"planner": AgentBinding("planner", "fake", "fake-plan")})
    denied = ArchitectureStage(bindings, artifacts).run(prd_artifact_id="art_missing")
    assert denied.status == "DENIED"
