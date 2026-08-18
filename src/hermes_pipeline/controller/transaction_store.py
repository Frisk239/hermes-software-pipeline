"""Private Controller transaction store port (slices 01-02 through 01-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_PHASE_01
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


class PersistenceError(Exception):
    def __init__(self, message: str = "persistence unavailable") -> None:
        super().__init__(message)


class OutboxNotFound(Exception):
    def __init__(self, message: str = "outbox not found") -> None:
        super().__init__(message)


class LeaseError(Exception):
    def __init__(self, message: str = "lease rejected") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class InboxRecord:
    workspace_id: str
    command_id: str
    command_fingerprint: str
    receipt_json: str


@dataclass(frozen=True)
class EventWrite:
    event_id: str
    workspace_id: str
    pipeline_id: str
    event_type: str
    payload_json: str
    pipeline_revision: int


@dataclass(frozen=True)
class PipelineSnapshot:
    workspace_id: str
    pipeline_id: str
    status: str
    revision: int
    text: str


@dataclass(frozen=True)
class OutboxRecord:
    workspace_id: str
    command_id: str
    effect_type: str
    payload_json: str
    delivery_receipt_json: str | None = None


@dataclass(frozen=True)
class AcceptedWrite:
    inbox: InboxRecord
    event: EventWrite
    pipeline: PipelineSnapshot
    outbox: OutboxRecord


@dataclass(frozen=True)
class LeaseRecord:
    workspace_id: str
    pipeline_id: str
    attempt_id: str
    run_id: str
    holder: str
    generation: int
    expires_at: int

    def __post_init__(self) -> None:
        if self.generation < 1:
            raise ValueError("generation must be >= 1")


@dataclass(frozen=True)
class StoreCounts:
    inbox: int
    events: int
    pipelines: int
    outbox: int


def fold_pipeline_events(
    workspace_id: str, pipeline_id: str, events: list[EventWrite]
) -> PipelineSnapshot:
    status: Literal["UNCONFIRMED", "OPEN", "REJECTED"] = "UNCONFIRMED"
    revision = 0
    text = ""
    for event in events:
        if event.event_type == "REQUIREMENT_CONFIRMED":
            status = "OPEN"
            revision = event.pipeline_revision
            payload = json.loads(event.payload_json)
            text = str(payload.get("text", ""))
        elif event.event_type == "REQUIREMENT_REJECTED":
            status = "REJECTED"
            revision = event.pipeline_revision
    return PipelineSnapshot(
        workspace_id=workspace_id,
        pipeline_id=pipeline_id,
        status=status,
        revision=revision,
        text=text,
    )


@runtime_checkable
class ControllerTransactionStore(Protocol):
    def find_inbox(self, workspace_id: str, command_id: str) -> InboxRecord | None: ...

    def load_pipeline(
        self, workspace_id: str, pipeline_id: str
    ) -> PipelineSnapshot | None: ...

    def commit_accepted(self, write: AcceptedWrite) -> None: ...

    def list_events(self, workspace_id: str, pipeline_id: str) -> list[EventWrite]: ...

    def rebuild_pipeline(
        self, workspace_id: str, pipeline_id: str
    ) -> PipelineSnapshot: ...

    def delete_pipeline(self, workspace_id: str, pipeline_id: str) -> None: ...

    def list_pending_outbox(self, workspace_id: str) -> list[OutboxRecord]: ...

    def record_outbox_delivery(
        self, workspace_id: str, command_id: str, delivery_receipt_json: str
    ) -> None: ...

    def find_outbox(
        self, workspace_id: str, command_id: str
    ) -> OutboxRecord | None: ...

    def load_lease(self, workspace_id: str, pipeline_id: str) -> LeaseRecord | None: ...

    def save_lease(self, record: LeaseRecord) -> None: ...

    def counts(self) -> StoreCounts: ...

    def close(self) -> None: ...


__all__ = [
    "AcceptedWrite",
    "ControllerTransactionStore",
    "EventWrite",
    "InboxRecord",
    "LeaseError",
    "LeaseRecord",
    "OutboxNotFound",
    "OutboxRecord",
    "PersistenceError",
    "PipelineSnapshot",
    "StoreCounts",
    "fold_pipeline_events",
]
