"""Lease and fencing tests (slice-00-04, AC-10).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Stage Attempt/Run leases carry monotonically increasing fencing
generations. Positive: the current generation accepts its result; a newer
generation fences the stale holder. Negative: a stale-generation result,
an expired lease, a result from a superseded holder, or a fabricated
future generation is rejected (fencing accepts only the authoritative
current generation). The spike lease is not a production lock.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from hermes_pipeline.persistence.leases import (
    LEASE_DURATION_SECONDS,
    LeaseFailure,
    LeaseStore,
)
from hermes_pipeline.persistence.sqlite_spike import SqliteControllerStore


class _ManualClock:
    """Deterministic clock; tests advance time explicitly."""

    def __init__(self, start: int = 1_000_000) -> None:
        self._now = start

    def __call__(self) -> int:
        return self._now

    def advance(self, seconds: int) -> None:
        self._now += seconds


def _assert_safe_lease_failure(error: LeaseFailure) -> None:
    """Check a lease boundary error without echoing driver-derived details."""
    if (
        str(error) != "lease persistence unavailable"
        or error.__cause__ is not None
        or error.__context__ is not None
    ):
        raise AssertionError("lease store leaked an unsafe persistence failure")


def test_lease_table_shares_the_controller_database_file(tmp_path: Path) -> None:
    """AC-10: the five Controller tables and lease table use one SQLite file."""
    database = tmp_path / "controller-with-leases.db"
    controller_store = SqliteControllerStore(database)
    lease_store = LeaseStore(database, _ManualClock())
    connection = sqlite3.connect(database)
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        connection.close()

    assert {
        "spike_inbox",
        "spike_events",
        "spike_projection",
        "spike_outbox",
        "spike_receipts",
        "spike_leases",
    } <= tables
    lease_store.close()
    controller_store.close()


def test_closed_lease_store_returns_only_typed_safe_failures(tmp_path: Path) -> None:
    """A closed database cannot leak sqlite3 exceptions through LeaseStore."""
    store = LeaseStore(tmp_path / "closed-acquire.db", _ManualClock())
    store.close()
    with pytest.raises(LeaseFailure) as excinfo:
        store.acquire("run-1", "holder-a")
    _assert_safe_lease_failure(excinfo.value)

    store = LeaseStore(tmp_path / "closed-submit.db", _ManualClock())
    store.close()
    with pytest.raises(LeaseFailure) as excinfo:
        store.submit_result("run-1", "holder-a", 1)
    _assert_safe_lease_failure(excinfo.value)

    store = LeaseStore(tmp_path / "closed-read.db", _ManualClock())
    store.close()
    with pytest.raises(LeaseFailure) as excinfo:
        store.read("run-1")
    _assert_safe_lease_failure(excinfo.value)


def test_unopenable_lease_database_returns_only_typed_safe_failure(
    tmp_path: Path,
) -> None:
    """Construction also translates a raw sqlite3 open failure."""
    directory_as_database = tmp_path / "not-a-database-file"
    directory_as_database.mkdir()
    with pytest.raises(LeaseFailure) as excinfo:
        LeaseStore(directory_as_database, _ManualClock())
    _assert_safe_lease_failure(excinfo.value)


def test_acquire_first_lease_generation_one(
    tmp_path: Path,
) -> None:
    clock = _ManualClock()
    store = LeaseStore(tmp_path / "leases.db", clock)
    verdict = store.acquire("run-1", "holder-a")
    assert verdict.outcome == "ACQUIRED"
    assert verdict.generation == 1
    assert verdict.holder == "holder-a"
    lease = store.read("run-1")
    assert lease is not None
    assert lease.generation == 1
    assert lease.holder == "holder-a"
    store.close()


def test_current_generation_accepts_result(tmp_path: Path) -> None:
    clock = _ManualClock()
    store = LeaseStore(tmp_path / "leases.db", clock)
    store.acquire("run-1", "holder-a")
    verdict = store.submit_result("run-1", "holder-a", 1)
    assert verdict.outcome == "RENEWED"
    assert verdict.generation == 1
    store.close()


def test_stale_generation_result_rejected(tmp_path: Path) -> None:
    clock = _ManualClock()
    store = LeaseStore(tmp_path / "leases.db", clock)
    store.acquire("run-1", "holder-a")
    # Holder b takes over: generation becomes 2 and fences holder a.
    takeover = store.acquire("run-1", "holder-b")
    assert takeover.outcome == "ACQUIRED"
    assert takeover.generation == 2
    stale = store.submit_result("run-1", "holder-a", 1)
    assert stale.outcome == "REJECTED_STALE"
    assert stale.generation == 2
    store.close()


def test_superseded_holder_result_rejected(tmp_path: Path) -> None:
    clock = _ManualClock()
    store = LeaseStore(tmp_path / "leases.db", clock)
    store.acquire("run-1", "holder-a")
    store.acquire("run-1", "holder-b")
    store.acquire("run-1", "holder-c")
    verdict = store.submit_result("run-1", "holder-b", 2)
    assert verdict.outcome == "REJECTED_STALE"
    assert verdict.generation == 3
    store.close()


def test_expired_lease_rejected(tmp_path: Path) -> None:
    clock = _ManualClock()
    store = LeaseStore(tmp_path / "leases.db", clock)
    store.acquire("run-1", "holder-a")
    clock.advance(LEASE_DURATION_SECONDS + 1)
    verdict = store.submit_result("run-1", "holder-a", 1)
    assert verdict.outcome == "REJECTED_EXPIRED"
    store.close()


def test_future_generation_result_rejected(tmp_path: Path) -> None:
    """Negative: a fabricated future generation is rejected. Fencing accepts
    only a result whose generation is exactly equal to the authoritative
    current generation; a forged higher generation can never advance."""
    clock = _ManualClock()
    store = LeaseStore(tmp_path / "leases.db", clock)
    store.acquire("run-1", "holder-a")
    forged = store.submit_result("run-1", "holder-a", 99)
    assert forged.outcome == "REJECTED_STALE"
    assert forged.generation == 1  # the authoritative current generation
    forged_again = store.submit_result("run-1", "holder-a", 2)
    assert forged_again.outcome == "REJECTED_STALE"
    assert forged_again.generation == 1
    # The current generation still accepts its own result afterwards.
    current = store.submit_result("run-1", "holder-a", 1)
    assert current.outcome == "RENEWED"
    assert current.generation == 1
    store.close()


def test_takeover_after_expiry_gets_next_generation(tmp_path: Path) -> None:
    clock = _ManualClock()
    store = LeaseStore(tmp_path / "leases.db", clock)
    store.acquire("run-1", "holder-a")
    clock.advance(LEASE_DURATION_SECONDS + 1)
    verdict = store.acquire("run-1", "holder-b")
    assert verdict.outcome == "ACQUIRED"
    assert verdict.generation == 2  # monotonic, never reused
    store.close()


def test_generations_are_monotonically_increasing(tmp_path: Path) -> None:
    clock = _ManualClock()
    store = LeaseStore(tmp_path / "leases.db", clock)
    seen: list[int] = []
    for holder in ("a", "b", "c", "d"):
        verdict = store.acquire("run-1", holder)
        assert verdict.outcome == "ACQUIRED"
        seen.append(verdict.generation)
    assert seen == [1, 2, 3, 4]
    store.close()
