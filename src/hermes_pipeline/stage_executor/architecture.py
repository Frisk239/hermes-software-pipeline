"""Architecture Stage, test plan, and Requirement Question (slice 03-03).

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from hermes_pipeline.artifacts.ports import ArtifactPutRequest, ArtifactsPort
from hermes_pipeline.controller.ports import ControllerPort, PipelineQuery
from hermes_pipeline.runtime_broker.binding import BindingNotFound, BindingTable

ARCH_BYTES = b"hermes-pipeline-architecture-v1\n"
TESTPLAN_BYTES = b"hermes-pipeline-testplan-v1\n"

ArchitectureStatus = Literal["COMPLETED", "DENIED", "QUESTION"]
ArchitectureGateStatus = Literal["PASS", "FAIL"]


@dataclass(frozen=True)
class ArchitectureResult:
    status: ArchitectureStatus
    design_id: str | None = None
    testplan_id: str | None = None
    question: str | None = None


@dataclass(frozen=True)
class ArchitectureGateVerdict:
    status: ArchitectureGateStatus


class ArchitectureStage:
    def __init__(self, bindings: BindingTable, artifacts: ArtifactsPort) -> None:
        self._bindings = bindings
        self._artifacts = artifacts

    def run(
        self,
        *,
        prd_artifact_id: str,
        question: str | None = None,
    ) -> ArchitectureResult:
        try:
            self._bindings.resolve("planner")
        except BindingNotFound:
            return ArchitectureResult(status="DENIED")
        if not self._artifacts.verify(prd_artifact_id).ok:
            return ArchitectureResult(status="DENIED")
        if question:
            return ArchitectureResult(status="QUESTION", question=question)
        design = self._artifacts.put(ArtifactPutRequest(payload=ARCH_BYTES))
        testplan = self._artifacts.put(ArtifactPutRequest(payload=TESTPLAN_BYTES))
        return ArchitectureResult(
            status="COMPLETED",
            design_id=design.artifact_id,
            testplan_id=testplan.artifact_id,
        )


class ArchitectureGate:
    def __init__(self, controller: ControllerPort, artifacts: ArtifactsPort) -> None:
        self._controller = controller
        self._artifacts = artifacts

    def evaluate(
        self,
        *,
        pipeline_id: str,
        workspace_id: str,
        prd_artifact_id: str | None,
        result: ArchitectureResult,
    ) -> ArchitectureGateVerdict:
        if result.status != "COMPLETED":
            return ArchitectureGateVerdict(status="FAIL")
        if not prd_artifact_id or not result.design_id or not result.testplan_id:
            return ArchitectureGateVerdict(status="FAIL")
        view = self._controller.read(
            PipelineQuery(pipeline_id=pipeline_id, workspace_id=workspace_id)
        )
        if view.status != "OPEN":
            return ArchitectureGateVerdict(status="FAIL")
        if not self._artifacts.verify(prd_artifact_id).ok:
            return ArchitectureGateVerdict(status="FAIL")
        if not self._artifacts.verify(result.design_id).ok:
            return ArchitectureGateVerdict(status="FAIL")
        if not self._artifacts.verify(result.testplan_id).ok:
            return ArchitectureGateVerdict(status="FAIL")
        return ArchitectureGateVerdict(status="PASS")


__all__ = [
    "ARCH_BYTES",
    "TESTPLAN_BYTES",
    "ArchitectureGate",
    "ArchitectureGateVerdict",
    "ArchitectureResult",
    "ArchitectureStage",
]
