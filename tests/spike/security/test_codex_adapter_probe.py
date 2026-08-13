"""Fake Codex Adapter probe (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import pytest

from hermes_pipeline.runtime_broker._codex import (
    classify_codex_jsonl,
    sanctioned_codex_argv,
)
from hermes_pipeline.runtime_broker._identity import assert_no_dangerous_codex_flags

pytestmark = pytest.mark.fake_only


def test_classifies_jsonl_success_and_last_message() -> None:
    stream = "\n".join(
        [
            '{"type":"thread.started"}',
            '{"type":"item.completed","item":{"type":"message","content":[{"type":"output_text","text":"HERMES_CODEX_PROBE_OK"}]}}',
            '{"type":"turn.completed","status":"completed"}',
        ]
    )
    result = classify_codex_jsonl(stream)
    assert result.outcome == "ok"
    assert result.final_text == "HERMES_CODEX_PROBE_OK"


def test_classifies_no_credential_failure() -> None:
    stream = '{"type":"error","error":{"message":"missing credentials"}}'
    result = classify_codex_jsonl(stream)
    assert result.outcome == "no_credential"


def test_sanctioned_argv_omits_dangerous_bypass_flags() -> None:
    argv = sanctioned_codex_argv("codex", "/snapshot", "ping")
    assert "--json" in argv
    assert "--sandbox" in argv
    assert_no_dangerous_codex_flags(argv)
    with pytest.raises(ValueError):
        assert_no_dangerous_codex_flags(
            [*argv, "--dangerously-bypass-approvals-and-sandbox"]
        )
