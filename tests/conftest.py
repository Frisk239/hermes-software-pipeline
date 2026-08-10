"""Shared test setup (slice-00-02).

Exposes deterministic facilities: a frozen UTC clock, an identity sequence,
and an auto-cleaned temporary root. Bootstrap scripts are loaded only through
the CLI's isolated loader in the individual tests, so test collection never
mutates interpreter import state.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import sqlite3
import sys
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from facilities import DeterministicIdentitySequence, FrozenUtcClock

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ALLOWED_OS_FAMILIES = frozenset({"Windows", "Linux", "Darwin"})
_ALLOWED_ARCHITECTURES = frozenset(
    {"AMD64", "x86_64", "aarch64", "arm64", "x86", "i386", "i686"}
)
_VERSION_PATTERN = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
MAX_PLATFORM_VERSION_LENGTH = 32
MAX_PLATFORM_EVIDENCE_LENGTH = 256
# Hypothesis creates a constants store even when its example database is
# disabled. Keep that generated state inside the managed virtual environment
# so the repository artifact audit remains meaningful after every test run.
os.environ.setdefault(
    "HYPOTHESIS_STORAGE_DIRECTORY", str(_REPO_ROOT / ".venv" / ".hypothesis")
)


def _bounded_runner_label(os_family: str) -> str:
    """Derive a finite CI label without emitting environment values."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return "local"
    return {"Windows": "windows-latest", "Linux": "ubuntu-latest"}.get(
        os_family, "local"
    )


def _bounded_platform_value(value: str, allowed: frozenset[str]) -> str:
    """Fail closed rather than print an unexpected platform-provided value."""
    return value if type(value) is str and value in allowed else "unsupported"


def bounded_version(value: str) -> str:
    """Render only a conventional numeric version string in test output."""
    if type(value) is not str or len(value) > MAX_PLATFORM_VERSION_LENGTH:
        return "unsupported"
    return value if _VERSION_PATTERN.fullmatch(value) else "unsupported"


def platform_evidence_line() -> str:
    """One bounded, redacted per-platform AC-08 evidence line.

    Pytest prints this header before every successful test run, including each
    GitHub Actions matrix job.  It deliberately renders only the five fields
    permitted by the Slice contract; it never serializes environment values,
    hostnames, usernames, paths, or database content.
    """
    os_family = _bounded_platform_value(platform.system(), _ALLOWED_OS_FAMILIES)
    architecture = _bounded_platform_value(platform.machine(), _ALLOWED_ARCHITECTURES)
    python_version = bounded_version(
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    sqlite_version = bounded_version(sqlite3.sqlite_version)
    line = (
        "slice-00-04 platform-evidence "
        f"os_family={os_family} "
        f"architecture={architecture} "
        f"ci_runner_label={_bounded_runner_label(os_family)} "
        f"python_version={python_version} "
        f"sqlite_version={sqlite_version}"
    )
    if len(line) > MAX_PLATFORM_EVIDENCE_LENGTH:
        return "slice-00-04 platform-evidence unsupported"
    return line


def pytest_report_header(config: pytest.Config) -> str:
    """Record the candidate-bound platform evidence in every pytest log."""
    del config
    return platform_evidence_line()


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
