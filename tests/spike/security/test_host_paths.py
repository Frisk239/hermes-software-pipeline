"""Host success paths stay closed without isolation proof (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_pipeline.runtime_broker._host import run_bootstrap, run_controlled_e2e
from hermes_pipeline.runtime_broker._identity import load_tool_lock
from hermes_pipeline.runtime_broker._isolation import (
    IsolationError,
    prove_host_isolation,
)
from hermes_pipeline.runtime_broker._provision import materialize_browser_project

pytestmark = pytest.mark.fake_only

REPO = Path(__file__).resolve().parents[3]
TOOL_LOCK = (
    REPO
    / "docs"
    / "roadmap"
    / "phase-00-foundation"
    / "slices"
    / "00-06-agent-runtime-security-spikes"
    / "tool-lock.json"
)


def test_isolation_proof_fails_closed_on_this_host(tmp_path: Path) -> None:
    snapshot = tmp_path / "snap"
    snapshot.mkdir()
    parent_before = {path.name for path in tmp_path.iterdir()}
    with pytest.raises(IsolationError):
        prove_host_isolation(state_root=tmp_path / "state", snapshot=snapshot)
    parent_after = {path.name for path in tmp_path.iterdir()}
    assert "isolation-canary-outside" not in parent_after
    assert parent_after - parent_before <= {"state", "snap"}
    source = (
        REPO / "src" / "hermes_pipeline" / "runtime_broker" / "_isolation.py"
    ).read_text(encoding="utf-8")
    assert "1.1.1.1" not in source
    assert "isolation-canary-outside" not in source


def test_authorized_cli_does_not_emit_ok_without_isolation() -> None:
    code = run_bootstrap(
        [
            "selfcheck",
            "--state-root",
            "missing",
            "--candidate-sha",
            "c",
            "--source-tree-digest",
            "d",
            "--tool-lock",
            str(TOOL_LOCK),
            "--tool-record",
            "missing-record",
            "--host-gate",
            "missing-gate",
            "--run-binding",
            "missing-binding",
        ]
    )
    assert code == 1
    code = run_controlled_e2e(
        [
            "--state-root",
            "missing",
            "--candidate-sha",
            "c",
            "--source-tree-digest",
            "d",
            "--tool-lock",
            str(TOOL_LOCK),
            "--tool-record",
            "missing-record",
            "--host-gate",
            "missing-gate",
            "--run-binding",
            "missing-binding",
        ]
    )
    assert code == 1


def test_materialize_byte_copies_package_inputs(tmp_path: Path) -> None:
    lock = load_tool_lock(TOOL_LOCK)
    project = materialize_browser_project(lock, REPO, tmp_path)
    src = (
        REPO
        / "docs"
        / "roadmap"
        / "phase-00-foundation"
        / "slices"
        / "00-06-agent-runtime-security-spikes"
        / "package.json"
    )
    assert project.joinpath("package.json").read_bytes() == src.read_bytes()
    npmrc = tmp_path / "tools" / "browser-runtime" / "npmrc"
    assert npmrc.is_file()
    assert (
        json.loads(project.joinpath("package.json").read_text(encoding="utf-8"))["name"]
        == "hermes-browser-runtime"
    )
