"""Typed Codex Adapter probe (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, cast

CodexOutcome = Literal["ok", "no_credential", "error", "timeout", "cancelled"]


@dataclass(frozen=True)
class CodexProbeResult:
    """Classification of a Codex --json JSONL stream."""

    outcome: CodexOutcome
    final_text: str
    events: tuple[dict[str, Any], ...]


def sanctioned_codex_argv(executable: str, snapshot: str, prompt: str) -> list[str]:
    """Build the locked fake/real Codex argv without dangerous flags."""
    return [
        executable,
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "-C",
        snapshot,
        prompt,
    ]


def classify_codex_jsonl(text: str) -> CodexProbeResult:
    """Parse Codex --json JSONL and classify without using exit codes."""
    events: list[dict[str, Any]] = []
    final = ""
    outcome: CodexOutcome = "error"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        typed = cast(dict[str, Any], event)
        events.append(typed)
        kind = str(typed.get("type") or typed.get("item") or "")
        error_obj = typed.get("error")
        payload = cast(dict[str, Any], error_obj) if isinstance(error_obj, dict) else {}
        message = str(payload.get("message", typed.get("message", "")))
        if "auth" in message.lower() or "credential" in message.lower():
            outcome = "no_credential"
        text_value = typed.get("text")
        if isinstance(text_value, str) and text_value:
            final = text_value
        item = typed.get("item")
        if isinstance(item, dict):
            typed_item = cast(dict[str, Any], item)
            content = typed_item.get("content")
            if isinstance(content, list):
                for part in cast(list[object], content):
                    if isinstance(part, dict):
                        typed_part = cast(dict[str, Any], part)
                        if typed_part.get("type") == "output_text":
                            final = str(typed_part.get("text") or final)
        if outcome != "no_credential" and (
            kind.endswith("completed") or typed.get("status") == "completed"
        ):
            outcome = "ok"
    return CodexProbeResult(outcome=outcome, final_text=final, events=tuple(events))
