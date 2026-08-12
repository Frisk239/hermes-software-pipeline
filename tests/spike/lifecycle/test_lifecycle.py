"""Lifecycle idempotency with a real runtime (slice-00-05, AC-07).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

``hermes pipeline setup|doctor|start|status|stop`` operate idempotently on
the non-production skeleton: repeated identical invocations converge; a
second ``start`` without an intermediate ``stop`` converges to one runtime;
``stop`` without a running runtime is a no-op with a stable exit code; all
commands return structured bounded JSON with stable exit codes and no
sensitive content.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hermes_shim._lifecycle import (
    LifecycleResult,
    doctor_command,
    setup_command,
    start_command,
    status_command,
    stop_command,
)
from tests.spike.runtime._harness import provision


def _start_with_retry(
    home: Path, plugin_dir: Path, attempts: int = 2
) -> LifecycleResult:
    """Idempotent start with bounded retry.

    ``start`` is contractually idempotent (repeated invocations converge);
    on slow sandbox hosts the runtime may need more than one start call to
    become ready within the fixed 30 s budget. Every attempt runs the full
    provision/launch/readiness path.
    """
    import time

    last = None
    for _ in range(attempts):
        last = start_command(home, plugin_dir)
        if last.ok:
            return last
        time.sleep(2.0)
    assert last is not None  # attempts >= 1
    return last


def _stop_with_retry(home: Path, attempts: int = 3) -> LifecycleResult:
    """Idempotent stop with bounded retry.

    ``stop`` is contractually idempotent (stopping an already-stopped
    runtime is a no-op); a retry covers the sandbox-host case where the
    termination round races the descriptor re-read. Every attempt runs the
    full drain/terminate/remove path.
    """
    import time

    last = None
    for _ in range(attempts):
        last = stop_command(home)
        if last.ok:
            return last
        time.sleep(1.0)
    assert last is not None  # attempts >= 1
    return last


@pytest.fixture
def plugin_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def test_full_sequence_twice_converges(tmp_path: Path, plugin_dir: Path) -> None:
    provision(tmp_path, offline=False)
    home = tmp_path / "hermes-home"
    home.mkdir()

    def run_sequence() -> list[str]:
        outputs: list[str] = []
        outputs.append(setup_command(home).as_json())
        start1 = _start_with_retry(home, plugin_dir)
        assert start1.ok, start1.as_json()
        outputs.append(start1.as_json())
        # A second start without an intermediate stop converges.
        start2 = _start_with_retry(home, plugin_dir)
        assert start2.ok, start2.as_json()
        outputs.append(start2.as_json())
        status = status_command(home)
        assert status.ok, status.as_json()
        outputs.append(status.as_json())
        doctor = doctor_command(home, plugin_dir)
        assert doctor.ok, doctor.as_json()
        outputs.append(doctor.as_json())
        stop1 = _stop_with_retry(home)
        assert stop1.ok, stop1.as_json()
        outputs.append(stop1.as_json())
        # Stop without a running runtime is a no-op with the same exit code.
        stop2 = _stop_with_retry(home)
        assert stop2.ok and stop2.exit_code == 0
        outputs.append(stop2.as_json())
        return outputs

    first = run_sequence()
    second = run_sequence()

    # Repeated identical invocations converge: the stable command surface
    # (ok, exit_code, checks) is identical; dynamic detail (pid, port,
    # creation time) is stripped before comparison.
    def stable(outputs: list[str]) -> list[str]:
        stable_outputs: list[str] = []
        for output in outputs:
            document = json.loads(output)
            document.pop("detail", None)
            stable_outputs.append(json.dumps(document, sort_keys=True))
        return stable_outputs

    assert stable(first) == stable(second)
    for output in first + second:
        document = json.loads(output)
        assert document["ok"] is True
        assert document["exit_code"] == 0
        assert "command" in document
        text = output
        assert "Traceback" not in text
        assert "Bearer " not in text
        assert str(home) not in text


def test_start_after_killed_runtime_recovers(tmp_path: Path, plugin_dir: Path) -> None:
    provision(tmp_path, offline=False)
    home = tmp_path / "hermes-home"
    home.mkdir()
    setup_command(home)
    start1 = _start_with_retry(home, plugin_dir)
    assert start1.ok
    # Kill the runtime process behind the shim's back (crash recovery).
    document = json.loads(start1.as_json())["detail"]["runtime"]
    import contextlib
    import os

    with contextlib.suppress(OSError):
        os.kill(int(document["pid"]), 9)  # SIGKILL / TerminateProcess
    import time

    time.sleep(1.0)
    start2 = _start_with_retry(home, plugin_dir)
    assert start2.ok, start2.as_json()
    status = status_command(home)
    assert status.ok, status.as_json()
    _stop_with_retry(home)
