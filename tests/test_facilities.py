"""Deterministic test facilities and framework smokes (AC-06).

The frozen UTC clock, identity sequence, and temp-root cleanup are pure and
injectable; the pytest-asyncio and Hypothesis smokes prove the async and
property-testing facilities work without wall time, network, credentials,
or user directories.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from facilities import DeterministicIdentitySequence, FrozenUtcClock

FROZEN_INSTANT = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


def test_frozen_utc_clock_is_fixed_and_utc(
    frozen_utc_clock: FrozenUtcClock,
) -> None:
    assert frozen_utc_clock.now() == FROZEN_INSTANT
    assert frozen_utc_clock.now().tzinfo is UTC


def test_frozen_utc_clock_never_moves(
    frozen_utc_clock: FrozenUtcClock,
) -> None:
    assert frozen_utc_clock.now() == frozen_utc_clock.now()


def test_identity_sequence_is_deterministic() -> None:
    first = DeterministicIdentitySequence(prefix="stage-", start=7)
    second = DeterministicIdentitySequence(prefix="stage-", start=7)
    assert [first.next_id() for _ in range(3)] == [second.next_id() for _ in range(3)]


def test_identity_sequence_is_monotonic(
    identity_sequence: DeterministicIdentitySequence,
) -> None:
    assert [identity_sequence.next_id() for _ in range(5)] == [
        "id-0",
        "id-1",
        "id-2",
        "id-3",
        "id-4",
    ]


def test_temp_root_can_hold_files(auto_temp_root: Path) -> None:
    marker = auto_temp_root / "marker.txt"
    marker.write_text("x", encoding="utf-8")
    assert marker.is_file()


async def test_pytest_asyncio_smoke() -> None:
    assert await _double(21) == 42


async def _double(value: int) -> int:
    return value * 2


@settings(database=None, derandomize=True, deadline=None, max_examples=100)
@given(st.integers(min_value=0, max_value=10_000))
def test_hypothesis_deterministic_property_smoke(value: int) -> None:
    assert sorted([value, value]) == [value, value]
