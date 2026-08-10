"""SQLite spike Controller persistence Adapter (slice-00-04).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

The SQLite spike Adapter implements the private Controller persistence port
with SQLAlchemy Core and one explicit SQLite driver transaction mode
(AC-03, AC-08):

- the legacy ``sqlite3`` default transaction control is disabled: the
  ``connect`` event sets ``isolation_level = None`` (native autocommit), so
  the driver never opens an implicit transaction behind the Adapter's back;
- the ``begin`` event then emits an explicit ``BEGIN`` for every
  transaction, and SQLAlchemy issues the matching ``COMMIT`` / ``ROLLBACK``;
  the atomicity of the five-record commit therefore comes only from this
  explicit BEGIN/COMMIT pair and never from the driver default — a fixture
  that relies on the legacy implicit control behaves differently and fails
  the behavior-difference assertions;
- WAL journal mode with ``synchronous=FULL`` is applied to every pooled
  connection inside the same ``connect`` event (before any transaction
  opens), with one single writer;
- the five logical records (Inbox, Event, projection, Outbox, receipt) are
  committed all-or-none in one transaction; ``FaultSpec`` injects
  ``InjectedFault`` with independent ``before``/``after`` hooks per logical
  write for AC-03 rollback evidence — an ``after`` hook fires only after the
  named write executed inside the transaction (probed and recorded as
  bounded evidence on the ``FaultSpec``), then the whole transaction rolls
  back;
- every driver failure is translated at the port boundary into a safe
  ``PersistenceError``; raw ``sqlite3``/SQLAlchemy exceptions never cross.

The event hash chain is computed by ``event_chain`` inside the same
transaction; ``rebuild_projection`` replays the Event Log in order and
verifies the chain before returning the rebuilt state (AC-06).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Literal, NoReturn, cast

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine

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

#: Fixed logical-write positions shared with the in-memory Adapter.
WRITE_INBOX = 1
WRITE_EVENT = 2
WRITE_PROJECTION = 3
WRITE_OUTBOX = 4
WRITE_RECEIPT = 5

#: Test-only real-process crash boundary selectors used by the AC-05 worker.
#: They are deliberately private to this experimental Adapter: normal callers
#: never enable them, and no process control crosses the Controller port.
CrashPoint = Literal["pre-commit", "post-commit"]
CRASH_EXIT_PRE_COMMIT = 41
CRASH_EXIT_POST_COMMIT = 42

#: Explicit driver transaction mode (AC-03/AC-08): the legacy ``sqlite3``
#: implicit transaction control is disabled on every connection
#: (``isolation_level = None`` in the ``connect`` event) and an explicit
#: ``BEGIN`` is emitted by the ``begin`` event hook for every transaction;
#: SQLAlchemy issues the matching COMMIT/ROLLBACK. Documented in
#: ``docs/development/compatibility-targets.md`` and proven by the
#: behavior-difference tests in ``tests/spike/persistence``.
DRIVER_TRANSACTION_MODE = (
    "sqlalchemy-engine-begin-explicit-begin-event-hook-native-autocommit"
)

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS spike_inbox (
        command_id TEXT PRIMARY KEY,
        payload_hash TEXT NOT NULL,
        command_json TEXT NOT NULL,
        receipt_json TEXT NOT NULL,
        recorded_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spike_events (
        sequence INTEGER PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        pipeline_revision INTEGER NOT NULL,
        previous_event_hash TEXT,
        event_hash TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spike_projection (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        value INTEGER NOT NULL,
        revision INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spike_outbox (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        command_id TEXT NOT NULL,
        effect_type TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spike_receipts (
        command_id TEXT PRIMARY KEY,
        receipt_json TEXT NOT NULL
    )
    """,
)


class SqliteControllerStore(ControllerPersistencePort):
    """SQLite spike implementation of the private Controller persistence port."""

    def __init__(
        self,
        database_path: Path | str,
        fault_spec: FaultSpec | None = None,
        *,
        max_page_count: int | None = None,
        crash_at: CrashPoint | None = None,
    ) -> None:
        if crash_at not in (None, "pre-commit", "post-commit"):
            raise ValueError("unsupported crash point")
        self._database_path = Path(database_path)
        self._fault_spec = fault_spec or FaultSpec()
        self._max_page_count = max_page_count
        self._crash_at = crash_at
        url = f"sqlite:///{self._database_path.as_posix()}"
        self._engine: Engine = create_engine(url, future=True)

        def _configure_explicit_transactions(
            dbapi_connection: object, connection_record: object
        ) -> None:
            connection = cast(sqlite3.Connection, dbapi_connection)
            # Explicit driver transaction mode (AC-03/AC-08): disable the
            # legacy sqlite3 implicit transaction control entirely (native
            # autocommit); every transaction is then opened only by the
            # explicit "begin" event hook below. WAL + synchronous=FULL are
            # applied on the same raw connection before any transaction
            # opens; SQLite forbids changing these settings inside one.
            connection.isolation_level = None
            cursor = connection.cursor()
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = FULL")
            if self._max_page_count is not None:
                # max_page_count is enforced per connection and is a no-op
                # inside a transaction, so it is applied on the raw
                # connection before any transaction opens (the deterministic
                # SQLITE_FULL injection boundary, AC-09).
                cursor.execute(f"PRAGMA max_page_count = {int(self._max_page_count)}")
            cursor.close()

        def _emit_explicit_begin(conn: Connection) -> None:
            # The explicit BEGIN event hook: every transaction starts with a
            # real "BEGIN" statement issued by the Adapter, never by the
            # driver's legacy default; SQLAlchemy still emits the matching
            # COMMIT/ROLLBACK.
            conn.exec_driver_sql("BEGIN")

        event.listen(self._engine, "connect", _configure_explicit_transactions)
        event.listen(self._engine, "begin", _emit_explicit_begin)

        self._initialize()

    def _initialize(self) -> None:
        # Schema DDL runs inside one explicit engine.begin() transaction.
        with self._engine.begin() as conn:
            for statement in SCHEMA_STATEMENTS:
                conn.execute(text(statement))
            has_projection = conn.execute(
                text("SELECT 1 FROM spike_projection WHERE id = 1")
            ).first()
            if has_projection is None:
                conn.execute(
                    text(
                        "INSERT INTO spike_projection (id, value, revision) "
                        "VALUES (1, 0, 0)"
                    )
                )

    def close(self) -> None:
        """Dispose the engine; safe to call more than once."""
        self._engine.dispose()

    # -- private port contract -------------------------------------------

    def find_command(self, command_id: str) -> StoredCommand | None:
        failure: PersistenceError | None = None
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT payload_hash, receipt_json FROM spike_inbox "
                        "WHERE command_id = :command_id"
                    ),
                    {"command_id": command_id},
                ).first()
        except Exception as exc:
            failure = self._translate(exc)
        else:
            if row is None:
                return None
            return StoredCommand(payload_hash=str(row[0]), receipt_json=str(row[1]))
        self._raise_captured_failure(failure)

    def load_counter(self) -> CounterState:
        failure: PersistenceError | None = None
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    text("SELECT value, revision FROM spike_projection WHERE id = 1")
                ).first()
        except Exception as exc:
            failure = self._translate(exc)
        else:
            if row is None:
                return CounterState(value=0, revision=0)
            return CounterState(value=int(row[0]), revision=int(row[1]))
        self._raise_captured_failure(failure)

    def commit_acceptance(self, writes: AcceptanceWrites) -> None:
        failure: PersistenceError | None = None
        try:
            with self._engine.begin() as conn:
                self._fault_before(conn, WRITE_INBOX)
                conn.execute(
                    text(
                        "INSERT INTO spike_inbox "
                        "(command_id, payload_hash, command_json, "
                        " receipt_json, recorded_at) "
                        "VALUES (:command_id, :payload_hash, :command_json, "
                        ":receipt_json, :recorded_at)"
                    ),
                    {
                        "command_id": writes.inbox.command_id,
                        "payload_hash": writes.inbox.payload_hash,
                        "command_json": writes.inbox.command_json,
                        "receipt_json": writes.receipt.receipt_json,
                        "recorded_at": writes.inbox.recorded_at,
                    },
                )
                self._fault_after(conn, WRITE_INBOX, writes.inbox.command_id)
                self._fault_before(conn, WRITE_EVENT)
                previous = self._last_event_hash(conn)
                event_hash = chain_hash(
                    previous, writes.event.sequence, writes.event.payload_json
                )
                conn.execute(
                    text(
                        "INSERT INTO spike_events "
                        "(sequence, event_id, pipeline_revision, "
                        " previous_event_hash, event_hash, payload_json) "
                        "VALUES (:sequence, :event_id, :pipeline_revision, "
                        " :previous_event_hash, :event_hash, :payload_json)"
                    ),
                    {
                        "sequence": writes.event.sequence,
                        "event_id": writes.event.event_id,
                        "pipeline_revision": writes.event.pipeline_revision,
                        "previous_event_hash": previous,
                        "event_hash": event_hash,
                        "payload_json": writes.event.payload_json,
                    },
                )
                self._fault_after(conn, WRITE_EVENT, writes.event.event_id)
                self._fault_before(conn, WRITE_PROJECTION)
                conn.execute(
                    text(
                        "UPDATE spike_projection "
                        "SET value = :value, revision = :revision WHERE id = 1"
                    ),
                    {
                        "value": writes.projection.value,
                        "revision": writes.projection.revision,
                    },
                )
                self._fault_after(conn, WRITE_PROJECTION, None)
                self._fault_before(conn, WRITE_OUTBOX)
                conn.execute(
                    text(
                        "INSERT INTO spike_outbox "
                        "(command_id, effect_type, payload_json) "
                        "VALUES (:command_id, :effect_type, :payload_json)"
                    ),
                    {
                        "command_id": writes.outbox.command_id,
                        "effect_type": writes.outbox.effect_type,
                        "payload_json": writes.outbox.payload_json,
                    },
                )
                self._fault_after(conn, WRITE_OUTBOX, writes.outbox.command_id)
                self._fault_before(conn, WRITE_RECEIPT)
                conn.execute(
                    text(
                        "INSERT INTO spike_receipts (command_id, receipt_json) "
                        "VALUES (:command_id, :receipt_json)"
                    ),
                    {
                        "command_id": writes.receipt.command_id,
                        "receipt_json": writes.receipt.receipt_json,
                    },
                )
                self._fault_after(conn, WRITE_RECEIPT, writes.receipt.command_id)
                self._crash_before_commit()
            # At this point ``engine.begin`` has issued the actual COMMIT.
            # The post-commit crash is therefore on the real Adapter path,
            # not a duplicate raw-sqlite test implementation (AC-05).
            self._crash_after_commit()
        except InjectedFault:
            failure = PersistenceError(
                PersistenceErrorKind.UNAVAILABLE,
                "persistence unavailable",
            )
        except Exception as exc:
            failure = self._translate(exc)
        else:
            return
        self._raise_captured_failure(failure)

    def rebuild_projection(self) -> CounterState:
        failure: PersistenceError | None = None
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT sequence, previous_event_hash, event_hash, "
                        "payload_json FROM spike_events ORDER BY sequence"
                    )
                ).all()
        except Exception as exc:
            failure = self._translate(exc)
        else:
            events: list[tuple[int, str | None, str, str]] = []
            for row in rows:
                events.append(
                    (
                        int(row[0]),
                        str(row[1]) if row[1] is not None else None,
                        str(row[2]),
                        str(row[3]),
                    )
                )
            try:
                verify_chain(events)
            except ValueError:
                failure = PersistenceError(
                    PersistenceErrorKind.UNAVAILABLE, "persistence unavailable"
                )
            else:
                rebuilt = CounterState(value=0, revision=0)
                for _ in events:
                    rebuilt = CounterState(
                        value=rebuilt.value + 1, revision=rebuilt.revision + 1
                    )
                return rebuilt
        self._raise_captured_failure(failure)

    def audit(self) -> StoreAudit:
        failure: PersistenceError | None = None
        try:
            with self._engine.connect() as conn:
                inbox = int(
                    conn.execute(text("SELECT COUNT(*) FROM spike_inbox")).scalar() or 0
                )
                events = int(
                    conn.execute(text("SELECT COUNT(*) FROM spike_events")).scalar()
                    or 0
                )
                outbox = int(
                    conn.execute(text("SELECT COUNT(*) FROM spike_outbox")).scalar()
                    or 0
                )
                receipts = int(
                    conn.execute(text("SELECT COUNT(*) FROM spike_receipts")).scalar()
                    or 0
                )
                projection_row = conn.execute(
                    text("SELECT value, revision FROM spike_projection WHERE id = 1")
                ).first()
        except Exception as exc:
            failure = self._translate(exc)
        else:
            projection = (
                CounterState(
                    value=int(projection_row[0]), revision=int(projection_row[1])
                )
                if projection_row is not None
                else None
            )
            return StoreAudit(
                inbox_count=inbox,
                event_count=events,
                outbox_count=outbox,
                receipt_count=receipts,
                projection=projection,
            )
        self._raise_captured_failure(failure)

    def selected_pragmas(self) -> dict[str, object]:
        """Return the AC-09 PRAGMAs from an Adapter-configured connection.

        This is experimental evidence only, not a Controller port method.
        Reading through the Engine ensures ``synchronous`` is measured on a
        connection that received this Adapter's explicit configuration,
        rather than on an unrelated raw sqlite3 connection.
        """
        failure: PersistenceError | None = None
        try:
            with self._engine.connect() as conn:
                return {
                    "journal_mode": str(
                        conn.execute(text("PRAGMA journal_mode")).scalar() or ""
                    ),
                    "synchronous": int(
                        conn.execute(text("PRAGMA synchronous")).scalar() or 0
                    ),
                    "wal_autocheckpoint": int(
                        conn.execute(text("PRAGMA wal_autocheckpoint")).scalar() or 0
                    ),
                    "page_size": int(
                        conn.execute(text("PRAGMA page_size")).scalar() or 0
                    ),
                    "max_page_count": int(
                        conn.execute(text("PRAGMA max_page_count")).scalar() or 0
                    ),
                }
        except Exception as exc:
            failure = self._translate(exc)
        self._raise_captured_failure(failure)

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _raise_captured_failure(failure: PersistenceError | None) -> NoReturn:
        """Raise a safe error only after the raw exception handler has ended."""
        if failure is None:
            raise AssertionError("missing captured persistence failure")
        raise failure

    @staticmethod
    def _last_event_hash(conn: Connection) -> str | None:
        row = conn.execute(
            text("SELECT event_hash FROM spike_events ORDER BY sequence DESC LIMIT 1")
        ).first()
        return str(row[0]) if row is not None else None

    def _fault_before(self, conn: Connection, position: int) -> None:
        # ``conn`` is unused beyond the injection contract; the write
        # happens on the caller's explicit transaction connection. A
        # ``before`` hook fires before the named write executes, so no
        # after-write evidence is recorded for this phase.
        if position in self._fault_spec.before:
            raise InjectedFault(f"injected fault before logical write {position}")

    def _fault_after(
        self, conn: Connection, position: int, command_id: str | None
    ) -> None:
        # An ``after`` hook fires only after the named write has executed
        # inside this transaction: the probe below observes the written row
        # on the same connection (uncommitted but visible inside the
        # transaction) and records bounded, sensitive-free evidence on the
        # FaultSpec before the InjectedFault is raised. The surrounding
        # engine.begin() then rolls the whole transaction back, so the tests
        # can prove both that the target write really ran and that all five
        # records are absent afterwards (AC-03).
        if position in self._fault_spec.after:
            probe = self._probe_write(conn, position, command_id)
            self._fault_spec.record(position, probe)
            raise InjectedFault(f"injected fault after logical write {position}")

    def _crash_before_commit(self) -> None:
        """Test-only real process exit after all writes but before COMMIT."""
        if self._crash_at == "pre-commit":
            os._exit(CRASH_EXIT_PRE_COMMIT)

    def _crash_after_commit(self) -> None:
        """Test-only real process exit after the Adapter's COMMIT."""
        if self._crash_at == "post-commit":
            os._exit(CRASH_EXIT_POST_COMMIT)

    @staticmethod
    def _probe_write(conn: Connection, position: int, command_id: str | None) -> str:
        """Bounded probe of the just-executed write, visible in-transaction."""
        if position == WRITE_INBOX:
            count = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM spike_inbox WHERE command_id = :cid"),
                    {"cid": command_id},
                ).scalar()
                or 0
            )
            return f"rows={count}"
        if position == WRITE_EVENT:
            count = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM spike_events WHERE event_id = :eid"),
                    {"eid": command_id},
                ).scalar()
                or 0
            )
            return f"rows={count}"
        if position == WRITE_PROJECTION:
            revision = conn.execute(
                text("SELECT revision FROM spike_projection WHERE id = 1")
            ).scalar()
            return f"revision={int(revision or 0)}"
        if position in (WRITE_OUTBOX, WRITE_RECEIPT):
            table = "spike_outbox" if position == WRITE_OUTBOX else "spike_receipts"
            count = int(
                conn.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE command_id = :cid"),
                    {"cid": command_id},
                ).scalar()
                or 0
            )
            return f"rows={count}"
        raise AssertionError(f"unknown logical write position {position}")

    @staticmethod
    def _translate(exc: Exception) -> PersistenceError:
        """Translate any driver exception into a safe, sensitive-free error."""
        text_lower = str(exc).lower()
        kind = (
            PersistenceErrorKind.SQLITE_FULL
            if "database or disk is full" in text_lower
            else PersistenceErrorKind.UNAVAILABLE
        )
        return PersistenceError(kind, "persistence unavailable")


__all__ = [
    "CRASH_EXIT_POST_COMMIT",
    "CRASH_EXIT_PRE_COMMIT",
    "DRIVER_TRANSACTION_MODE",
    "SCHEMA_STATEMENTS",
    "WRITE_EVENT",
    "WRITE_INBOX",
    "WRITE_OUTBOX",
    "WRITE_PROJECTION",
    "WRITE_RECEIPT",
    "CrashPoint",
    "SqliteControllerStore",
]
