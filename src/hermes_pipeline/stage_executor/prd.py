"""Deterministic PRD Stage and automatic Gate (slice 03-02).

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from hermes_pipeline.artifacts.local_cas import ArtifactNotFound
from hermes_pipeline.artifacts.ports import ArtifactPutRequest, ArtifactsPort
from hermes_pipeline.controller.ports import ControllerPort, PipelineQuery
from hermes_pipeline.runtime_broker.binding import BindingNotFound, BindingTable
from hermes_pipeline.runtime_broker.ports import RuntimeBrokerPort, RuntimeLaunchRequest
from hermes_pipeline.stage_executor.contracts import prd_shape_ok
from hermes_pipeline.stage_executor.harvest import PRD_NAMES, named_file_bytes

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
    def __init__(
        self,
        bindings: BindingTable,
        artifacts: ArtifactsPort,
        planner: RuntimeBrokerPort | None = None,
        folder: Path | None = None,
    ) -> None:
        self._bindings = bindings
        self._artifacts = artifacts
        self._planner = planner
        self._folder = folder

    def run(
        self,
        pipeline_id: str,
        workspace_id: str,
        project_id: str,
        prompt: str = "",
    ) -> PrdStageResult:
        del workspace_id, project_id
        try:
            binding = self._bindings.resolve("planner")
        except BindingNotFound:
            return PrdStageResult(status="DENIED")
        if binding.runtime == "fake":
            body = PRD_BYTES
        else:
            harvested = self._run_bound_planner(pipeline_id, binding.model, prompt)
            if harvested is None:
                return PrdStageResult(status="DENIED")
            body = harvested
        record = self._artifacts.put(ArtifactPutRequest(payload=body))
        return PrdStageResult(status="COMPLETED", artifact_id=record.artifact_id)

    def _run_bound_planner(
        self, pipeline_id: str, model: str, prompt: str
    ) -> bytes | None:
        if self._planner is None:
            return None
        runtime_id = f"prd-{pipeline_id}"
        self._planner.launch(
            RuntimeLaunchRequest(
                runtime_id=runtime_id,
                role="planner",
                model=model,
                prompt=prompt,
            )
        )
        return named_file_bytes(self._folder, PRD_NAMES)


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
        try:
            body = self._artifacts.open(artifact_id)
        except (OSError, KeyError, ValueError, ArtifactNotFound):
            return PrdGateVerdict(status="FAIL")
        if not prd_shape_ok(body):
            return PrdGateVerdict(status="FAIL")
        return PrdGateVerdict(status="PASS")


__all__ = [
    "PRD_BYTES",
    "PrdGate",
    "PrdGateVerdict",
    "PrdStage",
    "PrdStageResult",
]
