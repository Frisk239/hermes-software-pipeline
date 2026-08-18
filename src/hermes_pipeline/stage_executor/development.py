"""Development Stage plus Candidate under an approved baseline (03-05).

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from hermes_pipeline.artifacts.ports import ArtifactPutRequest, ArtifactsPort
from hermes_pipeline.operations.baseline import SolutionApproval
from hermes_pipeline.repository.worktree import (
    SECRET_CANARY,
    CandidateRecord,
    ManagedWorktree,
)
from hermes_pipeline.runtime_broker.binding import BindingNotFound, BindingTable
from hermes_pipeline.runtime_broker.ports import RuntimeBrokerPort, RuntimeLaunchRequest

IMPL_NAME = "src/app.py"
IMPL_BYTES = b"print('login-page')\n"

DevelopmentStatus = Literal["COMPLETED", "DENIED"]
CandidateGateStatus = Literal["PASS", "FAIL"]


@dataclass(frozen=True)
class DevelopmentResult:
    status: DevelopmentStatus
    artifact_id: str | None = None
    candidate: CandidateRecord | None = None


@dataclass(frozen=True)
class CandidateGateVerdict:
    status: CandidateGateStatus


class DevelopmentStage:
    def __init__(
        self,
        bindings: BindingTable,
        approval: SolutionApproval,
        artifacts: ArtifactsPort,
        worktree: ManagedWorktree,
        executor: RuntimeBrokerPort | None = None,
    ) -> None:
        self._bindings = bindings
        self._approval = approval
        self._artifacts = artifacts
        self._worktree = worktree
        self._executor = executor

    def run(
        self,
        *,
        pipeline_id: str,
        prd_id: str,
        design_id: str,
        testplan_id: str,
        payload: bytes = IMPL_BYTES,
        relative_path: str = IMPL_NAME,
    ) -> DevelopmentResult:
        try:
            binding = self._bindings.resolve("executor")
        except BindingNotFound:
            return DevelopmentResult(status="DENIED")
        if not self._approval.is_fresh(
            pipeline_id=pipeline_id,
            prd_id=prd_id,
            design_id=design_id,
            testplan_id=testplan_id,
        ):
            return DevelopmentResult(status="DENIED")
        if binding.runtime == "fake":
            try:
                written = self._worktree.write(relative_path, payload)
            except ValueError:
                return DevelopmentResult(status="DENIED")
            body = payload
        else:
            harvested = self._run_bound_executor(pipeline_id, binding.model)
            if harvested is None:
                return DevelopmentResult(status="DENIED")
            written, body = harvested
        record = self._artifacts.put(ArtifactPutRequest(payload=body))
        candidate = CandidateRecord(
            sha=self._worktree.candidate_sha(),
            relative_path=written.relative_to(self._worktree.root).as_posix(),
        )
        return DevelopmentResult(
            status="COMPLETED",
            artifact_id=record.artifact_id,
            candidate=candidate,
        )

    def _run_bound_executor(
        self, pipeline_id: str, model: str
    ) -> tuple[Path, bytes] | None:
        if self._executor is None:
            return None
        handle = self._executor.launch(
            RuntimeLaunchRequest(
                runtime_id=f"dev-{pipeline_id}",
                role="executor",
                model=model,
            )
        )
        if handle.status != "COMPLETED":
            return None
        files = self._worktree.files()
        if not files:
            return None
        written = files[0]
        body = written.read_bytes()
        if SECRET_CANARY.encode("utf-8") in body:
            return None
        return written, body


class CandidateGate:
    def __init__(self, approval: SolutionApproval, artifacts: ArtifactsPort) -> None:
        self._approval = approval
        self._artifacts = artifacts

    def evaluate(
        self,
        *,
        pipeline_id: str,
        prd_id: str,
        design_id: str,
        testplan_id: str,
        result: DevelopmentResult,
    ) -> CandidateGateVerdict:
        if result.status != "COMPLETED" or result.artifact_id is None:
            return CandidateGateVerdict(status="FAIL")
        if result.candidate is None or len(result.candidate.sha) != 64:
            return CandidateGateVerdict(status="FAIL")
        if not self._approval.is_fresh(
            pipeline_id=pipeline_id,
            prd_id=prd_id,
            design_id=design_id,
            testplan_id=testplan_id,
        ):
            return CandidateGateVerdict(status="FAIL")
        if not self._artifacts.verify(result.artifact_id).ok:
            return CandidateGateVerdict(status="FAIL")
        return CandidateGateVerdict(status="PASS")


__all__ = [
    "IMPL_BYTES",
    "IMPL_NAME",
    "CandidateGate",
    "CandidateGateVerdict",
    "DevelopmentResult",
    "DevelopmentStage",
]
