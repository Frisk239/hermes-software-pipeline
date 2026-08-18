from __future__ import annotations

from pathlib import Path

from hermes_pipeline.artifacts import LocalCasArtifacts
from hermes_pipeline.operations.baseline import SolutionApproval
from hermes_pipeline.operations.projects import ProjectRegistry
from hermes_pipeline.repository.worktree import SECRET_CANARY, ManagedWorktree
from hermes_pipeline.runtime_broker.binding import AgentBinding, BindingTable
from hermes_pipeline.stage_executor.development import (
    IMPL_BYTES,
    CandidateGate,
    DevelopmentStage,
)


def _stage(
    tmp_path: Path,
) -> tuple[DevelopmentStage, SolutionApproval, LocalCasArtifacts]:
    registry = ProjectRegistry()
    registry.register("prj_demo", "Demo")
    registry.admit("prj_demo", "approver", "ADMIN")
    approval = SolutionApproval(registry)
    approval.designate("pl_demo", "prj_demo", "approver")
    approval.approve(
        pipeline_id="pl_demo",
        project_id="prj_demo",
        actor_id="approver",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    artifacts = LocalCasArtifacts(tmp_path / "cas")
    bindings = BindingTable({"executor": AgentBinding("executor", "fake", "fake-dev")})
    stage = DevelopmentStage(
        bindings, approval, artifacts, ManagedWorktree(tmp_path / "wt")
    )
    return stage, approval, artifacts


def test_fresh_baseline_writes_worktree_and_candidate(tmp_path: Path) -> None:
    stage, approval, artifacts = _stage(tmp_path)
    result = stage.run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert result.status == "COMPLETED"
    assert result.artifact_id is not None
    assert result.candidate is not None
    assert len(result.candidate.sha) == 64
    assert artifacts.open(result.artifact_id) == IMPL_BYTES
    assert (tmp_path / "wt" / "src" / "app.py").read_bytes() == IMPL_BYTES
    assert (
        CandidateGate(approval, artifacts)
        .evaluate(
            pipeline_id="pl_demo",
            prd_id="art_prd",
            design_id="art_design",
            testplan_id="art_test",
            result=result,
        )
        .status
        == "PASS"
    )


def test_stale_baseline_or_missing_executor_is_denied(tmp_path: Path) -> None:
    stage, approval, artifacts = _stage(tmp_path)
    stale = stage.run(
        pipeline_id="pl_demo",
        prd_id="art_prd_v2",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert stale.status == "DENIED"
    empty = DevelopmentStage(
        BindingTable({}),
        approval,
        artifacts,
        ManagedWorktree(tmp_path / "wt2"),
    )
    assert (
        empty.run(
            pipeline_id="pl_demo",
            prd_id="art_prd",
            design_id="art_design",
            testplan_id="art_test",
        ).status
        == "DENIED"
    )


def test_secret_or_escape_is_denied(tmp_path: Path) -> None:
    stage, _approval, _artifacts = _stage(tmp_path)
    secret = stage.run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
        payload=f"token={SECRET_CANARY}".encode(),
    )
    assert secret.status == "DENIED"
    escape = stage.run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
        relative_path="../escape.py",
    )
    assert escape.status == "DENIED"
