"""Real subprocess crash matrix (slice-00-04, AC-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

A real subprocess crash is injected only at the durable boundaries
(pre-commit and post-commit of the five-record transaction), followed by a
fresh-process restart from the same database and WAL. The matrix proves:

- no duplicate Event and no lost acknowledged command after either crash
  point;
- recovery reconciles Inbox, Event, projection, Outbox, and receipt;
- re-driving the acknowledged command path after the post-commit crash
  returns the original receipt without appending a second Event;
- ordinary in-transaction exception injection (AC-03) is never presented as
  process-crash evidence (negative fixture).
"""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest
from tests.spike.conftest import make_spike_command

from hermes_pipeline.controller._persistence_port import FaultSpec
from hermes_pipeline.controller.spike_controller import SpikeController
from hermes_pipeline.persistence.sqlite_spike import (
    CRASH_EXIT_POST_COMMIT,
    CRASH_EXIT_PRE_COMMIT,
    SqliteControllerStore,
)

WORKER = Path(__file__).resolve().parent / "_crash_worker.py"
PROBE = Path(__file__).resolve().parent / "_recovery_probe.py"

CRASH_EXIT_CODES = {
    "pre-commit": 41,
    "post-commit": 42,
}


def _run_probe(database: Path) -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, str(PROBE), str(database)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError("recovery probe failed")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict):
        raise AssertionError("recovery probe returned invalid audit")
    return cast(dict[str, object], payload)


def _assert_crash_worker_exited_at_boundary(
    proc: subprocess.CompletedProcess[str],
    expected_exit_code: int,
) -> None:
    """Check the bounded crash signal without rendering child-process output."""
    if proc.returncode != expected_exit_code:
        raise AssertionError(
            "crash worker did not exit at the expected durable boundary"
        )


def _assert_safe_diagnostic(rendered: str, expected: str, canary: str) -> None:
    """Verify diagnostic redaction without echoing the canary on regression."""
    if (
        rendered != expected
        or canary in rendered
        or chr(10) in rendered
        or chr(7) in rendered
    ):
        raise AssertionError("unsafe crash-recovery diagnostic")


def test_recovery_probe_failure_does_not_render_subprocess_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AC-09 negative: probe output cannot escape through a failed assertion."""
    canary = "canary-probe-output" + chr(10) + "with-control" + chr(7)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout=canary, stderr=canary
        )

    monkeypatch.setattr(
        subprocess,
        "run",
        fake_run,
    )

    with pytest.raises(AssertionError) as raised:
        _run_probe(tmp_path / "probe.db")

    _assert_safe_diagnostic(str(raised.value), "recovery probe failed", canary)


def test_crash_worker_failure_does_not_render_subprocess_output() -> None:
    """AC-05 negative: crash-worker output remains outside diagnostics."""
    canary = "canary-worker-output" + chr(10) + "with-control" + chr(7)
    proc = subprocess.CompletedProcess(
        args=[], returncode=1, stdout=canary, stderr=canary
    )

    with pytest.raises(AssertionError) as raised:
        _assert_crash_worker_exited_at_boundary(proc, CRASH_EXIT_CODES["post-commit"])

    _assert_safe_diagnostic(
        str(raised.value),
        "crash worker did not exit at the expected durable boundary",
        canary,
    )


@pytest.mark.parametrize("crash_point", ["pre-commit", "post-commit"])
def test_real_subprocess_crash_at_durable_boundary(
    tmp_path: Path,
    crash_point: str,
    frozen_clock: Callable[[], datetime],
) -> None:
    """AC-05: crash at each durable boundary, then fresh-process restart."""
    database = tmp_path / f"crash-{crash_point}.db"
    command_id = f"cmd_crash_{'pre' if crash_point == 'pre-commit' else 'post'}"

    proc = subprocess.run(
        [sys.executable, str(WORKER), str(database), crash_point, command_id],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    _assert_crash_worker_exited_at_boundary(proc, CRASH_EXIT_CODES[crash_point])

    # Fresh process restarts from the same database and WAL.
    audit = _run_probe(database)
    assert audit["chain_ok"] is True
    if crash_point == "pre-commit":
        assert audit["inbox"] == 0
        assert audit["events"] == 0
        assert audit["outbox"] == 0
        assert audit["receipts"] == 0
        assert audit["projection_value"] == 0
        assert audit["projection_revision"] == 0
    else:
        assert audit["inbox"] == 1
        assert audit["events"] == 1
        assert audit["outbox"] == 1
        assert audit["receipts"] == 1
        assert audit["projection_value"] == 1
        assert audit["projection_revision"] == 1

        # Re-drive the acknowledged command path once: the same command must
        # return the original receipt and append no second Event.
        store = SqliteControllerStore(database)
        controller = SpikeController(store, frozen_clock, lambda: "evt_replay")
        receipt = controller.submit(make_spike_command(command_id))
        assert receipt.status == "ACCEPTED"
        assert receipt.observed_revision == 1
        audit_after = store.audit()
        assert audit_after.event_count == 1
        assert audit_after.receipt_count == 1
        store.close()


def test_exception_injection_is_not_presented_as_crash_evidence(
    tmp_path: Path,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
) -> None:
    """AC-05 negative: AC-03 in-transaction exception injection is
    transaction-failure evidence, never process-crash evidence. After an
    injected fault the same process keeps running and the store stays
    usable; crash evidence requires a real subprocess exit code."""
    database = tmp_path / "inject-not-crash.db"
    failing = SqliteControllerStore(
        database, fault_spec=FaultSpec(before=frozenset({1}))
    )
    controller = SpikeController(failing, frozen_clock, event_id_sequence)
    receipt = controller.submit(make_spike_command("cmd_inject_only"))
    assert receipt.status == "REJECTED"
    # The same process continues: the store is still fully usable.
    assert failing.audit().event_count == 0
    failing.close()
    # Crash evidence is bound to the actual Adapter's subprocess exit codes.
    assert CRASH_EXIT_PRE_COMMIT == 41
    assert CRASH_EXIT_POST_COMMIT == 42


def test_crash_worker_uses_real_process_exit_only() -> None:
    """AC-05 structural guard: the worker drives the actual Controller and
    Adapter, whose source owns the real process exits.  A duplicate raw
    sqlite transaction is not admissible crash evidence."""
    worker_source = WORKER.read_text(encoding="utf-8")
    adapter_text = inspect.getsource(SqliteControllerStore)
    assert "SpikeController" in worker_source
    assert "SqliteControllerStore" in worker_source
    assert "sqlite3.connect" not in worker_source
    assert "os._exit(CRASH_EXIT_PRE_COMMIT)" in adapter_text
    assert "os._exit(CRASH_EXIT_POST_COMMIT)" in adapter_text


def test_no_acknowledged_command_is_lost_after_post_commit_crash(
    tmp_path: Path,
    frozen_clock: Callable[[], datetime],
) -> None:
    """AC-05: after the post-commit crash, the acknowledged command's five
    records are all durable and the chain verifies in a fresh process."""
    database = tmp_path / "crash-lost.db"
    command_id = "cmd_crash_lost"
    proc = subprocess.run(
        [sys.executable, str(WORKER), str(database), "post-commit", command_id],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    _assert_crash_worker_exited_at_boundary(proc, CRASH_EXIT_CODES["post-commit"])
    audit = _run_probe(database)
    assert audit["events"] == 1
    assert audit["receipts"] == 1
    assert audit["inbox"] == 1
    assert audit["outbox"] == 1
    assert audit["chain_ok"] is True
