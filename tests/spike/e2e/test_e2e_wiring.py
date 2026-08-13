"""Locked E2E fixture/provider/config/oracle (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_pipeline.runtime_broker._e2e import (
    E2E_OK,
    FIXTURE_BODY,
    MockChatProvider,
    e2e_success,
    fixture_response,
    mcp_config,
    write_opencode_config,
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


def test_fixture_page_body_and_404() -> None:
    status, ctype, body = fixture_response("/page")
    assert status == 200
    assert ctype == "text/html"
    assert body == FIXTURE_BODY
    assert fixture_response("/other")[0] == 404


def test_mock_provider_three_calls_then_409() -> None:
    provider = MockChatProvider(18080)
    first = json.loads(provider.handle("POST", "/v1/chat/completions", b"{}")[2])
    second = json.loads(provider.handle("POST", "/v1/chat/completions", b"{}")[2])
    third = json.loads(provider.handle("POST", "/v1/chat/completions", b"{}")[2])
    assert first["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == (
        "chrome-devtools_navigate_page"
    )
    assert second["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == (
        "chrome-devtools_evaluate_script"
    )
    assert third["choices"][0]["message"]["content"] == E2E_OK
    assert provider.handle("POST", "/v1/chat/completions", b"{}")[0] == 409
    assert provider.handle("GET", "/v1/chat/completions", b"")[0] == 409


def test_opencode_config_stays_outside_snapshot(tmp_path: Path) -> None:
    lock = load_tool_lock(TOOL_LOCK)
    argv = mcp_argv(lock, tmp_path, 18080)
    mcp = mcp_config(argv, {"CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS": "1"})
    path = write_opencode_config(tmp_path, provider_port=18081, mcp=mcp)
    assert path.is_relative_to(tmp_path / "tools")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["permission"]["*"] == "deny"
    assert payload["mcp"]["chrome-devtools"] == mcp
    assert "snapshot" not in str(path)


def test_tools_list_is_not_success_oracle() -> None:
    assert e2e_success("tools/list ok", 1) is False
    weak = E2E_OK + " chrome-devtools_navigate_page"
    assert e2e_success(weak, 3) is False
    good = (
        "chrome-devtools_navigate_page http://127.0.0.1:18080/page "
        "chrome-devtools_evaluate_script "
        "{title:'Hermes E2E Fixture',proof:'hermes-00-06',"
        "text:'Hermes browser proof'} " + E2E_OK
    )
    assert e2e_success(good, 3) is True
