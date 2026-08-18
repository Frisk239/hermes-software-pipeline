"""Deterministic fake Stage on the real Executor / Broker / CAS ports.

DISPOSITION: ADOPTED_BY_02-03
"""

from __future__ import annotations

from hermes_pipeline.artifacts.ports import ArtifactPutRequest, ArtifactsPort
from hermes_pipeline.contracts.runtime import CapabilityProfile
from hermes_pipeline.runtime_broker.capability import CapabilityRequest, evaluate
from hermes_pipeline.runtime_broker.ports import RuntimeBrokerPort, RuntimeLaunchRequest
from hermes_pipeline.stage_executor.ports import (
    CancelReceipt,
    ExecutionCancelRequest,
    ExecutionHandle,
    ExecutionInput,
    ExecutionSnapshot,
    ResumeInput,
    StageStatus,
)

FAKE_STAGE_BYTES = b"hermes-pipeline-fake-stage-v1\n"
_SIDE_EFFECT = "LOCAL_TEST"


class FakeStageRun:
    def __init__(
        self,
        broker: RuntimeBrokerPort,
        artifacts: ArtifactsPort,
        profile: CapabilityProfile,
    ) -> None:
        self._broker = broker
        self._artifacts = artifacts
        self._profile = profile
        self._status: dict[str, StageStatus] = {}

    def start(self, execution_input: ExecutionInput) -> ExecutionHandle:
        existing = self._status.get(execution_input.run_id)
        if existing is not None:
            return ExecutionHandle(run_id=execution_input.run_id, status=existing)
        if not evaluate(
            self._profile, CapabilityRequest("SIDE_EFFECT", _SIDE_EFFECT)
        ).allowed:
            self._status[execution_input.run_id] = "DENIED"
            return ExecutionHandle(run_id=execution_input.run_id, status="DENIED")
        self._broker.launch(RuntimeLaunchRequest(runtime_id=execution_input.run_id))
        self._artifacts.put(ArtifactPutRequest(payload=FAKE_STAGE_BYTES))
        self._status[execution_input.run_id] = "COMPLETED"
        return ExecutionHandle(run_id=execution_input.run_id, status="COMPLETED")

    def resume(self, resume_input: ResumeInput) -> ExecutionHandle:
        status = self._status.get(resume_input.run_id, "UNSUPPORTED")
        return ExecutionHandle(run_id=resume_input.run_id, status=status)

    def cancel(self, cancel_request: ExecutionCancelRequest) -> CancelReceipt:
        self._status[cancel_request.run_id] = "CANCELLED"
        return CancelReceipt(run_id=cancel_request.run_id, status="CANCELLED")

    def inspect(self, run_id: str) -> ExecutionSnapshot:
        return ExecutionSnapshot(
            run_id=run_id, status=self._status.get(run_id, "UNSUPPORTED")
        )


__all__ = ["FAKE_STAGE_BYTES", "FakeStageRun"]
