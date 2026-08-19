"""Architecture Stage, test plan, and Requirement Question (slice 03-03).

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from hermes_pipeline.artifacts.ports import ArtifactPutRequest, ArtifactsPort
from hermes_pipeline.controller.ports import ControllerPort, PipelineQuery
from hermes_pipeline.runtime_broker.binding import BindingNotFound, BindingTable
from hermes_pipeline.runtime_broker.ports import RuntimeBrokerPort, RuntimeLaunchRequest
from hermes_pipeline.stage_executor.harvest import (
    DESIGN_NAMES,
    TESTPLAN_NAMES,
    named_file_bytes,
)

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
        *,
        prd_artifact_id: str,
        question: str | None = None,
        pipeline_id: str = "",
        prompt: str = "",
    ) -> ArchitectureResult:
        try:
            binding = self._bindings.resolve("planner")
        except BindingNotFound:
            return ArchitectureResult(status="DENIED")
        if not self._artifacts.verify(prd_artifact_id).ok:
            return ArchitectureResult(status="DENIED")
        if question:
            return ArchitectureResult(status="QUESTION", question=question)
        if binding.runtime == "fake":
            design_body = ARCH_BYTES
            testplan_body = TESTPLAN_BYTES
        else:
            harvested = self._run_bound_planner(pipeline_id, binding.model, prompt)
            if harvested is None:
                return ArchitectureResult(status="DENIED")
            design_body, testplan_body = harvested
        design = self._artifacts.put(ArtifactPutRequest(payload=design_body))
        testplan = self._artifacts.put(ArtifactPutRequest(payload=testplan_body))
        return ArchitectureResult(
            status="COMPLETED",
            design_id=design.artifact_id,
            testplan_id=testplan.artifact_id,
        )

    def _run_bound_planner(
        self, pipeline_id: str, model: str, prompt: str
    ) -> tuple[bytes, bytes] | None:
        if self._planner is None:
            return None
        runtime_id = f"arch-{pipeline_id or 'local'}"
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
        design = named_file_bytes(self._folder, DESIGN_NAMES)
        testplan = named_file_bytes(self._folder, TESTPLAN_NAMES)
        if design is None or testplan is None:
            return None
        return design, testplan


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
