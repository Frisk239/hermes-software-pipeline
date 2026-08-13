"""Typed OpenCode Adapter probe (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, cast

OpenCodeOutcome = Literal["idle", "error", "denied", "timeout", "cancelled"]


@dataclass(frozen=True)
class OpenCodeProbeResult:
    """Classification of an OpenCode --format json event stream."""

    outcome: OpenCodeOutcome
    final_text: str
    events: tuple[dict[str, Any], ...]


def merge_permission_policy(
    injected: dict[str, str], hostile: dict[str, str]
) -> dict[str, str]:
    """Explicit denies win over a hostile repository opencode.json."""
    merged = dict(hostile)
    merged.update(injected)
    for key, value in injected.items():
        if value == "deny":
            merged[key] = "deny"
    return merged


def classify_opencode_events(text: str) -> OpenCodeProbeResult:
    """Classify from events, never from the process exit code."""
    events: list[dict[str, Any]] = []
    final = ""
    outcome: OpenCodeOutcome = "error"
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
        kind = str(typed.get("type") or "")
        if kind == "session.status" and typed.get("status") == "idle":
            outcome = "idle"
        if kind == "session.error":
            outcome = "error"
        if kind == "permission.denied":
            outcome = "denied"
        text_value = typed.get("text")
        if kind in {"text", "assistant"} and isinstance(text_value, str):
            final = text_value
        part = typed.get("part")
        if isinstance(part, dict):
            typed_part = cast(dict[str, Any], part)
            if typed_part.get("type") == "text":
                final = str(typed_part.get("text") or final)
    return OpenCodeProbeResult(outcome=outcome, final_text=final, events=tuple(events))
