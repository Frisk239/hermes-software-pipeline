"""Process identity and stale-descriptor algorithm (slice-00-05, AC-04/AC-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

The stale-descriptor algorithm: a descriptor is stale only when
``os.kill(pid, 0)`` reports the process gone **or** the recorded start
marker mismatches the process currently holding the PID; ``os.kill`` alone
is never proof of identity.
"""

from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from hermes_pipeline.transport._identity import (
    process_matches_identity,
    read_process_start_marker,
)


def test_linux_stat_comm_with_parentheses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A legal process name containing ')' must not shift field 22.

    ``/proc/<pid>/stat`` is split after the LAST ')' of the comm field;
    field 22 (starttime) stays exact for names like ``proc) with )``.
    """
    from pathlib import Path

    stat_text = (
        "1234 (proc) with ) parens) S 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 "
        "15 16 17 999 18 19 20"
    )

    def fake_read_text(self: Path, encoding: str = "utf-8") -> str:
        return stat_text

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    from hermes_pipeline.transport._identity import (
        _linux_starttime_ticks,  # pyright: ignore[reportPrivateUsage]
    )

    assert _linux_starttime_ticks(1234) == "999"  # pyright: ignore[reportPrivateUsage]

    from hermes_shim._descriptor import (
        _linux_starttime_ticks as shim_ticks,  # pyright: ignore[reportPrivateUsage]
    )

    assert shim_ticks(1234) == "999"  # pyright: ignore[reportPrivateUsage]


def test_linux_zombie_marker_is_never_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A readable matching ``/proc`` marker does not make a zombie live."""
    from pathlib import Path

    from hermes_shim import _descriptor as shim_descriptor

    from hermes_pipeline.transport import _identity as runtime_identity

    stat_text = (
        "1234 (zombie) Z 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 999 18 19 20"
    )

    def fake_read_text(self: Path, encoding: str = "utf-8") -> str:
        return stat_text

    def fake_kill(_pid: int, _signal: int) -> None:
        return None

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    linux_os = SimpleNamespace(name="posix", kill=fake_kill)
    monkeypatch.setattr(runtime_identity, "os", linux_os)
    monkeypatch.setattr(shim_descriptor, "os", linux_os)

    marker = {"value": "999", "source": "proc_stat_field22"}
    assert runtime_identity._linux_process_is_zombie(1234)  # pyright: ignore[reportPrivateUsage]
    assert shim_descriptor._linux_process_is_zombie(1234)  # pyright: ignore[reportPrivateUsage]
    assert not runtime_identity.process_matches_identity(1234, marker)
    assert not shim_descriptor.process_matches_identity(1234, marker)


def test_self_process_marker_readable_and_matching() -> None:
    marker = read_process_start_marker(os.getpid())
    assert marker is not None
    assert isinstance(marker["value"], str) and marker["value"]
    assert marker["source"] in ("proc_stat_field22", "win_getprocess_times")
    assert process_matches_identity(os.getpid(), marker)


def test_wrong_marker_mismatches_live_process() -> None:
    marker = read_process_start_marker(os.getpid())
    assert marker is not None
    wrong = {"value": "0", "source": marker["source"]}
    assert not process_matches_identity(os.getpid(), wrong)


def test_unknown_pid_reports_gone() -> None:
    assert not process_matches_identity(2**31 - 1, {"value": "0", "source": "x"})


def test_unverifiable_identity_fails_closed() -> None:
    """When the marker cannot be compared, a live process must never be
    declared stale: absence of proof keeps the descriptor."""
    # The current process is alive; a missing/None marker must not turn
    # into a stale verdict (os.kill(pid, 0) alone is never deletion
    # evidence).
    assert process_matches_identity(os.getpid(), None) is True
    assert process_matches_identity(os.getpid(), "not-a-dict") is True
    # The shim side (used by doctor/status/start cleanup) is identical.
    from hermes_shim._descriptor import process_matches_identity as shim_matches

    assert shim_matches(os.getpid(), None) is True
    assert shim_matches(os.getpid(), {"value": "0", "source": "x"}) is False


def test_child_process_marker_stable() -> None:
    """A spawned child keeps one marker for its lifetime (checked while the
    child is still alive)."""
    import json

    code = (
        "import os, json, time\n"
        "from hermes_pipeline.transport._identity import read_process_start_marker\n"
        "print(json.dumps(read_process_start_marker(os.getpid())), flush=True)\n"
        "time.sleep(5)\n"
    )
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        stdout = proc.stdout
        assert stdout is not None
        line = stdout.readline()
        marker = json.loads(line.strip())
        # The child is still alive: the same marker must match its PID.
        assert process_matches_identity(proc.pid, marker)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
