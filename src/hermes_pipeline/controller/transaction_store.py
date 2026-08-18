"""Private Controller transaction store port (slice 01-02).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_PHASE_01
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class PersistenceError(Exception):
    def __init__(self, message: str = "persistence unavailable") -> None:
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


@dataclass(frozen=True)
class PipelineSnapshot:
    workspace_id: str
    pipeline_id: str
    status: str
    revision: int
    text: str


@dataclass(frozen=True)
class AcceptedWrite:
    inbox: InboxRecord
    event: EventWrite
    pipeline: PipelineSnapshot


@dataclass(frozen=True)
class StoreCounts:
    inbox: int
    events: int
    pipelines: int


@runtime_checkable
class ControllerTransactionStore(Protocol):
    def find_inbox(self, workspace_id: str, command_id: str) -> InboxRecord | None: ...

    def load_pipeline(
        self, workspace_id: str, pipeline_id: str
    ) -> PipelineSnapshot | None: ...

    def commit_accepted(self, write: AcceptedWrite) -> None: ...

    def counts(self) -> StoreCounts: ...

    def close(self) -> None: ...


__all__ = [
    "AcceptedWrite",
    "ControllerTransactionStore",
    "EventWrite",
    "InboxRecord",
    "PersistenceError",
    "PipelineSnapshot",
    "StoreCounts",
]
