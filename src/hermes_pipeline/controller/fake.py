"""Deterministic in-memory Controller Adapter.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import (
    CommandError,
    CommandReceipt,
    ControllerCommand,
)
from hermes_pipeline.controller.ports import PipelineQuery, PipelineView

_RECORDED_AT = UtcTimestampRef("2026-01-01T00:00:00Z")


class FakeController:
    def __init__(self) -> None:
        self.last_submit: ControllerCommand | None = None

    def submit(self, command: ControllerCommand) -> CommandReceipt:
        self.last_submit = command
        return CommandReceipt(
            schema_id="https://schemas.hermes-pipeline.dev/runtime/command-receipt/v1",
            schema_version=FixedV1Integer(1),
            command_id=command.command_id,
            status="ACCEPTED",
            pipeline_id=command.pipeline_id,
            observed_revision=0,
            event_ids=[],
            error=CommandError(code="INTERNAL_ERROR", message="", retryable=False),
            recorded_at=_RECORDED_AT,
            correlation_id=command.correlation_id,
        )

    def read(self, query: PipelineQuery) -> PipelineView:
        return PipelineView(pipeline_id=query.pipeline_id, revision=0, status="UNKNOWN")


__all__ = ["FakeController"]
