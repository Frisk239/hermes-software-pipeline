"""Private Controller persistence port and spike records (slice-00-04).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

This port is private to the Controller: Controller code depends only on
this port and on domain values, and never imports SQLAlchemy, LangGraph,
Alembic, filesystem code, or a concrete persistence Adapter, and never
executes SQL or filesystem operations itself (architecture rule ARCH-06).

The spike submit flow evaluates a command against CounterSpike state and
commits Inbox, Event, projection, Outbox, and receipt records in one
explicit SQLite transaction (all-or-none). The port has a deterministic
in-memory Adapter and one SQLite spike Adapter; both implement the shared
port contract.

Every driver failure is translated inside the Adapters into the typed
``PersistenceError`` below; raw ``sqlite3``, SQLAlchemy, or driver
exceptions never cross this port. The event hash chain is owned by the
persistence layer (``hermes_pipeline.persistence.event_chain``), so the
Controller never computes event hashes itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from hermes_pipeline.domain.counter_spike import CounterState


class PersistenceErrorKind(StrEnum):
    """Safe, sensitive-free classification of a persistence failure."""

    UNAVAILABLE = "UNAVAILABLE"
    SQLITE_FULL = "SQLITE_FULL"


class PersistenceError(Exception):
    """Typed, sensitive-free persistence failure crossing the private port.

    ``kind`` is one of the fixed ``PersistenceErrorKind`` values and
    ``safe_message`` is fixed bounded text; no raw driver exception text,
    SQL, path, or database content is carried.
    """

    def __init__(self, kind: PersistenceErrorKind, safe_message: str) -> None:
        self.kind = kind
        self.safe_message = safe_message
        super().__init__(safe_message)


@dataclass(frozen=True)
class InboxRecord:
    """One spike Inbox row: the submitted command and its payload hash."""

    command_id: str
    payload_hash: str
    command_json: str
    recorded_at: str


@dataclass(frozen=True)
class EventRecord:
    """One spike Event row (before the persistence layer adds the hash chain).

    ``sequence`` equals the new pipeline revision: accepted commands and
    Events are strictly 1:1. The persistence layer computes and stores
    ``previous_event_hash`` and ``event_hash`` from ``event_chain``; the
    Controller never touches the hash chain.
    """

    sequence: int
    event_id: str
    pipeline_revision: int
    payload_json: str


@dataclass(frozen=True)
class ProjectionRecord:
    """The updated live projection row (value, revision)."""

    value: int
    revision: int


@dataclass(frozen=True)
class OutboxRecord:
    """One spike Outbox row (no real effect is scheduled by the spike)."""

    command_id: str
    effect_type: str
    payload_json: str


@dataclass(frozen=True)
class ReceiptRecord:
    """One durable receipt row; replays return this exact receipt."""

    command_id: str
    receipt_json: str


@dataclass(frozen=True)
class AcceptanceWrites:
    """The five logical records committed atomically by one accepted command."""

    inbox: InboxRecord
    event: EventRecord
    projection: ProjectionRecord
    outbox: OutboxRecord
    receipt: ReceiptRecord


@dataclass(frozen=True)
class StoredCommand:
    """A previously accepted command (for deduplication and replay)."""

    payload_hash: str
    receipt_json: str


@dataclass(frozen=True)
class StoreAudit:
    """Deterministic read-only audit counts for spike assertions."""

    inbox_count: int
    event_count: int
    outbox_count: int
    receipt_count: int
    projection: CounterState | None


@dataclass
class FaultSpec:
    """Deterministic in-transaction fault injection for AC-03 evidence.

    ``before`` and ``after`` are independent hook sets over the fixed
    logical-write positions (1 = Inbox, 2 = Event, 3 = projection, 4 =
    Outbox, 5 = receipt). A ``before`` hook fires *before* the named write
    executes; an ``after`` hook fires only *after* the named write has
    executed inside the transaction, so the tests can prove both that the
    target write really ran (observable ``evidence``) and that the whole
    transaction still rolls back (all five records absent). Both phases
    raise the same deterministic ``InjectedFault`` and are transaction-
    failure evidence only, never process-crash evidence (AC-05).

    ``evidence`` is a bounded, sensitive-free in-memory record of every
    after-hook probe: entries have the fixed shape
    ``after:write:<position>:probe:<probe>`` and carry no SQL, path,
    database content, or raw exception text. It is owned by the caller
    (the test), which passes the same instance into the Adapter.
    """

    before: frozenset[int] = frozenset()
    after: frozenset[int] = frozenset()
    evidence: list[str] = field(default_factory=list[str])

    def record(self, position: int, probe: str) -> None:
        """Record one bounded after-write probe (write already executed)."""
        self.evidence.append(f"after:write:{position}:probe:{probe}")


class InjectedFault(Exception):
    """The deterministic exception raised at a configured injection point."""


@runtime_checkable
class ControllerPersistencePort(Protocol):
    """The private Controller persistence port (spike).

    Implementations must provide an atomic five-record commit, deterministic
    in-memory or SQLite storage, and a rebuild path that verifies the Event
    hash chain.
    """

    def find_command(self, command_id: str) -> StoredCommand | None:
        """Return the stored command, or None when never accepted."""
        raise NotImplementedError

    def load_counter(self) -> CounterState:
        """Return the current CounterSpike state (projection)."""
        raise NotImplementedError

    def commit_acceptance(self, writes: AcceptanceWrites) -> None:
        """Atomically commit the five records or none of them.

        Raises ``PersistenceError`` (translated, sensitive-free) on any
        driver or injected failure; the whole transaction is rolled back.
        """
        raise NotImplementedError

    def rebuild_projection(self) -> CounterState:
        """Rebuild the projection from the Event Log with hash-chain
        verification; a broken chain raises ``PersistenceError``."""
        raise NotImplementedError

    def audit(self) -> StoreAudit:
        """Return deterministic read-only record counts."""
        raise NotImplementedError


__all__ = [
    "AcceptanceWrites",
    "ControllerPersistencePort",
    "EventRecord",
    "FaultSpec",
    "InboxRecord",
    "InjectedFault",
    "OutboxRecord",
    "PersistenceError",
    "PersistenceErrorKind",
    "ProjectionRecord",
    "ReceiptRecord",
    "StoreAudit",
    "StoredCommand",
]
