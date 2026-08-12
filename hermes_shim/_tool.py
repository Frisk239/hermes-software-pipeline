"""Declared high-level tool for the Hermes Shim (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

One minimal declared high-level tool (``pipeline_health``) proves the
``ctx.register_tool`` surface; the PluginManager probe asserts exactly one
registered tool. The handler is stdlib-only, offline, deterministic, and
never touches the managed runtime.
"""

from __future__ import annotations

import json
from typing import Any

TOOL_NAME = "pipeline_health"
TOOLSET = "hermes_pipeline"
TOOL_DESCRIPTION = (
    "Report the Hermes Software Pipeline shim health (spike tool; "
    "never reaches the managed runtime)."
)

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def pipeline_health_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """One deterministic, bounded health string (no paths or env values)."""
    del args, kwargs
    return json.dumps(
        {"ok": True, "tool": TOOL_NAME, "spike": "slice-00-05"},
        sort_keys=True,
        separators=(",", ":"),
    )


def register(ctx: object) -> None:
    """Register the tool on a Hermes PluginContext."""
    ctx.register_tool(
        name=TOOL_NAME,
        toolset=TOOLSET,
        schema=TOOL_SCHEMA,
        handler=pipeline_health_handler,
        description=TOOL_DESCRIPTION,
    )


__all__ = ["pipeline_health_handler", "register"]
