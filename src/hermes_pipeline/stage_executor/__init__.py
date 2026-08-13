"""stage_executor Module — public start/resume/cancel/inspect Interface.

Stage execution workflows. The Module boundary is fixed by
``docs/architecture/system-and-module-design.md``. LangGraph belongs only
inside this Module's keep-marked spike Adapter.
"""

from hermes_pipeline.stage_executor.fake import FakeStageExecutor
from hermes_pipeline.stage_executor.ports import (
    CancelReceipt,
    ExecutionCancelRequest,
    ExecutionHandle,
    ExecutionInput,
    ExecutionSnapshot,
    ResumeInput,
    StageExecutorPort,
)

__all__ = [
    "CancelReceipt",
    "ExecutionCancelRequest",
    "ExecutionHandle",
    "ExecutionInput",
    "ExecutionSnapshot",
    "FakeStageExecutor",
    "ResumeInput",
    "StageExecutorPort",
]
