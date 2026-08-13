"""Fake controlled E2E composition and labels (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_pipeline.runtime_broker._capability import (
    e2e_browser_composition,
    record_matrix,
)
from hermes_pipeline.runtime_broker._identity import load_tool_lock, mcp_argv

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

E2E_LABEL = "not an OS-level egress-block proof"


def test_loopback_e2e_is_labeled_not_os_egress_proof() -> None:
    assert E2E_LABEL in ("not an OS-level egress-block proof")
    lock = load_tool_lock(TOOL_LOCK)
    argv = mcp_argv(lock, Path("state"), 18080)
    assert any("127.0.0.1" in item for item in argv)
    assert e2e_browser_composition(record_matrix()) is True


def test_tools_list_is_never_e2e_evidence() -> None:
    wiring = lock_text()
    assert "tools/list success is never EC-00-09 evidence" in wiring


def lock_text() -> str:
    return TOOL_LOCK.read_text(encoding="utf-8")
