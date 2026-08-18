"""SQLAlchemy Core SQLite adapter for ControllerTransactionStore.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_PHASE_01
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import NoReturn, cast

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    event,
    func,
    select,
)
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

from hermes_pipeline.controller.transaction_store import (
    AcceptedWrite,
    InboxRecord,
    PersistenceError,
    PipelineSnapshot,
    StoreCounts,
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
        self._upgrade()
        self._engine: Engine = create_engine(self._url, future=True, poolclass=NullPool)
        event.listen(self._engine, "connect", self._configure_connection)
        event.listen(self._engine, "begin", self._emit_explicit_begin)

    def trip_commit_failure(self) -> None:
        self._fail_after = "event"

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
        failure: PersistenceError | None = None
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    select(_PIPELINES).where(
                        _PIPELINES.c.workspace_id == workspace_id,
                        _PIPELINES.c.pipeline_id == pipeline_id,
                    )
                ).first()
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
        except Exception as exc:
            failure = self._translate(exc)
        else:
            return StoreCounts(inbox=inbox, events=events, pipelines=pipelines)
        _raise_captured(failure)

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
