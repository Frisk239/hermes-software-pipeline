"""Shared test setup (slice-00-02).

Adds the repository root and the bootstrap ``scripts/`` directory to the
import path so tests can drive the dependency-free checkers in-process,
and exposes the deterministic facilities: a frozen UTC clock, an identity
sequence, and an auto-cleaned temporary root.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from facilities import DeterministicIdentitySequence, FrozenUtcClock

_REPO_ROOT = Path(__file__).resolve().parents[1]
# Hypothesis creates a constants store even when its example database is
# disabled. Keep that generated state inside the managed virtual environment
# so the repository artifact audit remains meaningful after every test run.
os.environ.setdefault(
    "HYPOTHESIS_STORAGE_DIRECTORY", str(_REPO_ROOT / ".venv" / ".hypothesis")
)
for _entry in (str(_REPO_ROOT / "scripts"), str(_REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)


@pytest.fixture
def frozen_utc_clock() -> FrozenUtcClock:
    """A clock frozen at a fixed UTC instant; never reads the wall clock."""
    return FrozenUtcClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))


@pytest.fixture
def identity_sequence() -> DeterministicIdentitySequence:
    """A deterministic identity sequence starting at id-0."""
    return DeterministicIdentitySequence()


@pytest.fixture
def auto_temp_root() -> Iterator[Path]:
    """A temporary root deleted automatically after the test.

    Built on ``tempfile.mkdtemp`` so cleanup is owned by this fixture and
    is provably complete before the fixture returns.
    """
    root = Path(tempfile.mkdtemp(prefix="hermes-pipeline-test-"))
    yield root
    shutil.rmtree(root, ignore_errors=True)
    assert not root.exists(), "temporary root must be cleaned up"
