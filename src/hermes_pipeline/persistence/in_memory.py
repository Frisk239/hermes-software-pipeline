"""Deterministic in-memory Controller persistence Adapter (slice-00-04).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

The deterministic in-memory Adapter implements the same private port
contract as the SQLite spike Adapter: a five-record atomic commit (Inbox,
Event, projection, Outbox, receipt) with the same fixed logical-write
positions and the same deterministic ``FaultSpec`` injection points — with
independent ``before`` and ``after`` hooks per logical write, where an
``after`` hook fires only after the named write executed on the staged
store (probed and recorded as bounded evidence) and the whole staged
transaction is then discarded — an Event hash chain computed by
``event_chain``, and a rebuild path that verifies the chain. No SQLite is
required; Controller logic runs against this Adapter with no database
present (AC-02).

Atomicity is modelled by staging the five writes on copies and swapping
them in only when every write succeeded; any injected fault discards the
staged copy (rollback semantics) and raises ``InjectedFault``, which the
Adapter translates into a safe ``PersistenceError`` at the port boundary.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import NoReturn, cast

from hermes_pipeline.controller._persistence_port import (
    AcceptanceWrites,
    ControllerPersistencePort,
    FaultSpec,
    InjectedFault,
    PersistenceError,
    PersistenceErrorKind,
    StoreAudit,
    StoredCommand,
)
from hermes_pipeline.domain.counter_spike import CounterState
from hermes_pipeline.persistence.event_chain import chain_hash, verify_chain

#: Fixed logical-write positions shared with the SQLite Adapter.
WRITE_INBOX = 1
WRITE_EVENT = 2
WRITE_PROJECTION = 3
WRITE_OUTBOX = 4
WRITE_RECEIPT = 5


@dataclass
class _InMemoryStore:
    """The staged store contents under the atomic commit model.

    ``projection`` always exists: it starts at the strict initial state
    ``(value=0, revision=0)``, mirroring the SQLite Adapter's seeded
    projection row, so ``audit().projection`` is never ``None``.
    """

    inbox: dict[str, StoredCommand] = field(default_factory=dict[str, StoredCommand])
    events: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    projection: CounterState = field(
        default_factory=lambda: CounterState(value=0, revision=0)
    )
    outbox: list[dict[str, str]] = field(default_factory=list[dict[str, str]])
    receipts: dict[str, str] = field(default_factory=dict[str, str])


def _raise_captured_failure(failure: PersistenceError | None) -> NoReturn:
    """Raise only after a raw exception handler has completed."""
    if failure is None:
        raise AssertionError("missing captured persistence failure")
    raise failure


class InMemoryControllerStore(ControllerPersistencePort):
    """Deterministic in-memory implementation of the private persistence port."""

    def __init__(self, fault_spec: FaultSpec | None = None) -> None:
        self._fault_spec = fault_spec or FaultSpec()
        self._store = _InMemoryStore()

    # -- private port contract -------------------------------------------

    def find_command(self, command_id: str) -> StoredCommand | None:
        return self._store.inbox.get(command_id)

    def load_counter(self) -> CounterState:
        return self._store.projection

    def commit_acceptance(self, writes: AcceptanceWrites) -> None:
        staged = copy.deepcopy(self._store)
        previous_hash = self._last_event_hash(staged)
        failure: PersistenceError | None = None
        try:
            self._write_inbox(staged, writes)
            self._write_event(staged, writes, previous_hash)
            self._write_projection(staged, writes)
            self._write_outbox(staged, writes)
            self._write_receipt(staged, writes)
        except InjectedFault:
            # Rollback semantics: the staged copy is discarded.
            failure = PersistenceError(
                PersistenceErrorKind.UNAVAILABLE,
                "persistence unavailable",
            )
        else:
            self._store = staged
            return
        _raise_captured_failure(failure)

    def rebuild_projection(self) -> CounterState:
        rows: list[tuple[int, str | None, str, str]] = []
        for row in self._store.events:
            rows.append(
                (
                    int(cast(int, row["sequence"])),
                    cast(
                        str | None,
                        row["previous_event_hash"]
                        if row["previous_event_hash"]
                        else None,
                    ),
                    str(row["event_hash"]),
                    str(row["payload_json"]),
                )
            )
        failure: PersistenceError | None = None
        try:
            verify_chain(rows)
        except ValueError:
            failure = PersistenceError(
                PersistenceErrorKind.UNAVAILABLE, "persistence unavailable"
            )
        else:
            rebuilt = CounterState(value=0, revision=0)
            for _ in rows:
                rebuilt = CounterState(
                    value=rebuilt.value + 1, revision=rebuilt.revision + 1
                )
            return rebuilt
        _raise_captured_failure(failure)

    def audit(self) -> StoreAudit:
        return StoreAudit(
            inbox_count=len(self._store.inbox),
            event_count=len(self._store.events),
            outbox_count=len(self._store.outbox),
            receipt_count=len(self._store.receipts),
            projection=self._store.projection,
        )

    # -- fault-aware logical writes --------------------------------------

    @staticmethod
    def _last_event_hash(store: _InMemoryStore) -> str | None:
        if not store.events:
            return None
        return str(store.events[-1]["event_hash"])

    def _raise_before(self, position: int) -> None:
        """A ``before`` hook fires before the named write executes (no
        after-write evidence is recorded for this phase)."""
        if position in self._fault_spec.before:
            raise InjectedFault(f"injected fault before logical write {position}")

    def _raise_after(self, position: int, probe: str) -> None:
        """An ``after`` hook fires only after the named write executed.

        The staged store already holds the written record (observable
        evidence on the shared ``FaultSpec``), then ``InjectedFault`` is
        raised and the staged copy is discarded, so the whole transaction
        rolls back (AC-03): the tests prove both that the target write ran
        and that all five records are absent afterwards.
        """
        if position in self._fault_spec.after:
            self._fault_spec.record(position, probe)
            raise InjectedFault(f"injected fault after logical write {position}")

    def _write_inbox(self, store: _InMemoryStore, writes: AcceptanceWrites) -> None:
        self._raise_before(WRITE_INBOX)
        store.inbox[writes.inbox.command_id] = StoredCommand(
            payload_hash=writes.inbox.payload_hash,
            receipt_json=writes.receipt.receipt_json,
        )
        # Probe matches the SQLite Adapter's probe: rows for this command_id.
        self._raise_after(WRITE_INBOX, "rows=1")

    def _write_event(
        self,
        store: _InMemoryStore,
        writes: AcceptanceWrites,
        previous_hash: str | None,
    ) -> None:
        self._raise_before(WRITE_EVENT)
        event_hash = chain_hash(
            previous_hash, writes.event.sequence, writes.event.payload_json
        )
        store.events.append(
            {
                "sequence": writes.event.sequence,
                "event_id": writes.event.event_id,
                "pipeline_revision": writes.event.pipeline_revision,
                "previous_event_hash": previous_hash,
                "event_hash": event_hash,
                "payload_json": writes.event.payload_json,
            }
        )
        self._raise_after(WRITE_EVENT, "rows=1")

    def _write_projection(
        self, store: _InMemoryStore, writes: AcceptanceWrites
    ) -> None:
        self._raise_before(WRITE_PROJECTION)
        store.projection = CounterState(
            value=writes.projection.value, revision=writes.projection.revision
        )
        self._raise_after(WRITE_PROJECTION, f"revision={store.projection.revision}")

    def _write_outbox(self, store: _InMemoryStore, writes: AcceptanceWrites) -> None:
        self._raise_before(WRITE_OUTBOX)
        store.outbox.append(
            {
                "command_id": writes.outbox.command_id,
                "effect_type": writes.outbox.effect_type,
                "payload_json": writes.outbox.payload_json,
            }
        )
        self._raise_after(WRITE_OUTBOX, "rows=1")

    def _write_receipt(self, store: _InMemoryStore, writes: AcceptanceWrites) -> None:
        self._raise_before(WRITE_RECEIPT)
        store.receipts[writes.receipt.command_id] = writes.receipt.receipt_json
        self._raise_after(WRITE_RECEIPT, "rows=1")


__all__ = [
    "WRITE_EVENT",
    "WRITE_INBOX",
    "WRITE_OUTBOX",
    "WRITE_PROJECTION",
    "WRITE_RECEIPT",
    "InMemoryControllerStore",
]
