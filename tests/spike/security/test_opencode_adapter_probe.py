"""Fake OpenCode Adapter probe (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import pytest

from hermes_pipeline.runtime_broker._opencode import (
    classify_opencode_events,
    merge_permission_policy,
)

pytestmark = pytest.mark.fake_only


def test_classifies_idle_from_events_not_exit_code() -> None:
    stream = "\n".join(
        [
            '{"type":"text","text":"HERMES_OPENCODE_PROBE_OK"}',
            '{"type":"session.status","status":"idle"}',
        ]
    )
    result = classify_opencode_events(stream)
    assert result.outcome == "idle"
    assert result.final_text == "HERMES_OPENCODE_PROBE_OK"


def test_classifies_permission_denied() -> None:
    result = classify_opencode_events('{"type":"permission.denied","tool":"bash"}')
    assert result.outcome == "denied"


def test_injected_deny_wins_over_hostile_repository_config() -> None:
    merged = merge_permission_policy(
        {"*": "deny", "chrome-devtools_*": "allow"},
        {"*": "allow", "bash": "allow"},
    )
    assert merged["*"] == "deny"
    assert merged["chrome-devtools_*"] == "allow"
    assert merged.get("bash") == "allow"
