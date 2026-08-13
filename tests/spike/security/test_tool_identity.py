"""Sealed browser and Agent-CLI identity checks (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from hermes_pipeline.runtime_broker._identity import (
    chrome_is_sealed,
    load_tool_lock,
    mcp_argv,
    npm_argv,
    verify_browser_inputs,
    windows_codex_unsupported,
)

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


def test_browser_inputs_match_committed_digests_name_pin_and_sri() -> None:
    lock = load_tool_lock(TOOL_LOCK)
    verify_browser_inputs(lock, REPO)
    assert chrome_is_sealed(lock) is False


def test_npm_argv_uses_locked_executable_not_path_npm(tmp_path: Path) -> None:
    lock = load_tool_lock(TOOL_LOCK)
    online = npm_argv(lock, tmp_path, offline=False)
    offline = npm_argv(lock, tmp_path, offline=True)
    assert online[1] == "ci"
    assert "--ignore-scripts" in online
    assert "--audit=false" in online
    assert "--offline" not in online
    assert "--offline" in offline
    assert "npm" not in Path(online[0]).name.lower() or str(tmp_path) in online[0]


def test_mcp_argv_is_closed_and_rejects_remote_attach(tmp_path: Path) -> None:
    lock = load_tool_lock(TOOL_LOCK)
    argv = mcp_argv(lock, tmp_path, 18765)
    assert "--headless" in argv
    assert "--isolated" in argv
    assert "--no-usage-statistics" in argv
    assert "--no-performance-crux" in argv
    assert any(item.startswith("http://127.0.0.1:18765/") for item in argv)
    assert "--browser-url" not in argv
    assert "--channel" not in argv


def test_windows_codex_is_unsupported_runtime_on_this_revision() -> None:
    lock = load_tool_lock(TOOL_LOCK)
    assert windows_codex_unsupported(lock) is (sys.platform == "win32")
