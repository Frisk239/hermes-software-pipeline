"""Deterministic PRD Stage and automatic Gate (slice 03-02).

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from hermes_pipeline.artifacts.ports import ArtifactPutRequest, ArtifactsPort
from hermes_pipeline.controller.ports import ControllerPort, PipelineQuery
from hermes_pipeline.repository.worktree import SECRET_CANARY
from hermes_pipeline.runtime_broker.binding import BindingNotFound, BindingTable
from hermes_pipeline.runtime_broker.ports import RuntimeBrokerPort, RuntimeLaunchRequest

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
        handle = self._planner.launch(
            RuntimeLaunchRequest(
                runtime_id=runtime_id,
                role="planner",
                model=model,
                prompt=prompt,
            )
        )
        if handle.status != "COMPLETED":
            return None
        text = self._planner.collect(runtime_id).final_text.strip()
        if text:
            return text.encode("utf-8")
        return _first_file_bytes(self._folder)


def _first_file_bytes(folder: Path | None) -> bytes | None:
    if folder is None or not folder.is_dir():
        return None
    files = [path for path in sorted(folder.rglob("*")) if path.is_file()]
    if not files:
        return None
    body = files[0].read_bytes()
    if SECRET_CANARY.encode("utf-8") in body:
        return None
    return body


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
