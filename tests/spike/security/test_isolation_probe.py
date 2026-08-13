"""Isolation child-probe oracle (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_pipeline.runtime_broker._isolation import (
    IsolationError,
    evaluate_child_probe_report,
    prove_host_isolation,
)

pytestmark = pytest.mark.fake_only


def test_child_report_requires_every_locked_assertion() -> None:
    good = {
        "appcontainer": True,
        "outside_read": "access_denied",
        "outside_write": "access_denied",
        "snapshot_write": "access_denied",
        "state_write": "ok",
        "egress": "failed",
        "uid": 1,
    }
    assert evaluate_child_probe_report(good, windows=True) is True
    bad = dict(good)
    bad["appcontainer"] = False
    assert evaluate_child_probe_report(bad, windows=True) is False
    hostish = {
        "appcontainer": False,
        "outside_read": "ok",
        "outside_write": "ok",
        "snapshot_write": "ok",
        "state_write": "ok",
        "egress": "failed",
        "uid": 0,
    }
    assert evaluate_child_probe_report(hostish, windows=False) is False


def test_windows_child_probe_is_not_a_stub() -> None:
    source = (
        Path(__file__)
        .resolve()
        .parents[3]
        .joinpath("src/hermes_pipeline/runtime_broker/_isolation.py")
        .read_text(encoding="utf-8")
    )
    assert "CreateAppContainerProfile" in source
    assert "_run_appcontainer_process" in source
    assert "return False\n    del state_root" not in source


def test_prove_host_isolation_still_fail_closes_without_child_proof(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "snap"
    snapshot.mkdir()
    with pytest.raises(IsolationError):
        prove_host_isolation(state_root=tmp_path / "state", snapshot=snapshot)
