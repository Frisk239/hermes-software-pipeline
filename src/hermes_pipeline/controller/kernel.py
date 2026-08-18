"""KernelController — durable submit over a private transaction store.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_PHASE_01
"""

from __future__ import annotations

from typing import Literal

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.jcs import canonical_json, content_hash
from hermes_pipeline.contracts.runtime import (
    CommandError,
    CommandReceipt,
    ControllerCommand,
)
from hermes_pipeline.controller.ports import PipelineQuery, PipelineView
from hermes_pipeline.controller.transaction_store import (
    AcceptedWrite,
    ControllerTransactionStore,
    EventWrite,
    InboxRecord,
    PersistenceError,
    PipelineSnapshot,
)
from hermes_pipeline.domain.errors import (
    ACCEPTED,
    EMPTY_REQUIREMENT,
    INVALID_TRANSITION,
)
from hermes_pipeline.domain.pipeline import (
    ConfirmRequirement,
    PipelineState,
    RejectRequirement,
    RequirementConfirmed,
    apply,
)

_RECEIPT_SCHEMA = "https://schemas.hermes-pipeline.dev/runtime/command-receipt/v1"
_STATUSES = frozenset({"UNCONFIRMED", "OPEN", "REJECTED"})


def _domain_command(
    command: ControllerCommand,
) -> ConfirmRequirement | RejectRequirement | None:
    payload = command.payload
    if command.command_type == "CONFIRM_REQUIREMENT":
        text = payload.get("text")
        if type(text) is str:
            return ConfirmRequirement(text=text)
        return None
    if command.command_type == "REJECT_REQUIREMENT":
        reason = payload.get("reason")
        if type(reason) is str:
            return RejectRequirement(reason=reason)
        return None
    return None


class KernelController:
    def __init__(self, store: ControllerTransactionStore, *, recorded_at: str) -> None:
        self._store = store
        self._recorded_at = recorded_at

    def submit(self, command: ControllerCommand) -> CommandReceipt:
        fingerprint = content_hash(command.model_dump(mode="json"))
        try:
            existing = self._store.find_inbox(command.workspace_id, command.command_id)
        except PersistenceError:
            return self._unavailable(command)
        if existing is not None:
            if existing.command_fingerprint == fingerprint:
                return CommandReceipt.model_validate_json(existing.receipt_json)
            return self._receipt(
                command,
                status="CONFLICT",
                observed_revision=self._safe_revision(command),
                error=CommandError(
                    code="CONFLICT",
                    message="command identity conflict",
                    retryable=False,
                ),
            )
        parsed = _domain_command(command)
        if parsed is None:
            return self._receipt(
                command,
                status="REJECTED",
                observed_revision=self._safe_revision(command),
                error=CommandError(
                    code="VALIDATION_ERROR",
                    message="unsupported command",
                    retryable=False,
                ),
            )
        try:
            snapshot = self._store.load_pipeline(
                command.workspace_id, command.pipeline_id
            )
        except PersistenceError:
            return self._unavailable(command)
        current = self._state_from_snapshot(snapshot)
        if current is None:
            return self._unavailable(command)
        if command.expected_revision != current.revision:
            return self._receipt(
                command,
                status="CONFLICT",
                observed_revision=current.revision,
                error=CommandError(
                    code="CONFLICT",
                    message="expected revision conflict",
                    retryable=False,
                ),
            )
        result = apply(current, parsed)
        if result.outcome == EMPTY_REQUIREMENT:
            return self._receipt(
                command,
                status="REJECTED",
                observed_revision=current.revision,
                error=CommandError(
                    code="VALIDATION_ERROR",
                    message="empty requirement",
                    retryable=False,
                ),
            )
        if result.outcome == INVALID_TRANSITION:
            return self._receipt(
                command,
                status="REJECTED",
                observed_revision=current.revision,
                error=CommandError(
                    code="VALIDATION_ERROR",
                    message="invalid transition",
                    retryable=False,
                ),
            )
        if result.outcome != ACCEPTED or result.event is None:
            return self._unavailable(command)
        event_id = f"evt_{command.workspace_id}_{command.command_id}"
        event = result.event
        if isinstance(event, RequirementConfirmed):
            event_type = "REQUIREMENT_CONFIRMED"
            payload_json = canonical_json({"text": event.text})
        else:
            event_type = "REQUIREMENT_REJECTED"
            payload_json = canonical_json({"reason": event.reason})
        receipt = self._receipt(
            command,
            status="ACCEPTED",
            observed_revision=result.state.revision,
            event_ids=[event_id],
        )
        write = AcceptedWrite(
            inbox=InboxRecord(
                workspace_id=command.workspace_id,
                command_id=command.command_id,
                command_fingerprint=fingerprint,
                receipt_json=receipt.model_dump_json(),
            ),
            event=EventWrite(
                event_id=event_id,
                workspace_id=command.workspace_id,
                pipeline_id=command.pipeline_id,
                event_type=event_type,
                payload_json=payload_json,
            ),
            pipeline=PipelineSnapshot(
                workspace_id=command.workspace_id,
                pipeline_id=command.pipeline_id,
                status=result.state.status,
                revision=result.state.revision,
                text=result.state.text,
            ),
        )
        try:
            self._store.commit_accepted(write)
        except PersistenceError:
            return self._unavailable(command)
        return receipt

    def read(self, query: PipelineQuery) -> PipelineView:
        return PipelineView(pipeline_id=query.pipeline_id, revision=0, status="UNKNOWN")

    def _safe_revision(self, command: ControllerCommand) -> int:
        try:
            snapshot = self._store.load_pipeline(
                command.workspace_id, command.pipeline_id
            )
        except PersistenceError:
            return 0
        return 0 if snapshot is None else snapshot.revision

    def _state_from_snapshot(
        self, snapshot: PipelineSnapshot | None
    ) -> PipelineState | None:
        if snapshot is None:
            return PipelineState(status="UNCONFIRMED", revision=0, text="")
        status = snapshot.status
        if status == "UNCONFIRMED" or status == "OPEN" or status == "REJECTED":
            return PipelineState(
                status=status, revision=snapshot.revision, text=snapshot.text
            )
        return None

    def _unavailable(self, command: ControllerCommand) -> CommandReceipt:
        return self._receipt(
            command,
            status="REJECTED",
            observed_revision=0,
            error=CommandError(
                code="INTERNAL_ERROR",
                message="persistence unavailable",
                retryable=True,
            ),
        )

    def _receipt(
        self,
        command: ControllerCommand,
        *,
        status: Literal["ACCEPTED", "REJECTED", "CONFLICT"],
        observed_revision: int,
        event_ids: list[str] | None = None,
        error: CommandError | None = None,
    ) -> CommandReceipt:
        return CommandReceipt(
            schema_id=_RECEIPT_SCHEMA,
            schema_version=FixedV1Integer(1),
            command_id=command.command_id,
            status=status,
            pipeline_id=command.pipeline_id,
            observed_revision=observed_revision,
            event_ids=[] if event_ids is None else event_ids,
            error=error
            or CommandError(code="INTERNAL_ERROR", message="", retryable=False),
            recorded_at=UtcTimestampRef(self._recorded_at),
            correlation_id=command.correlation_id,
        )


__all__ = ["KernelController"]
