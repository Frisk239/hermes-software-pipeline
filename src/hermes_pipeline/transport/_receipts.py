"""Disposable fake receipt store (slice-00-05, fixed decision D4).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

The fake runtime accepts one fake Controller-command envelope
(``command_id`` + payload) and persists a receipt with stdlib ``sqlite3``
in the disposable state root. A duplicate ``command_id`` returns the
original receipt unchanged (the persisted values are never rewritten); the
receipt row and the single effect commit atomically, so the three crash
points converge to exactly one acknowledged result. The store and its data
are disposable spike artifacts with an explicit disposition and never
become production persistence. The database path must stay inside the
state root (symlink escape rejected before any file is created).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ._state import ensure_inside_state_root

_SCHEMA = """
CREATE TABLE IF NOT EXISTS receipts (
    command_id TEXT PRIMARY KEY,
    payload_hash TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    effect_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS effects (
    command_id TEXT PRIMARY KEY,
    effect_count INTEGER NOT NULL
);
"""


class ReceiptStore:
    """Stdlib sqlite3 receipt store in the disposable state root.

    The store derives its database path from an explicit trusted
    ``state_root`` (never from path inference), and every file operation
    is guarded before any mkdir/connect so a symlinked/junctioned
    descriptor directory can never redirect the database outside the root.
    """

    def __init__(self, state_root: Path) -> None:
        self._root = state_root
        self._db_path = state_root / "descriptor" / "receipts.sqlite3"

    def _guard(self) -> None:
        ensure_inside_state_root(self._root, self._db_path)

    def open(self) -> None:
        """Create the schema idempotently (file is disposable)."""
        self._guard()
        db_path = self._db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_path)) as conn:
            conn.executescript(_SCHEMA)

    def process(self, command_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Process one fake command exactly once and return its receipt.

        The effect (one counter increment) and the receipt row commit in one
        transaction: a crash before this call leaves no row and no effect
        (retry processes afresh); a crash after commit is answered by the
        dedup path on retry (original receipt, no second effect).
        """
        payload_hash = _stable_hash(command_id, payload)
        self._guard()
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT receipt_json FROM receipts WHERE command_id = ?",
                (command_id,),
            ).fetchone()
            if row is not None:
                conn.commit()
                # Return the persisted receipt unchanged: a duplicate
                # command returns the original values exactly (never a
                # rewritten flag), so retries cannot fabricate state.
                return json.loads(row[0])
            effect_row = conn.execute(
                "SELECT effect_count FROM effects WHERE command_id = ?",
                (command_id,),
            ).fetchone()
            if effect_row is None:
                conn.execute(
                    "INSERT INTO effects (command_id, effect_count) VALUES (?, 1)",
                    (command_id,),
                )
                effect_count = 1
            else:
                effect_count = int(effect_row[0]) + 1
                conn.execute(
                    "UPDATE effects SET effect_count = ? WHERE command_id = ?",
                    (effect_count, command_id),
                )
            receipt = {
                "command_id": command_id,
                "payload_hash": payload_hash,
                "effect_count": effect_count,
                "deduplicated": False,
                "processed_at": "2026-01-01T00:00:00Z",
            }
            conn.execute(
                "INSERT INTO receipts (command_id, payload_hash, receipt_json,"
                " effect_count, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    command_id,
                    payload_hash,
                    json.dumps(receipt, sort_keys=True, separators=(",", ":")),
                    effect_count,
                    receipt["processed_at"],
                ),
            )
            conn.commit()
            return receipt

    def get(self, command_id: str) -> dict[str, Any] | None:
        """The persisted receipt for one command id (None when absent)."""
        self._guard()
        with sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                "SELECT receipt_json FROM receipts WHERE command_id = ?",
                (command_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def effect_count(self, command_id: str) -> int:
        """The total effect count for one command id."""
        self._guard()
        with sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                "SELECT effect_count FROM effects WHERE command_id = ?",
                (command_id,),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def is_forged(self, command_id: str, receipt: dict[str, Any]) -> bool:
        """True when a receipt does not match the persisted row."""
        persisted = self.get(command_id)
        if persisted is None:
            return True
        compare = dict(receipt)
        compare.pop("deduplicated", None)
        persisted_compare = dict(persisted)
        persisted_compare.pop("deduplicated", None)
        return compare != persisted_compare


def _stable_hash(command_id: str, payload: dict[str, Any]) -> str:
    import hashlib

    canonical = json.dumps(
        {"command_id": command_id, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


__all__ = ["ReceiptStore"]
