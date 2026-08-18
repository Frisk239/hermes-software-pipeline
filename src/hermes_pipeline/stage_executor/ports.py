"""Public Stage Executor Interface adopted by Slice 00-07.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

StageStatus = Literal["PENDING", "CANCELLED", "UNSUPPORTED", "COMPLETED", "DENIED"]


@dataclass(frozen=True)
class ExecutionInput:
    run_id: str


@dataclass(frozen=True)
class ResumeInput:
    run_id: str


@dataclass(frozen=True)
class ExecutionCancelRequest:
    run_id: str


@dataclass(frozen=True)
class ExecutionHandle:
    run_id: str
    status: StageStatus


@dataclass(frozen=True)
class ExecutionSnapshot:
    run_id: str
    status: StageStatus


@dataclass(frozen=True)
class CancelReceipt:
    run_id: str
    status: StageStatus


@runtime_checkable
class StageExecutorPort(Protocol):
    def start(self, execution_input: ExecutionInput) -> ExecutionHandle:
        """Start one Execution Run."""
        ...

    def resume(self, resume_input: ResumeInput) -> ExecutionHandle:
        """Resume one Execution Run."""
        ...

    def cancel(self, cancel_request: ExecutionCancelRequest) -> CancelReceipt:
        """Cancel one Execution Run."""
        ...

    def inspect(self, run_id: str) -> ExecutionSnapshot:
        """Inspect one Execution Run."""
        ...


__all__ = [
    "CancelReceipt",
    "ExecutionCancelRequest",
    "ExecutionHandle",
    "ExecutionInput",
    "ExecutionSnapshot",
    "ResumeInput",
    "StageExecutorPort",
    "StageStatus",
]
