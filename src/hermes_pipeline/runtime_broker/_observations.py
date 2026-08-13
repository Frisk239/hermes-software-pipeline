"""Post-execution tool-observations.json writer.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hermes_pipeline.runtime_broker._redaction import bound_text


def envelope(status: str, code: str, text: str) -> dict[str, str]:
    """Typed result envelope from the tool lock."""
    return {"status": status, "code": code, "bounded_text": bound_text(text)}


def write_observations(
    state_root: Path,
    *,
    tool_record_digest: str,
    run_binding_digest: str,
    asset: dict[str, str],
    version: dict[str, str],
    probe: dict[str, str],
    isolation: dict[str, str],
    clock: datetime | None = None,
) -> Path:
    """Write <state-root>/tools/tool-observations.json after execution."""
    observed = clock or datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "tool_record_digest": tool_record_digest,
        "run_binding_digest": run_binding_digest,
        "asset_verification_result": asset,
        "version_output": version,
        "capability_probe_result": probe,
        "isolation_proof_result": isolation,
        "observed_at_utc": observed.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }
    target = state_root / "tools" / "tool-observations.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target
