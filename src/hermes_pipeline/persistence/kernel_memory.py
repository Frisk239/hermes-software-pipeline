"""In-memory ControllerTransactionStore adapter (slice 01-02).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_PHASE_01
"""

from __future__ import annotations

from hermes_pipeline.controller.transaction_store import (
    AcceptedWrite,
    InboxRecord,
    PersistenceError,
    PipelineSnapshot,
    StoreCounts,
)


class MemoryKernelStore:
    def __init__(self) -> None:
        self._inbox: dict[tuple[str, str], InboxRecord] = {}
        self._events: list[object] = []
        self._pipelines: dict[tuple[str, str], PipelineSnapshot] = {}
        self._fail_after: str | None = None

    def trip_commit_failure(self) -> None:
        self._fail_after = "event"

    def find_inbox(self, workspace_id: str, command_id: str) -> InboxRecord | None:
        return self._inbox.get((workspace_id, command_id))

    def load_pipeline(
        self, workspace_id: str, pipeline_id: str
    ) -> PipelineSnapshot | None:
        return self._pipelines.get((workspace_id, pipeline_id))

    def commit_accepted(self, write: AcceptedWrite) -> None:
        staged_inbox = dict(self._inbox)
        staged_events = list(self._events)
        staged_pipelines = dict(self._pipelines)
        staged_inbox[(write.inbox.workspace_id, write.inbox.command_id)] = write.inbox
        staged_events.append(write.event)
        if self._fail_after == "event":
            self._fail_after = None
            raise PersistenceError("persistence unavailable")
        staged_pipelines[(write.pipeline.workspace_id, write.pipeline.pipeline_id)] = (
            write.pipeline
        )
        self._inbox = staged_inbox
        self._events = staged_events
        self._pipelines = staged_pipelines

    def counts(self) -> StoreCounts:
        return StoreCounts(
            inbox=len(self._inbox),
            events=len(self._events),
            pipelines=len(self._pipelines),
        )

    def close(self) -> None:
        return


__all__ = ["MemoryKernelStore"]
