"""Deterministic Stage Executor Adapter with no LangGraph import.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from hermes_pipeline.stage_executor.ports import (
    CancelReceipt,
    ExecutionCancelRequest,
    ExecutionHandle,
    ExecutionInput,
    ExecutionSnapshot,
    ResumeInput,
    StageStatus,
)


class FakeStageExecutor:
    def __init__(self) -> None:
        self._status: dict[str, StageStatus] = {}

    def start(self, execution_input: ExecutionInput) -> ExecutionHandle:
        self._status[execution_input.run_id] = "PENDING"
        return ExecutionHandle(run_id=execution_input.run_id, status="PENDING")

    def resume(self, resume_input: ResumeInput) -> ExecutionHandle:
        status = self._status.get(resume_input.run_id, "UNSUPPORTED")
        if status == "CANCELLED":
            return ExecutionHandle(run_id=resume_input.run_id, status="CANCELLED")
        self._status[resume_input.run_id] = "PENDING"
        return ExecutionHandle(run_id=resume_input.run_id, status="PENDING")

    def cancel(self, cancel_request: ExecutionCancelRequest) -> CancelReceipt:
        self._status[cancel_request.run_id] = "CANCELLED"
        return CancelReceipt(run_id=cancel_request.run_id, status="CANCELLED")

    def inspect(self, run_id: str) -> ExecutionSnapshot:
        return ExecutionSnapshot(
            run_id=run_id, status=self._status.get(run_id, "UNSUPPORTED")
        )


__all__ = ["FakeStageExecutor"]
