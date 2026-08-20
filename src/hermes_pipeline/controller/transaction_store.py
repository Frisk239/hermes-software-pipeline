"""Private Controller transaction store port (slices 01-02 through 01-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_PHASE_01
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast, runtime_checkable


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


_STAGE_EVENTS = {
    "PRD_RECORDED": "prd",
    "ARCHITECTURE_RECORDED": "architecture",
    "DEVELOPMENT_RECORDED": "development",
    "VERIFY_RECORDED": "verify",
    "APPROVAL_RECORDED": "approval",
}


def fold_pipeline_events(
    workspace_id: str, pipeline_id: str, events: list[EventWrite]
) -> PipelineSnapshot:
    status: Literal["UNCONFIRMED", "OPEN", "REJECTED"] = "UNCONFIRMED"
    revision = 0
    text = ""
    for event in events:
        revision = event.pipeline_revision
        if event.event_type == "REQUIREMENT_CONFIRMED":
            status = "OPEN"
            payload = json.loads(event.payload_json)
            text = str(payload.get("text", ""))
        elif event.event_type == "REQUIREMENT_REJECTED":
            status = "REJECTED"
    return PipelineSnapshot(
        workspace_id=workspace_id,
        pipeline_id=pipeline_id,
        status=status,
        revision=revision,
        text=text,
    )


def fold_stage_projection(events: list[EventWrite]) -> dict[str, str]:
    folded: dict[str, str] = {}
    for event in events:
        if event.event_type not in _STAGE_EVENTS:
            continue
        try:
            payload = json.loads(event.payload_json)
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        typed = cast(dict[str, Any], payload)
        for raw_key, raw_value in typed.items():
            key = str(raw_key)
            if key == "station":
                continue
            folded[key] = str(raw_value)
    return folded


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

    def delete_lease(self, workspace_id: str, pipeline_id: str) -> None: ...

    def delete_expired_leases(self, now: int) -> None: ...

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
    "fold_stage_projection",
]
