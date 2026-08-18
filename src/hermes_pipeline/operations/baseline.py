"""Solution Baseline Approval and stale-decision protection (slice 03-04)."""

from __future__ import annotations

from dataclasses import dataclass

from hermes_pipeline.operations.projects import ProjectRegistry


@dataclass(frozen=True)
class ApprovedBaseline:
    pipeline_id: str
    approver_id: str
    prd_id: str
    design_id: str
    testplan_id: str


class SolutionApproval:
    def __init__(self, registry: ProjectRegistry) -> None:
        self._registry = registry
        self._designated: dict[str, str] = {}
        self._approved: dict[str, ApprovedBaseline] = {}

    def designate(self, pipeline_id: str, project_id: str, principal_id: str) -> None:
        if self._registry.role_of(project_id, principal_id) is None:
            raise PermissionError(principal_id)
        self._designated[pipeline_id] = principal_id

    def approve(
        self,
        *,
        pipeline_id: str,
        project_id: str,
        actor_id: str,
        prd_id: str,
        design_id: str,
        testplan_id: str,
    ) -> ApprovedBaseline:
        if self._designated.get(pipeline_id) != actor_id:
            raise PermissionError(actor_id)
        if self._registry.role_of(project_id, actor_id) is None:
            raise PermissionError(actor_id)
        baseline = ApprovedBaseline(
            pipeline_id=pipeline_id,
            approver_id=actor_id,
            prd_id=prd_id,
            design_id=design_id,
            testplan_id=testplan_id,
        )
        self._approved[pipeline_id] = baseline
        return baseline

    def current(self, pipeline_id: str) -> ApprovedBaseline | None:
        return self._approved.get(pipeline_id)

    def is_fresh(
        self,
        *,
        pipeline_id: str,
        prd_id: str,
        design_id: str,
        testplan_id: str,
    ) -> bool:
        baseline = self._approved.get(pipeline_id)
        if baseline is None:
            return False
        return (
            baseline.prd_id == prd_id
            and baseline.design_id == design_id
            and baseline.testplan_id == testplan_id
        )


__all__ = ["ApprovedBaseline", "SolutionApproval"]
