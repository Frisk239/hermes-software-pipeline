"""State-root singleton lock (slice-00-05, AC-04/AC-10).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Two runtimes may not claim one state root: a second lock acquisition on
the same state root fails closed, and release allows re-acquisition.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from hermes_pipeline.transport._lock import StateRootLock, StateRootLockError


def test_second_acquisition_fails_closed(tmp_path: Path) -> None:
    first = StateRootLock(tmp_path)
    first.acquire()
    second = StateRootLock(tmp_path)
    with pytest.raises(StateRootLockError):
        second.acquire()
    first.release()
    second.acquire()
    second.release()


def test_release_is_idempotent(tmp_path: Path) -> None:
    lock = StateRootLock(tmp_path)
    lock.acquire()
    lock.release()
    lock.release()  # must not raise


def test_context_manager(tmp_path: Path) -> None:
    with StateRootLock(tmp_path):
        other = StateRootLock(tmp_path)
        with pytest.raises(StateRootLockError):
            other.acquire()
    reacquire = StateRootLock(tmp_path)
    reacquire.acquire()
    reacquire.release()


def test_lock_cross_process(tmp_path: Path) -> None:
    """A second process cannot acquire the held lock."""
    first = StateRootLock(tmp_path)
    first.acquire()
    code = (
        "import sys\n"
        "from hermes_pipeline.transport._lock import StateRootLock\n"
        "from hermes_pipeline.transport._lock import StateRootLockError\n"
        "try:\n"
        "    StateRootLock(__import__('pathlib').Path(sys.argv[1])).acquire()\n"
        "    print('ACQUIRED')\n"
        "except StateRootLockError:\n"
        "    print('LOCKED')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "LOCKED"
    first.release()
    proc = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.stdout.strip() == "ACQUIRED"
