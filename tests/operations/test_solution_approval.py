from __future__ import annotations

import pytest

from hermes_pipeline.operations.baseline import SolutionApproval
from hermes_pipeline.operations.projects import ProjectRegistry


def _approval() -> SolutionApproval:
    registry = ProjectRegistry()
    registry.register("prj_demo", "Demo")
    registry.admit("prj_demo", "approver", "ADMIN")
    registry.admit("prj_demo", "alice", "CONTRIBUTOR")
    approval = SolutionApproval(registry)
    approval.designate("pl_demo", "prj_demo", "approver")
    return approval


def test_designated_approver_freezes_baseline() -> None:
    approval = _approval()
    baseline = approval.approve(
        pipeline_id="pl_demo",
        project_id="prj_demo",
        actor_id="approver",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert baseline.approver_id == "approver"
    assert approval.is_fresh(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert approval.current("pl_demo") == baseline


def test_non_approver_cannot_approve() -> None:
    approval = _approval()
    with pytest.raises(PermissionError):
        approval.approve(
            pipeline_id="pl_demo",
            project_id="prj_demo",
            actor_id="alice",
            prd_id="art_prd",
            design_id="art_design",
            testplan_id="art_test",
        )
    assert approval.current("pl_demo") is None
    assert not approval.is_fresh(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )


def test_changed_artifact_is_stale() -> None:
    approval = _approval()
    approval.approve(
        pipeline_id="pl_demo",
        project_id="prj_demo",
        actor_id="approver",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert not approval.is_fresh(
        pipeline_id="pl_demo",
        prd_id="art_prd_v2",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert not approval.is_fresh(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design_v2",
        testplan_id="art_test",
    )


def test_viewer_cannot_designate_or_approve() -> None:
    registry = ProjectRegistry()
    registry.register("prj_demo", "Demo")
    registry.admit("prj_demo", "viewer", "VIEWER")
    approval = SolutionApproval(registry)
    with pytest.raises(PermissionError):
        approval.designate("pl_demo", "prj_demo", "viewer")


def test_restore_keeps_fresh_baseline() -> None:
    first = _approval()
    first.approve(
        pipeline_id="pl_demo",
        project_id="prj_demo",
        actor_id="approver",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    registry = ProjectRegistry()
    registry.register("prj_demo", "Demo")
    registry.admit("prj_demo", "approver", "ADMIN")
    second = SolutionApproval(registry)
    second.restore(first.dump())
    assert second.is_fresh(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )


def test_undesignated_member_cannot_be_approver() -> None:
    registry = ProjectRegistry()
    registry.register("prj_demo", "Demo")
    approval = SolutionApproval(registry)
    with pytest.raises(PermissionError):
        approval.designate("pl_demo", "prj_demo", "stranger")
