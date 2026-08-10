"""Stage lease and fencing spike (slice-00-04, AC-10).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Stage Attempt/Run leases carry monotonically increasing fencing
generations. A result carrying an expired or superseded generation is
rejected, and a generation takeover fences the stale holder. Only a result
whose generation is exactly equal to the current generation is accepted —
a fabricated future generation is also rejected, because fencing accepts
the authoritative current generation and nothing else. The spike lease is
not a production lock: it exists only to produce written feasibility
evidence for the fencing boundary.

The lease table lives in the Controller database file (one SQLite file for
the spike Inbox, Event, projection, Outbox, receipt, and lease tables) and
uses the standard library ``sqlite3`` module with explicit transactions
(never the legacy implicit transaction control: every statement batch runs
inside an explicit ``BEGIN IMMEDIATE`` / ``COMMIT`` pair).
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn

#: A lease is held for one fixed deterministic duration; the spike clock is
#: injected so tests are fully deterministic.
LEASE_DURATION_SECONDS = 60


@dataclass(frozen=True)
class Lease:
    """One lease row: holder, generation, and expiry (epoch seconds)."""

    holder: str
    generation: int
    expires_at: int


@dataclass(frozen=True)
class LeaseVerdict:
    """Bounded typed verdict of one lease operation."""

    outcome: Literal["ACQUIRED", "RENEWED", "REJECTED_STALE", "REJECTED_EXPIRED"]
    generation: int
    holder: str


class LeaseFailure(Exception):
    """Bounded typed failure for the experimental lease Interface."""


def _raise_lease_failure() -> NoReturn:
    """Raise only after a raw driver exception handler has completed."""
    raise LeaseFailure("lease persistence unavailable")


class LeaseStore:
    """SQLite-backed spike lease store with fencing generations.

    ``clock`` is an injected ``() -> int`` epoch-seconds provider so tests
    never depend on wall time.
    """

    def __init__(self, database_path: Path | str, clock: Callable[[], int]) -> None:
        self._clock = clock
        connection: sqlite3.Connection | None = None
        try:
            self._database_path = Path(database_path)
            connection = sqlite3.connect(self._database_path, isolation_level=None)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS spike_leases ("
                " lease_name TEXT PRIMARY KEY,"
                " holder TEXT NOT NULL,"
                " generation INTEGER NOT NULL,"
                " expires_at INTEGER NOT NULL"
                ")"
            )
            connection.commit()
        except Exception:
            if connection is not None:
                try:
                    connection.rollback()
                    connection.close()
                except Exception:
                    pass
        else:
            self._connection = connection
            return
        _raise_lease_failure()

    def close(self) -> None:
        """Close the underlying connection."""
        try:
            self._connection.close()
        except Exception:
            # ``close`` has no result channel; retain its idempotent,
            # non-throwing cleanup semantics without exposing driver text.
            return

    def _now(self) -> int:
        return int(self._clock())

    def acquire(self, name: str, holder: str) -> LeaseVerdict:
        """Acquire (or take over) the named lease with a new generation.

        A takeover increments the generation, fencing the stale holder.
        Returns the current generation for the holder when the lease is
        already held by it and still valid.
        """
        conn = self._connection
        try:
            now = self._now()
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT holder, generation, expires_at FROM spike_leases "
                "WHERE lease_name = ?",
                (name,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO spike_leases "
                    "(lease_name, holder, generation, expires_at) "
                    "VALUES (?, ?, 1, ?)",
                    (name, holder, now + LEASE_DURATION_SECONDS),
                )
                conn.commit()
                return LeaseVerdict("ACQUIRED", 1, holder)
            existing_holder, generation, expires_at = row
            if existing_holder == holder and expires_at > now:
                conn.commit()
                return LeaseVerdict("RENEWED", int(generation), holder)
            # Takeover: monotonic generation bump fences the stale holder.
            new_generation = int(generation) + 1
            conn.execute(
                "UPDATE spike_leases SET holder = ?, generation = ?, expires_at = ? "
                "WHERE lease_name = ?",
                (holder, new_generation, now + LEASE_DURATION_SECONDS, name),
            )
            conn.commit()
            return LeaseVerdict("ACQUIRED", new_generation, holder)
        except Exception:
            with contextlib.suppress(Exception):
                conn.rollback()
        _raise_lease_failure()

    def submit_result(self, name: str, holder: str, generation: int) -> LeaseVerdict:
        """Verdict for one result carrying a fencing generation.

        Only a result whose generation is *exactly equal* to the current
        lease generation (from the current holder, not expired) is accepted.
        A superseded (older) generation, a fabricated *future* generation,
        a different holder, or an expired lease rejects the result; the
        verdict always reports the authoritative current generation.
        """
        try:
            now = self._now()
            row = self._connection.execute(
                "SELECT holder, generation, expires_at FROM spike_leases "
                "WHERE lease_name = ?",
                (name,),
            ).fetchone()
            if row is None:
                return LeaseVerdict("REJECTED_EXPIRED", generation, holder)
            current_holder, current_generation, expires_at = row
            current = int(current_generation)
            if current_holder != holder or generation != current:
                return LeaseVerdict("REJECTED_STALE", current, holder)
            if expires_at <= now:
                return LeaseVerdict("REJECTED_EXPIRED", current, holder)
            return LeaseVerdict("RENEWED", current, holder)
        except Exception:
            pass
        _raise_lease_failure()

    def read(self, name: str) -> Lease | None:
        """Read the current lease row (for assertions)."""
        try:
            row = self._connection.execute(
                "SELECT holder, generation, expires_at FROM spike_leases "
                "WHERE lease_name = ?",
                (name,),
            ).fetchone()
            if row is None:
                return None
            return Lease(
                holder=str(row[0]), generation=int(row[1]), expires_at=int(row[2])
            )
        except Exception:
            pass
        _raise_lease_failure()


__all__ = [
    "LEASE_DURATION_SECONDS",
    "Lease",
    "LeaseFailure",
    "LeaseStore",
    "LeaseVerdict",
]
