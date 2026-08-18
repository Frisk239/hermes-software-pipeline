"""Deterministic PRD Stage and automatic Gate (slice 03-02).

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from hermes_pipeline.artifacts.ports import ArtifactPutRequest, ArtifactsPort
from hermes_pipeline.controller.ports import ControllerPort, PipelineQuery
from hermes_pipeline.runtime_broker.binding import BindingNotFound, BindingTable

PRD_BYTES = b"hermes-pipeline-prd-v1\n"

PrdStageStatus = Literal["COMPLETED", "DENIED"]
PrdGateStatus = Literal["PASS", "FAIL"]


@dataclass(frozen=True)
class PrdStageResult:
    status: PrdStageStatus
    artifact_id: str | None = None


@dataclass(frozen=True)
class PrdGateVerdict:
    status: PrdGateStatus


class PrdStage:
    def __init__(self, bindings: BindingTable, artifacts: ArtifactsPort) -> None:
        self._bindings = bindings
        self._artifacts = artifacts

    def run(
        self, pipeline_id: str, workspace_id: str, project_id: str
    ) -> PrdStageResult:
        del pipeline_id, workspace_id, project_id
        try:
            self._bindings.resolve("planner")
        except BindingNotFound:
            return PrdStageResult(status="DENIED")
        record = self._artifacts.put(ArtifactPutRequest(payload=PRD_BYTES))
        return PrdStageResult(status="COMPLETED", artifact_id=record.artifact_id)


class PrdGate:
    def __init__(self, controller: ControllerPort, artifacts: ArtifactsPort) -> None:
        self._controller = controller
        self._artifacts = artifacts

    def evaluate(
        self,
        *,
        pipeline_id: str,
        workspace_id: str,
        artifact_id: str | None,
    ) -> PrdGateVerdict:
        if not artifact_id:
            return PrdGateVerdict(status="FAIL")
        view = self._controller.read(
            PipelineQuery(pipeline_id=pipeline_id, workspace_id=workspace_id)
        )
        if view.status != "OPEN":
            return PrdGateVerdict(status="FAIL")
        if not self._artifacts.verify(artifact_id).ok:
            return PrdGateVerdict(status="FAIL")
        return PrdGateVerdict(status="PASS")


__all__ = [
    "PRD_BYTES",
    "PrdGate",
    "PrdGateVerdict",
    "PrdStage",
    "PrdStageResult",
]
