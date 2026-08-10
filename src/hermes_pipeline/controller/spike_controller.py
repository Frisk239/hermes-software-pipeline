"""Spike Controller implementing ControllerCommandPort (slice-00-04).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

The spike Controller is the deterministic submit orchestration behind the
accepted ``ControllerCommandPort.submit(command: ControllerCommand) ->
CommandReceipt`` Interface. It depends only on the private persistence port
and on domain values; it never imports SQLAlchemy, LangGraph, Alembic,
filesystem code, or a concrete persistence Adapter and never executes SQL
or filesystem operations itself (AC-02, architecture rule ARCH-06).

Failure mappings (AC-03/AC-04, typed failure boundary):

- domain ``INVALID_DELTA`` -> ``REJECTED``/``VALIDATION_ERROR`` with fixed
  message ``invalid delta``;
- same command ID with a different canonical payload hash is classified
  privately as ``COMMAND_ID_CONFLICT`` and returns the schema-compatible
  ``CONFLICT``/``CONFLICT`` receipt with fixed message ``command identity
  conflict``;
- expected-revision mismatch -> ``CONFLICT``/``CONFLICT`` with fixed
  message ``expected revision conflict``;
- persistence failures including ``SQLITE_FULL`` -> an in-memory,
  non-durable ``REJECTED``/``INTERNAL_ERROR`` receipt with fixed message
  ``persistence unavailable`` and ``retryable=true``; no durable receipt
  record or partial records are written on that path.

Raw ``sqlite3``, SQLAlchemy, or driver exceptions never cross the
Interface. Time and identity enter through injectable providers so every
submission is deterministic in tests.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.jcs import canonical_json
from hermes_pipeline.contracts.runtime import (
    CommandError,
    CommandReceipt,
    ControllerCommand,
)
from hermes_pipeline.controller._command_port import ControllerCommandPort
from hermes_pipeline.controller._persistence_port import (
    AcceptanceWrites,
    ControllerPersistencePort,
    EventRecord,
    InboxRecord,
    OutboxRecord,
    PersistenceError,
    PersistenceErrorKind,
    ProjectionRecord,
    ReceiptRecord,
)
from hermes_pipeline.domain.counter_spike import CounterSpike, CounterState

#: The CounterSpike command type and payload field of the spike.
COMMAND_TYPE = "COUNTER_INCREMENT"
PAYLOAD_DELTA_FIELD = "delta"

#: Fixed safe failure messages (typed failure boundary).
MESSAGE_INVALID_DELTA = "invalid delta"
MESSAGE_IDENTITY_CONFLICT = "command identity conflict"
MESSAGE_REVISION_CONFLICT = "expected revision conflict"
MESSAGE_PERSISTENCE_UNAVAILABLE = "persistence unavailable"

#: Private duplicate classification (never crosses the Interface).
COMMAND_ID_CONFLICT = "COMMAND_ID_CONFLICT"

#: Spike Outbox effect placeholder; no real effect is scheduled.
SPIKE_OUTBOX_EFFECT = "SPIKE_NOOP_EFFECT"


@dataclass(frozen=True)
class SubmitOutcome:
    """Internal submit outcome before Interface projection.

    ``duplicate_class`` carries the private ``COMMAND_ID_CONFLICT``
    classification used by assertions; the Stage-visible receipt is always
    schema-compatible.
    """

    receipt: CommandReceipt
    duplicate_class: str | None = None
    appended_event: bool = False


def _rfc3339_utc(instant: datetime) -> str:
    """Format an instant as a fixed RFC 3339 UTC timestamp."""
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _payload_hash(payload: dict[str, object]) -> str:
    """Canonical payload hash used for same-ID conflict detection."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class SpikeController(ControllerCommandPort):
    """Deterministic spike implementation of the Stage-facing Interface.

    ``port`` is the private persistence port (in-memory or SQLite Adapter),
    ``clock`` is an injectable UTC instant provider, and ``new_event_id`` is
    an injectable deterministic event-id provider.
    """

    def __init__(
        self,
        port: ControllerPersistencePort,
        clock: Callable[[], datetime],
        new_event_id: Callable[[], str],
    ) -> None:
        self._port = port
        self._clock = clock
        self._new_event_id = new_event_id
        self._spike = CounterSpike()

    def submit(self, command: ControllerCommand) -> CommandReceipt:
        """Submit one immutable command and return its schema-compatible receipt.

        The full submit flow (deduplication, revision check, evaluation,
        atomic five-record commit) is private; callers see only
        ``CommandReceipt`` values.
        """
        return self.submit_internal(command).receipt

    def submit_internal(self, command: ControllerCommand) -> SubmitOutcome:
        """Spike-internal submit returning the private classification.

        Not part of the Stage-facing Interface; exists so the spike tests
        can assert the private ``COMMAND_ID_CONFLICT`` classification and
        the appended-event flag without leaking them through ``submit``.
        """
        return self._submit_impl(command)

    # -- internals ---------------------------------------------------------

    def _submit_impl(self, command: ControllerCommand) -> SubmitOutcome:
        try:
            stored = self._port.find_command(command.command_id)
        except PersistenceError as exc:
            # The deduplication probe is persistence too: a failure here
            # must map to the same fixed non-durable failure receipt as any
            # other persistence failure, and no raw exception may cross the
            # Interface (AC-02/AC-03 typed failure boundary).
            return SubmitOutcome(receipt=self._failure_receipt(command, exc))
        payload_hash = _payload_hash(command.payload)
        if stored is not None:
            if stored.payload_hash == payload_hash:
                return self._replay_receipt(stored.receipt_json, command)
            return SubmitOutcome(
                receipt=self._conflict_receipt(command, MESSAGE_IDENTITY_CONFLICT),
                duplicate_class=COMMAND_ID_CONFLICT,
            )

        try:
            state = self._port.load_counter()
        except PersistenceError as exc:
            return SubmitOutcome(receipt=self._failure_receipt(command, exc))

        if command.expected_revision != state.revision:
            return SubmitOutcome(
                receipt=self._conflict_receipt(command, MESSAGE_REVISION_CONFLICT)
            )

        delta = command.payload.get(PAYLOAD_DELTA_FIELD)
        delta_value = (
            delta if isinstance(delta, int) and not isinstance(delta, bool) else 0
        )
        result = self._spike.apply(state, delta_value)
        if result.outcome == "INVALID_DELTA":
            return SubmitOutcome(receipt=self._rejected_receipt(command, state))

        assert result.event is not None  # ACCEPTED always carries the event
        new_state = result.state
        event_id = self._new_event_id()
        recorded_at = UtcTimestampRef(_rfc3339_utc(self._clock()))
        receipt = self._accepted_receipt(command, new_state, event_id, recorded_at)
        writes = AcceptanceWrites(
            inbox=InboxRecord(
                command_id=command.command_id,
                payload_hash=payload_hash,
                command_json=canonical_json(command.model_dump()),
                recorded_at=recorded_at,
            ),
            event=EventRecord(
                sequence=new_state.revision,
                event_id=event_id,
                pipeline_revision=new_state.revision,
                payload_json=canonical_json(result.event.payload()),
            ),
            projection=ProjectionRecord(
                value=new_state.value, revision=new_state.revision
            ),
            outbox=OutboxRecord(
                command_id=command.command_id,
                effect_type=SPIKE_OUTBOX_EFFECT,
                payload_json=canonical_json({"command_id": command.command_id}),
            ),
            receipt=ReceiptRecord(
                command_id=command.command_id,
                receipt_json=receipt.model_dump_json(),
            ),
        )
        try:
            self._port.commit_acceptance(writes)
        except PersistenceError as exc:
            return SubmitOutcome(receipt=self._failure_receipt(command, exc))
        return SubmitOutcome(receipt=receipt, appended_event=True)

    def _replay_receipt(
        self, receipt_json: str, command: ControllerCommand
    ) -> SubmitOutcome:
        """Return the original receipt for an identical replayed command."""
        try:
            receipt = CommandReceipt.model_validate_json(receipt_json)
        except Exception:
            # A stored receipt that cannot be decoded is a persistence-level
            # failure; translate it exactly like any other port failure.
            return SubmitOutcome(
                receipt=self._failure_receipt(
                    command,
                    PersistenceError(
                        PersistenceErrorKind.UNAVAILABLE,
                        MESSAGE_PERSISTENCE_UNAVAILABLE,
                    ),
                )
            )
        return SubmitOutcome(receipt=receipt)

    def _accepted_receipt(
        self,
        command: ControllerCommand,
        state: CounterState,
        event_id: str,
        recorded_at: UtcTimestampRef,
    ) -> CommandReceipt:
        return CommandReceipt(
            schema_id="https://schemas.hermes-pipeline.dev/runtime/command-receipt/v1",
            schema_version=FixedV1Integer(1),
            command_id=command.command_id,
            status="ACCEPTED",
            pipeline_id=command.pipeline_id,
            observed_revision=state.revision,
            event_ids=[event_id],
            error=CommandError(code="INTERNAL_ERROR", message="", retryable=False),
            recorded_at=recorded_at,
            correlation_id=command.correlation_id,
        )

    def _rejected_receipt(
        self, command: ControllerCommand, state: CounterState
    ) -> CommandReceipt:
        return CommandReceipt(
            schema_id="https://schemas.hermes-pipeline.dev/runtime/command-receipt/v1",
            schema_version=FixedV1Integer(1),
            command_id=command.command_id,
            status="REJECTED",
            pipeline_id=command.pipeline_id,
            observed_revision=state.revision,
            event_ids=[],
            error=CommandError(
                code="VALIDATION_ERROR",
                message=MESSAGE_INVALID_DELTA,
                retryable=False,
            ),
            recorded_at=UtcTimestampRef(_rfc3339_utc(self._clock())),
            correlation_id=command.correlation_id,
        )

    def _conflict_receipt(
        self, command: ControllerCommand, message: str
    ) -> CommandReceipt:
        observed = self._safe_observed_revision()
        return CommandReceipt(
            schema_id="https://schemas.hermes-pipeline.dev/runtime/command-receipt/v1",
            schema_version=FixedV1Integer(1),
            command_id=command.command_id,
            status="CONFLICT",
            pipeline_id=command.pipeline_id,
            observed_revision=observed,
            event_ids=[],
            error=CommandError(code="CONFLICT", message=message, retryable=False),
            recorded_at=UtcTimestampRef(_rfc3339_utc(self._clock())),
            correlation_id=command.correlation_id,
        )

    def _failure_receipt(
        self, command: ControllerCommand, exc: PersistenceError
    ) -> CommandReceipt:
        observed = self._safe_observed_revision()
        return CommandReceipt(
            schema_id="https://schemas.hermes-pipeline.dev/runtime/command-receipt/v1",
            schema_version=FixedV1Integer(1),
            command_id=command.command_id,
            status="REJECTED",
            pipeline_id=command.pipeline_id,
            observed_revision=observed,
            event_ids=[],
            error=CommandError(
                code="INTERNAL_ERROR",
                message=MESSAGE_PERSISTENCE_UNAVAILABLE,
                retryable=True,
            ),
            recorded_at=UtcTimestampRef(_rfc3339_utc(self._clock())),
            correlation_id=command.correlation_id,
        )

    def _safe_observed_revision(self) -> int:
        """Best-effort current revision; never lets a port failure escape."""
        try:
            return self._port.load_counter().revision
        except PersistenceError:
            return 0


__all__ = [
    "COMMAND_ID_CONFLICT",
    "COMMAND_TYPE",
    "MESSAGE_IDENTITY_CONFLICT",
    "MESSAGE_INVALID_DELTA",
    "MESSAGE_PERSISTENCE_UNAVAILABLE",
    "MESSAGE_REVISION_CONFLICT",
    "PAYLOAD_DELTA_FIELD",
    "SPIKE_OUTBOX_EFFECT",
    "SpikeController",
    "SubmitOutcome",
]
