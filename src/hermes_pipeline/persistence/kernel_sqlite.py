"""SQLAlchemy Core SQLite adapter for ControllerTransactionStore.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_PHASE_01
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, NoReturn, cast

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    delete,
    event,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

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

_METADATA = MetaData()

_INBOX = Table(
    "inbox",
    _METADATA,
    Column("workspace_id", Text, primary_key=True),
    Column("command_id", Text, primary_key=True),
    Column("command_fingerprint", Text, nullable=False),
    Column("receipt_json", Text, nullable=False),
)

_EVENTS = Table(
    "events",
    _METADATA,
    Column("event_id", Text, primary_key=True),
    Column("workspace_id", Text, nullable=False),
    Column("pipeline_id", Text, nullable=False),
    Column("event_type", Text, nullable=False),
    Column("payload_json", Text, nullable=False),
    Column("pipeline_revision", Integer, nullable=False),
)

_PIPELINES = Table(
    "pipelines",
    _METADATA,
    Column("workspace_id", Text, primary_key=True),
    Column("pipeline_id", Text, primary_key=True),
    Column("status", Text, nullable=False),
    Column("revision", Integer, nullable=False),
    Column("text", Text, nullable=False),
)

_OUTBOX = Table(
    "outbox",
    _METADATA,
    Column("workspace_id", Text, primary_key=True),
    Column("command_id", Text, primary_key=True),
    Column("effect_type", Text, nullable=False),
    Column("payload_json", Text, nullable=False),
    Column("delivery_receipt_json", Text, nullable=True),
)

_LEASES = Table(
    "leases",
    _METADATA,
    Column("workspace_id", Text, primary_key=True),
    Column("pipeline_id", Text, primary_key=True),
    Column("attempt_id", Text, nullable=False),
    Column("run_id", Text, nullable=False),
    Column("holder", Text, nullable=False),
    Column("generation", Integer, nullable=False),
    Column("expires_at", Integer, nullable=False),
)


def _migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "kernel_migrations"


def _raise_captured(failure: PersistenceError | None) -> NoReturn:
    if failure is None:
        raise AssertionError("missing captured persistence failure")
    raise failure


class SqliteKernelStore:
    def __init__(self, database_path: str) -> None:
        self._database_path = Path(database_path)
        self._url = f"sqlite:///{self._database_path.as_posix()}"
        self._fail_after: str | None = None
        self._fail_read = False
        self._upgrade()
        self._engine: Engine = create_engine(self._url, future=True, poolclass=NullPool)
        event.listen(self._engine, "connect", self._configure_connection)
        event.listen(self._engine, "begin", self._emit_explicit_begin)

    def trip_commit_failure(self) -> None:
        self._fail_after = "event"

    def trip_read_failure(self) -> None:
        self._fail_read = True

    def close(self) -> None:
        self._engine.dispose()

    def find_inbox(self, workspace_id: str, command_id: str) -> InboxRecord | None:
        failure: PersistenceError | None = None
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    select(_INBOX).where(
                        _INBOX.c.workspace_id == workspace_id,
                        _INBOX.c.command_id == command_id,
                    )
                ).first()
        except Exception as exc:
            failure = self._translate(exc)
        else:
            if row is None:
                return None
            return InboxRecord(
                workspace_id=str(row.workspace_id),
                command_id=str(row.command_id),
                command_fingerprint=str(row.command_fingerprint),
                receipt_json=str(row.receipt_json),
            )
        _raise_captured(failure)

    def load_pipeline(
        self, workspace_id: str, pipeline_id: str
    ) -> PipelineSnapshot | None:
        if self._fail_read:
            self._fail_read = False
            raise PersistenceError("persistence unavailable")
        if not workspace_id:
            return None
        failure: PersistenceError | None = None
        try:
            with self._engine.connect() as conn:
                stmt = select(_PIPELINES).where(
                    _PIPELINES.c.pipeline_id == pipeline_id,
                    _PIPELINES.c.workspace_id == workspace_id,
                )
                row = conn.execute(stmt).first()
        except Exception as exc:
            failure = self._translate(exc)
        else:
            if row is None:
                return None
            return PipelineSnapshot(
                workspace_id=str(row.workspace_id),
                pipeline_id=str(row.pipeline_id),
                status=str(row.status),
                revision=int(row.revision),
                text=str(row.text),
            )
        _raise_captured(failure)

    def commit_accepted(self, write: AcceptedWrite) -> None:
        failure: PersistenceError | None = None
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    _INBOX.insert().values(
                        workspace_id=write.inbox.workspace_id,
                        command_id=write.inbox.command_id,
                        command_fingerprint=write.inbox.command_fingerprint,
                        receipt_json=write.inbox.receipt_json,
                    )
                )
                conn.execute(
                    _EVENTS.insert().values(
                        event_id=write.event.event_id,
                        workspace_id=write.event.workspace_id,
                        pipeline_id=write.event.pipeline_id,
                        event_type=write.event.event_type,
                        payload_json=write.event.payload_json,
                        pipeline_revision=write.event.pipeline_revision,
                    )
                )
                conn.execute(
                    _OUTBOX.insert().values(
                        workspace_id=write.outbox.workspace_id,
                        command_id=write.outbox.command_id,
                        effect_type=write.outbox.effect_type,
                        payload_json=write.outbox.payload_json,
                        delivery_receipt_json=write.outbox.delivery_receipt_json,
                    )
                )
                if self._fail_after == "event":
                    self._fail_after = None
                    raise sqlite3.OperationalError("database or disk is full")
                upsert = insert(_PIPELINES).values(
                    workspace_id=write.pipeline.workspace_id,
                    pipeline_id=write.pipeline.pipeline_id,
                    status=write.pipeline.status,
                    revision=write.pipeline.revision,
                    text=write.pipeline.text,
                )
                conn.execute(
                    upsert.on_conflict_do_update(
                        index_elements=["workspace_id", "pipeline_id"],
                        set_={
                            "status": upsert.excluded.status,
                            "revision": upsert.excluded.revision,
                            "text": upsert.excluded.text,
                        },
                    )
                )
        except PersistenceError as exc:
            failure = exc
        except Exception as exc:
            failure = self._translate(exc)
        else:
            return
        _raise_captured(failure)

    def list_events(self, workspace_id: str, pipeline_id: str) -> list[EventWrite]:
        if not workspace_id:
            return []
        failure: PersistenceError | None = None
        try:
            with self._engine.connect() as conn:
                return self._list_events_on(conn, workspace_id, pipeline_id)
        except Exception as exc:
            failure = self._translate(exc)
        _raise_captured(failure)

    def delete_pipeline(self, workspace_id: str, pipeline_id: str) -> None:
        if not workspace_id:
            return
        failure: PersistenceError | None = None
        try:
            with self._engine.begin() as conn:
                self._delete_pipeline_on(conn, workspace_id, pipeline_id)
        except Exception as exc:
            failure = self._translate(exc)
        else:
            return
        _raise_captured(failure)

    def rebuild_pipeline(self, workspace_id: str, pipeline_id: str) -> PipelineSnapshot:
        if not workspace_id:
            return fold_pipeline_events("", pipeline_id, [])
        failure: PersistenceError | None = None
        try:
            with self._engine.begin() as conn:
                self._delete_pipeline_on(conn, workspace_id, pipeline_id)
                events = self._list_events_on(conn, workspace_id, pipeline_id)
                snapshot = fold_pipeline_events(workspace_id, pipeline_id, events)
                if workspace_id:
                    upsert = insert(_PIPELINES).values(
                        workspace_id=snapshot.workspace_id,
                        pipeline_id=snapshot.pipeline_id,
                        status=snapshot.status,
                        revision=snapshot.revision,
                        text=snapshot.text,
                    )
                    conn.execute(
                        upsert.on_conflict_do_update(
                            index_elements=["workspace_id", "pipeline_id"],
                            set_={
                                "status": upsert.excluded.status,
                                "revision": upsert.excluded.revision,
                                "text": upsert.excluded.text,
                            },
                        )
                    )
        except Exception as exc:
            failure = self._translate(exc)
        else:
            return snapshot
        _raise_captured(failure)

    def list_pending_outbox(self, workspace_id: str) -> list[OutboxRecord]:
        if not workspace_id:
            return []
        failure: PersistenceError | None = None
        try:
            with self._engine.connect() as conn:
                stmt = (
                    select(_OUTBOX)
                    .where(
                        _OUTBOX.c.workspace_id == workspace_id,
                        or_(
                            _OUTBOX.c.delivery_receipt_json.is_(None),
                            _OUTBOX.c.delivery_receipt_json == "",
                        ),
                    )
                    .order_by(_OUTBOX.c.command_id.asc())
                )
                rows = conn.execute(stmt).all()
        except Exception as exc:
            failure = self._translate(exc)
        else:
            return [self._outbox_from_row(row) for row in rows]
        _raise_captured(failure)

    def record_outbox_delivery(
        self, workspace_id: str, command_id: str, delivery_receipt_json: str
    ) -> None:
        if not workspace_id:
            return
        failure: PersistenceError | None = None
        try:
            with self._engine.begin() as conn:
                stmt = (
                    update(_OUTBOX)
                    .where(
                        _OUTBOX.c.workspace_id == workspace_id,
                        _OUTBOX.c.command_id == command_id,
                        or_(
                            _OUTBOX.c.delivery_receipt_json.is_(None),
                            _OUTBOX.c.delivery_receipt_json == "",
                        ),
                    )
                    .values(delivery_receipt_json=delivery_receipt_json)
                )
                conn.execute(stmt)
        except Exception as exc:
            failure = self._translate(exc)
        else:
            return
        _raise_captured(failure)

    def find_outbox(self, workspace_id: str, command_id: str) -> OutboxRecord | None:
        if not workspace_id:
            return None
        failure: PersistenceError | None = None
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    select(_OUTBOX).where(
                        _OUTBOX.c.workspace_id == workspace_id,
                        _OUTBOX.c.command_id == command_id,
                    )
                ).first()
        except Exception as exc:
            failure = self._translate(exc)
        else:
            if row is None:
                return None
            return self._outbox_from_row(row)
        _raise_captured(failure)

    def load_lease(self, workspace_id: str, pipeline_id: str) -> LeaseRecord | None:
        if not workspace_id:
            return None
        failure: PersistenceError | None = None
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    select(_LEASES).where(
                        _LEASES.c.workspace_id == workspace_id,
                        _LEASES.c.pipeline_id == pipeline_id,
                    )
                ).first()
        except Exception as exc:
            failure = self._translate(exc)
        else:
            if row is None:
                return None
            return self._lease_from_row(row)
        _raise_captured(failure)

    def save_lease(self, record: LeaseRecord) -> None:
        if not record.workspace_id:
            return
        failure: PersistenceError | None = None
        try:
            with self._engine.begin() as conn:
                upsert = insert(_LEASES).values(
                    workspace_id=record.workspace_id,
                    pipeline_id=record.pipeline_id,
                    attempt_id=record.attempt_id,
                    run_id=record.run_id,
                    holder=record.holder,
                    generation=record.generation,
                    expires_at=record.expires_at,
                )
                conn.execute(
                    upsert.on_conflict_do_update(
                        index_elements=["workspace_id", "pipeline_id"],
                        set_={
                            "attempt_id": upsert.excluded.attempt_id,
                            "run_id": upsert.excluded.run_id,
                            "holder": upsert.excluded.holder,
                            "generation": upsert.excluded.generation,
                            "expires_at": upsert.excluded.expires_at,
                        },
                    )
                )
        except Exception as exc:
            failure = self._translate(exc)
        else:
            return
        _raise_captured(failure)

    def delete_lease(self, workspace_id: str, pipeline_id: str) -> None:
        if not workspace_id:
            return
        failure: PersistenceError | None = None
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    delete(_LEASES).where(
                        _LEASES.c.workspace_id == workspace_id,
                        _LEASES.c.pipeline_id == pipeline_id,
                    )
                )
        except Exception as exc:
            failure = self._translate(exc)
        else:
            return
        _raise_captured(failure)

    def delete_expired_leases(self, now: int) -> None:
        failure: PersistenceError | None = None
        try:
            with self._engine.begin() as conn:
                conn.execute(delete(_LEASES).where(_LEASES.c.expires_at < now))
        except Exception as exc:
            failure = self._translate(exc)
        else:
            return
        _raise_captured(failure)

    def counts(self) -> StoreCounts:
        failure: PersistenceError | None = None
        try:
            with self._engine.connect() as conn:
                inbox = int(
                    conn.execute(select(func.count()).select_from(_INBOX)).scalar() or 0
                )
                events = int(
                    conn.execute(select(func.count()).select_from(_EVENTS)).scalar()
                    or 0
                )
                pipelines = int(
                    conn.execute(select(func.count()).select_from(_PIPELINES)).scalar()
                    or 0
                )
                outbox = int(
                    conn.execute(select(func.count()).select_from(_OUTBOX)).scalar()
                    or 0
                )
        except Exception as exc:
            failure = self._translate(exc)
        else:
            return StoreCounts(
                inbox=inbox, events=events, pipelines=pipelines, outbox=outbox
            )
        _raise_captured(failure)

    @staticmethod
    def _list_events_on(
        conn: Connection, workspace_id: str, pipeline_id: str
    ) -> list[EventWrite]:
        stmt = (
            select(_EVENTS)
            .where(
                _EVENTS.c.pipeline_id == pipeline_id,
                _EVENTS.c.workspace_id == workspace_id,
            )
            .order_by(_EVENTS.c.pipeline_revision.asc())
        )
        rows = conn.execute(stmt).all()
        return [
            EventWrite(
                event_id=str(row.event_id),
                workspace_id=str(row.workspace_id),
                pipeline_id=str(row.pipeline_id),
                event_type=str(row.event_type),
                payload_json=str(row.payload_json),
                pipeline_revision=int(row.pipeline_revision),
            )
            for row in rows
        ]

    @staticmethod
    def _outbox_from_row(row: Any) -> OutboxRecord:
        receipt = row.delivery_receipt_json
        receipt_json = None if receipt is None or receipt == "" else str(receipt)
        return OutboxRecord(
            workspace_id=str(row.workspace_id),
            command_id=str(row.command_id),
            effect_type=str(row.effect_type),
            payload_json=str(row.payload_json),
            delivery_receipt_json=receipt_json,
        )

    @staticmethod
    def _lease_from_row(row: Any) -> LeaseRecord:
        return LeaseRecord(
            workspace_id=str(row.workspace_id),
            pipeline_id=str(row.pipeline_id),
            attempt_id=str(row.attempt_id),
            run_id=str(row.run_id),
            holder=str(row.holder),
            generation=int(row.generation),
            expires_at=int(row.expires_at),
        )

    @staticmethod
    def _delete_pipeline_on(
        conn: Connection, workspace_id: str, pipeline_id: str
    ) -> None:
        stmt = delete(_PIPELINES).where(
            _PIPELINES.c.pipeline_id == pipeline_id,
            _PIPELINES.c.workspace_id == workspace_id,
        )
        conn.execute(stmt)

    def _upgrade(self) -> None:
        script_dir = _migrations_dir()
        cfg = Config(str(script_dir / "alembic.ini"))
        cfg.set_main_option("script_location", str(script_dir))
        cfg.set_main_option("sqlalchemy.url", self._url)
        command.upgrade(cfg, "head")

    @staticmethod
    def _configure_connection(
        dbapi_connection: object, _connection_record: object
    ) -> None:
        connection = cast(sqlite3.Connection, dbapi_connection)
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = FULL")
        cursor.close()

    @staticmethod
    def _emit_explicit_begin(conn: Connection) -> None:
        conn.exec_driver_sql("BEGIN")

    @staticmethod
    def _translate(_exc: Exception) -> PersistenceError:
        return PersistenceError("persistence unavailable")


__all__ = ["SqliteKernelStore"]
