"""Phase-01 SQLite KernelStore (slice-01-02).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_PHASE_01

The Controller kernel persists Inbox, Event, and Pipeline rows in one
explicit ``BEGIN IMMEDIATE`` transaction and rolls back completely on any
sqlite3 failure. Driver failures cross this boundary as
``KernelStoreError``; raw sqlite3 exceptions never reach the Controller.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager, suppress
from typing import Final

_SCHEMA: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS inbox (
        command_id TEXT PRIMARY KEY,
        payload_hash TEXT NOT NULL,
        receipt_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        pipeline_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pipelines (
        pipeline_id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        revision INTEGER NOT NULL,
        text TEXT NOT NULL
    )
    """,
)


class KernelStoreError(Exception):
    """Safe, sensitive-free persistence failure crossing the KernelStore boundary."""


class KernelStore:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.isolation_level = None
        self._ensure_schema()

    def close(self) -> None:
        self._conn.close()

    def _ensure_schema(self) -> None:
        for statement in _SCHEMA:
            self._conn.execute(statement)

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        try:
            self._conn.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise KernelStoreError from exc
        try:
            yield
            self._conn.execute("COMMIT")
        except sqlite3.Error as exc:
            self._rollback()
            raise KernelStoreError from exc
        except BaseException:
            self._rollback()
            raise

    def _rollback(self) -> None:
        with suppress(sqlite3.Error):
            self._conn.execute("ROLLBACK")

    def find_inbox(self, command_id: str) -> tuple[str, str] | None:
        row = self._conn.execute(
            "SELECT payload_hash, receipt_json FROM inbox WHERE command_id = ?",
            (command_id,),
        ).fetchone()
        if row is None:
            return None
        return str(row[0]), str(row[1])

    def load_pipeline(self, pipeline_id: str) -> tuple[str, int, str] | None:
        row = self._conn.execute(
            "SELECT status, revision, text FROM pipelines WHERE pipeline_id = ?",
            (pipeline_id,),
        ).fetchone()
        if row is None:
            return None
        return str(row[0]), int(row[1]), str(row[2])

    def insert_inbox(
        self, command_id: str, payload_hash: str, receipt_json: str
    ) -> None:
        self._conn.execute(
            "INSERT INTO inbox (command_id, payload_hash, receipt_json)"
            " VALUES (?, ?, ?)",
            (command_id, payload_hash, receipt_json),
        )

    def insert_event(self, pipeline_id: str, event_type: str, payload_json: str) -> int:
        cursor = self._conn.execute(
            "INSERT INTO events (pipeline_id, event_type, payload_json)"
            " VALUES (?, ?, ?)",
            (pipeline_id, event_type, payload_json),
        )
        lastrowid = cursor.lastrowid
        if lastrowid is None:
            raise sqlite3.OperationalError("missing event id")
        return int(lastrowid)

    def upsert_pipeline(
        self, pipeline_id: str, status: str, revision: int, text: str
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO pipelines (pipeline_id, status, revision, text)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(pipeline_id) DO UPDATE SET
                status = excluded.status,
                revision = excluded.revision,
                text = excluded.text
            """,
            (pipeline_id, status, revision, text),
        )


__all__ = ["KernelStore", "KernelStoreError"]
