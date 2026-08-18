"""In-memory ControllerTransactionStore adapter (slices 01-02 through 01-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_PHASE_01
"""

from __future__ import annotations

from dataclasses import replace

from hermes_pipeline.controller.transaction_store import (
    AcceptedWrite,
    EventWrite,
    InboxRecord,
    LeaseRecord,
    OutboxRecord,
    PersistenceError,
    PipelineSnapshot,
    StoreCounts,
    fold_pipeline_events,
)


class MemoryKernelStore:
    def __init__(self) -> None:
        self._inbox: dict[tuple[str, str], InboxRecord] = {}
        self._events: list[EventWrite] = []
        self._pipelines: dict[tuple[str, str], PipelineSnapshot] = {}
        self._outbox: dict[tuple[str, str], OutboxRecord] = {}
        self._leases: dict[tuple[str, str], LeaseRecord] = {}
        self._fail_after: str | None = None
        self._fail_read = False

    def trip_commit_failure(self) -> None:
        self._fail_after = "event"

    def trip_read_failure(self) -> None:
        self._fail_read = True

    def find_inbox(self, workspace_id: str, command_id: str) -> InboxRecord | None:
        return self._inbox.get((workspace_id, command_id))

    def load_pipeline(
        self, workspace_id: str, pipeline_id: str
    ) -> PipelineSnapshot | None:
        if self._fail_read:
            self._fail_read = False
            raise PersistenceError("persistence unavailable")
        if not workspace_id:
            return None
        return self._pipelines.get((workspace_id, pipeline_id))

    def commit_accepted(self, write: AcceptedWrite) -> None:
        staged_inbox = dict(self._inbox)
        staged_events = list(self._events)
        staged_pipelines = dict(self._pipelines)
        staged_outbox = dict(self._outbox)
        staged_inbox[(write.inbox.workspace_id, write.inbox.command_id)] = write.inbox
        staged_events.append(write.event)
        staged_outbox[(write.outbox.workspace_id, write.outbox.command_id)] = (
            write.outbox
        )
        if self._fail_after == "event":
            self._fail_after = None
            raise PersistenceError("persistence unavailable")
        staged_pipelines[(write.pipeline.workspace_id, write.pipeline.pipeline_id)] = (
            write.pipeline
        )
        self._inbox = staged_inbox
        self._events = staged_events
        self._pipelines = staged_pipelines
        self._outbox = staged_outbox

    def list_events(self, workspace_id: str, pipeline_id: str) -> list[EventWrite]:
        if not workspace_id:
            return []
        matched = [
            event
            for event in self._events
            if event.pipeline_id == pipeline_id and event.workspace_id == workspace_id
        ]
        return sorted(matched, key=lambda event: event.pipeline_revision)

    def delete_pipeline(self, workspace_id: str, pipeline_id: str) -> None:
        if not workspace_id:
            return
        self._pipelines.pop((workspace_id, pipeline_id), None)

    def rebuild_pipeline(self, workspace_id: str, pipeline_id: str) -> PipelineSnapshot:
        if not workspace_id:
            return fold_pipeline_events("", pipeline_id, [])
        self.delete_pipeline(workspace_id, pipeline_id)
        events = self.list_events(workspace_id, pipeline_id)
        snapshot = fold_pipeline_events(workspace_id, pipeline_id, events)
        self._pipelines[(workspace_id, pipeline_id)] = snapshot
        return snapshot

    def list_pending_outbox(self, workspace_id: str) -> list[OutboxRecord]:
        if not workspace_id:
            return []
        pending = [
            record
            for record in self._outbox.values()
            if record.workspace_id == workspace_id and not record.delivery_receipt_json
        ]
        return sorted(pending, key=lambda record: record.command_id)

    def record_outbox_delivery(
        self, workspace_id: str, command_id: str, delivery_receipt_json: str
    ) -> None:
        if not workspace_id:
            return
        key = (workspace_id, command_id)
        existing = self._outbox.get(key)
        if existing is None or existing.delivery_receipt_json:
            return
        self._outbox[key] = replace(
            existing, delivery_receipt_json=delivery_receipt_json
        )

    def find_outbox(self, workspace_id: str, command_id: str) -> OutboxRecord | None:
        if not workspace_id:
            return None
        return self._outbox.get((workspace_id, command_id))

    def load_lease(self, workspace_id: str, pipeline_id: str) -> LeaseRecord | None:
        if not workspace_id:
            return None
        return self._leases.get((workspace_id, pipeline_id))

    def save_lease(self, record: LeaseRecord) -> None:
        if not record.workspace_id:
            return
        self._leases[(record.workspace_id, record.pipeline_id)] = record

    def delete_lease(self, workspace_id: str, pipeline_id: str) -> None:
        if not workspace_id:
            return
        self._leases.pop((workspace_id, pipeline_id), None)

    def delete_expired_leases(self, now: int) -> None:
        self._leases = {
            key: record
            for key, record in self._leases.items()
            if record.expires_at >= now
        }

    def counts(self) -> StoreCounts:
        return StoreCounts(
            inbox=len(self._inbox),
            events=len(self._events),
            pipelines=len(self._pipelines),
            outbox=len(self._outbox),
        )

    def close(self) -> None:
        return


__all__ = ["MemoryKernelStore"]
