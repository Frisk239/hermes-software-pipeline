"""Shared contract tests for the Stage Executor Interface fake."""

from __future__ import annotations

import hermes_pipeline.stage_executor.fake as fake_module
from hermes_pipeline.stage_executor import (
    ExecutionCancelRequest,
    ExecutionInput,
    FakeStageExecutor,
    ResumeInput,
    StageExecutorPort,
)


def test_fake_is_a_stage_executor_port() -> None:
    assert isinstance(FakeStageExecutor(), StageExecutorPort)


def test_fake_module_does_not_import_langgraph() -> None:
    assert "langgraph" not in fake_module.__dict__
    assert all("langgraph" not in name for name in dir(fake_module))


def test_start_inspect_cancel_round_trip() -> None:
    fake = FakeStageExecutor()
    handle = fake.start(ExecutionInput(run_id="run-1"))
    assert handle.status == "PENDING"
    assert fake.inspect("run-1").status == "PENDING"
    receipt = fake.cancel(ExecutionCancelRequest(run_id="run-1"))
    assert receipt.status == "CANCELLED"
    assert fake.inspect("run-1").status == "CANCELLED"


def test_unknown_inspect_is_unsupported() -> None:
    assert FakeStageExecutor().inspect("missing").status == "UNSUPPORTED"


def test_resume_unknown_then_pending() -> None:
    fake = FakeStageExecutor()
    resumed = fake.resume(ResumeInput(run_id="run-2"))
    assert resumed.status == "PENDING"
    assert fake.inspect("run-2").status == "PENDING"
