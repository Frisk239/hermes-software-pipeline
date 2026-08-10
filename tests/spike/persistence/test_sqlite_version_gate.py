"""SQLite WAL-reset version gate tests (slice-00-04, AC-08).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

``sqlite3.sqlite_version`` is recorded and compared against the exact
WAL-reset repair-version predicate::

    >=3.51.3 OR (>=3.50.7 AND <3.51.0) OR (>=3.44.6 AND <3.45.0)

Positive: every committed accept vector passes. Negative: every committed
reject vector fails deterministically. A linked library failing the
predicate on a required platform stops the Slice with a Contract Change
Request before any spike persistence conclusion is claimed (stop
condition); the revision-7 interpreter pin is a precondition, never a
substitute, for this gate.
"""

from __future__ import annotations

import sqlite3

import pytest
from tests.conftest import (
    MAX_PLATFORM_EVIDENCE_LENGTH,
    MAX_PLATFORM_VERSION_LENGTH,
    bounded_version,
    platform_evidence_line,
)

from hermes_pipeline.persistence.sqlite_version_gate import (
    ACCEPT_VECTORS,
    REJECT_VECTORS,
    linked_sqlite_version,
    parse_version,
    wal_reset_predicate,
)


def test_accept_vectors_pass_deterministically() -> None:
    """Every committed accept vector satisfies the predicate."""
    for version in ACCEPT_VECTORS:
        assert wal_reset_predicate(version), f"accept vector {version} failed"


def test_reject_vectors_fail_deterministically() -> None:
    """Every committed reject vector fails the predicate."""
    for version in REJECT_VECTORS:
        assert not wal_reset_predicate(version), f"reject vector {version} passed"


def test_linked_sqlite_version_satisfies_predicate() -> None:
    """The linked library on this platform must pass the gate. A failure
    here is the Slice stop condition (Contract Change Request), not a
    recoverable test failure."""
    linked = linked_sqlite_version()
    assert wal_reset_predicate(linked), (
        f"linked SQLite {linked} fails the WAL-reset repair-version predicate"
    )


def test_candidate_bound_platform_evidence_is_bounded_and_records_sqlite() -> None:
    """The pytest header is visible in every successful CI matrix log and
    carries the actual linked SQLite value without host or environment data."""
    line = platform_evidence_line()
    safe_sqlite_version = bounded_version(sqlite3.sqlite_version)
    if (
        not line.startswith("slice-00-04 platform-evidence ")
        or f"sqlite_version={safe_sqlite_version}" not in line
        or "GITHUB_ACTIONS" in line
        or len(line) > MAX_PLATFORM_EVIDENCE_LENGTH
        or chr(10) in line
        or chr(13) in line
        or chr(9) in line
        or chr(7) in line
    ):
        raise AssertionError("platform evidence is not bounded")


def test_platform_version_evidence_rejects_controls_and_oversized_values() -> None:
    """The evidence header has a fixed cap even with hostile version input."""
    oversized = "9" * (MAX_PLATFORM_VERSION_LENGTH + 1)
    control = "3.53.1" + chr(10) + "detail" + chr(7)
    if bounded_version(oversized) != "unsupported":
        raise AssertionError("platform evidence accepted an oversized version")
    if bounded_version(control) != "unsupported":
        raise AssertionError("platform evidence accepted a controlled version")


def test_platform_evidence_sanitizes_a_mutated_sqlite_version_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The full header remains safe if its SQLite-version source is hostile."""
    canary = "sqlite-version-canary" + chr(10) + "detail" + chr(7)
    monkeypatch.setattr(sqlite3, "sqlite_version", canary)
    line = platform_evidence_line()
    if (
        "sqlite_version=unsupported" not in line
        or canary in line
        or len(line) > MAX_PLATFORM_EVIDENCE_LENGTH
        or chr(10) in line
        or chr(13) in line
        or chr(9) in line
        or chr(7) in line
    ):
        raise AssertionError("platform evidence leaked an untrusted version source")


def test_parse_version_handles_suffixed_versions() -> None:
    assert parse_version("3.51.3") == (3, 51, 3)
    assert parse_version("3.53.1") == (3, 53, 1)
    assert parse_version("3.12.10beta2") == (3, 12, 10)


def test_gate_boundaries_are_exact() -> None:
    """Boundary sanity: the predicate has no off-by-one around the fix
    points."""
    assert wal_reset_predicate((3, 51, 3))
    assert wal_reset_predicate((3, 50, 7))
    assert wal_reset_predicate((3, 50, 8))
    assert not wal_reset_predicate((3, 50, 6))
    assert not wal_reset_predicate((3, 51, 0))
    assert not wal_reset_predicate((3, 51, 2))
    assert not wal_reset_predicate((3, 49, 1))  # the revision-6 blocker
    assert wal_reset_predicate((3, 44, 6))
    assert not wal_reset_predicate((3, 44, 5))
