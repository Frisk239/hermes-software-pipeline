"""Phase-01 Controller kernel (slice-01-02).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_PHASE_01

Deterministic Controller kernel backed by the SQLite KernelStore. The
kernel never touches sqlite3 directly; persistence failures cross the
KernelStore boundary as KernelStoreError.
"""

from __future__ import annotations

import hashlib
from typing import Literal, cast

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.jcs import canonical_json
from hermes_pipeline.contracts.runtime import (
    CommandError,
    CommandReceipt,
    ControllerCommand,
)
from hermes_pipeline.controller.ports import PipelineQuery, PipelineView
from hermes_pipeline.domain.errors import EMPTY_REQUIREMENT, INVALID_TRANSITION
from hermes_pipeline.domain.pipeline import (
    ConfirmRequirement,
    PipelineState,
    RejectRequirement,
    RequirementConfirmed,
    RequirementRejected,
    apply,
)
from hermes_pipeline.persistence.kernel_store import KernelStore, KernelStoreError

_RECEIPT_SCHEMA = "https://schemas.hermes-pipeline.dev/runtime/command-receipt/v1"
_FIXED_RECORDED_AT = "2026-01-01T00:00:00Z"
_UNSUPPORTED = "unsupported command"
_EMPTY = "empty requirement"
_INVALID = "invalid transition"
_IDENTITY = "command identity conflict"
_REVISION = "expected revision conflict"
_PERSISTENCE = "persistence unavailable"
_STATUSES = frozenset({"UNCONFIRMED", "OPEN", "REJECTED"})

ReceiptStatus = Literal["ACCEPTED", "REJECTED", "CONFLICT", "DEDUPLICATED"]
ErrorCode = Literal[
    "VALIDATION_ERROR",
    "AUTHENTICATION_FAILED",
    "AUTHORIZATION_DENIED",
    "NOT_FOUND",
    "CONFLICT",
    "POLICY_REJECTED",
    "LEASE_STALE",
    "DEPENDENCY_UNAVAILABLE",
    "RATE_LIMITED",
    "INTERNAL_ERROR",
]
PipelineStatus = Literal["UNCONFIRMED", "OPEN", "REJECTED"]


def _payload_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class KernelController:
    def __init__(
        self,
        store: KernelStore,
        recorded_at: str = _FIXED_RECORDED_AT,
    ) -> None:
        self._store = store
        self._recorded_at = UtcTimestampRef(recorded_at)

    def read(self, query: PipelineQuery) -> PipelineView:
        return PipelineView(pipeline_id=query.pipeline_id, revision=0, status="UNKNOWN")

    def submit(self, command: ControllerCommand) -> CommandReceipt:
        parsed = _parse(command)
        if parsed is None:
            return self._receipt(
                command,
                status="REJECTED",
                observed_revision=0,
                code="VALIDATION_ERROR",
                message=_UNSUPPORTED,
            )
        try:
            return self._submit_accepted_path(command, parsed)
        except KernelStoreError:
            return self._receipt(
                command,
                status="REJECTED",
                observed_revision=0,
                code="INTERNAL_ERROR",
                message=_PERSISTENCE,
                retryable=True,
            )

    def _submit_accepted_path(
        self,
        command: ControllerCommand,
        parsed: ConfirmRequirement | RejectRequirement,
    ) -> CommandReceipt:
        with self._store.transaction():
            existing = self._store.find_inbox(command.command_id)
            payload_hash = _payload_hash(command.payload)
            if existing is not None:
                stored_hash, receipt_json = existing
                if stored_hash == payload_hash:
                    return CommandReceipt.model_validate_json(receipt_json)
                return self._receipt(
                    command,
                    status="CONFLICT",
                    observed_revision=self._current_revision(command.pipeline_id),
                    code="CONFLICT",
                    message=_IDENTITY,
                )
            state = self._load_state(command.pipeline_id)
            if command.expected_revision != state.revision:
                return self._receipt(
                    command,
                    status="CONFLICT",
                    observed_revision=state.revision,
                    code="CONFLICT",
                    message=_REVISION,
                )
            result = apply(state, parsed)
            if result.outcome == EMPTY_REQUIREMENT:
                return self._receipt(
                    command,
                    status="REJECTED",
                    observed_revision=state.revision,
                    code="VALIDATION_ERROR",
                    message=_EMPTY,
                )
            if result.outcome == INVALID_TRANSITION:
                return self._receipt(
                    command,
                    status="REJECTED",
                    observed_revision=state.revision,
                    code="VALIDATION_ERROR",
                    message=_INVALID,
                )
            event = result.event
            if isinstance(event, RequirementConfirmed):
                event_type = "REQUIREMENT_CONFIRMED"
                payload_json = canonical_json({"text": event.text})
            elif isinstance(event, RequirementRejected):
                event_type = "REQUIREMENT_REJECTED"
                payload_json = canonical_json({"reason": event.reason})
            else:
                raise KernelStoreError("missing accepted event")
            event_id = self._store.insert_event(
                command.pipeline_id, event_type, payload_json
            )
            receipt = self._receipt(
                command,
                status="ACCEPTED",
                observed_revision=result.state.revision,
                event_ids=[str(event_id)],
            )
            self._store.insert_inbox(
                command.command_id, payload_hash, receipt.model_dump_json()
            )
            self._store.upsert_pipeline(
                command.pipeline_id,
                result.state.status,
                result.state.revision,
                result.state.text,
            )
            return receipt

    def _load_state(self, pipeline_id: str) -> PipelineState:
        loaded = self._store.load_pipeline(pipeline_id)
        if loaded is None:
            return PipelineState(status="UNCONFIRMED", revision=0, text="")
        status, revision, text = loaded
        if status not in _STATUSES:
            raise KernelStoreError("invalid pipeline status")
        return PipelineState(
            status=cast(PipelineStatus, status), revision=revision, text=text
        )

    def _current_revision(self, pipeline_id: str) -> int:
        loaded = self._store.load_pipeline(pipeline_id)
        if loaded is None:
            return 0
        return loaded[1]

    def _receipt(
        self,
        command: ControllerCommand,
        *,
        status: ReceiptStatus,
        observed_revision: int,
        code: ErrorCode = "INTERNAL_ERROR",
        message: str = "",
        retryable: bool = False,
        event_ids: list[str] | None = None,
    ) -> CommandReceipt:
        return CommandReceipt(
            schema_id=_RECEIPT_SCHEMA,
            schema_version=FixedV1Integer(1),
            command_id=command.command_id,
            status=status,
            pipeline_id=command.pipeline_id,
            observed_revision=observed_revision,
            event_ids=[] if event_ids is None else event_ids,
            error=CommandError(code=code, message=message, retryable=retryable),
            recorded_at=self._recorded_at,
            correlation_id=command.correlation_id,
        )


def _parse(
    command: ControllerCommand,
) -> ConfirmRequirement | RejectRequirement | None:
    if command.command_type == "CONFIRM_REQUIREMENT":
        text = command.payload.get("text")
        if isinstance(text, str):
            return ConfirmRequirement(text=text)
        return None
    if command.command_type == "REJECT_REQUIREMENT":
        reason = command.payload.get("reason")
        if isinstance(reason, str):
            return RejectRequirement(reason=reason)
        return None
    return None


__all__ = ["KernelController"]
