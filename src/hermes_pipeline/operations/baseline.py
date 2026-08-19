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
        role = self._registry.role_of(project_id, principal_id)
        if role is None or role == "VIEWER":
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
        role = self._registry.role_of(project_id, actor_id)
        if role is None or role == "VIEWER":
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

    def dump(self) -> dict[str, dict[str, str]]:
        dumped: dict[str, dict[str, str]] = {}
        for pipeline_id, baseline in self._approved.items():
            dumped[pipeline_id] = {
                "approval_status": "APPROVED",
                "approver_id": baseline.approver_id,
                "prd_id": baseline.prd_id,
                "design_id": baseline.design_id,
                "testplan_id": baseline.testplan_id,
                "designated_id": self._designated.get(
                    pipeline_id, baseline.approver_id
                ),
            }
        return dumped

    def restore(self, document: dict[str, dict[str, str]]) -> None:
        for pipeline_id, row in document.items():
            if row.get("approval_status") != "APPROVED":
                continue
            actor = row.get("approver_id", "")
            if not actor:
                continue
            self._designated[pipeline_id] = row.get("designated_id", "") or actor
            self._approved[pipeline_id] = ApprovedBaseline(
                pipeline_id=pipeline_id,
                approver_id=actor,
                prd_id=row.get("prd_id", ""),
                design_id=row.get("design_id", ""),
                testplan_id=row.get("testplan_id", ""),
            )

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
