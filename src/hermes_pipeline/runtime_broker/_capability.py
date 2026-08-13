"""Four-state CapabilityProfile field matrix (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

Verdict = Literal["ENFORCED", "OBSERVED_ONLY", "UNSUPPORTED_RUNTIME", "NOT_APPLICABLE"]
PLATFORM = "windows" if sys.platform == "win32" else "linux"

CAPABILITY_FIELDS = (
    "filesystem.read_roots",
    "filesystem.write_roots",
    "filesystem.path_escape",
    "executables.allowlist",
    "executables.no_shell_strings",
    "network.loopback",
    "network.egress",
    "secrets.environment_allow_list",
    "secrets.canary",
    "browser.isolated_profile",
    "browser.mcp_tool_allow",
    "browser.cleanup",
    "resources.timeout",
    "resources.output_cap",
    "resources.cancel",
    "resources.process_tree",
    "side_effects.git",
    "side_effects.ports",
    "side_effects.child_processes",
    "side_effects.external_writes",
)


@dataclass(frozen=True)
class FieldVerdict:
    """Dated four-state verdict for one CapabilityProfile field."""

    field: str
    platform: str
    verdict: Verdict
    observed_at_utc: str
    note: str


def _now() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def classify_network_deny(*, os_egress_block: bool, privileged: bool) -> Verdict:
    """--offline is never OS egress evidence."""
    if os_egress_block and privileged:
        return "ENFORCED"
    return "UNSUPPORTED_RUNTIME"


def classify_filesystem(*, lower_privilege_or_sandbox: bool) -> Verdict:
    """Same-user ACL is observed only."""
    if lower_privilege_or_sandbox:
        return "ENFORCED"
    return "OBSERVED_ONLY"


def record_matrix(
    *,
    os_egress_block: bool = False,
    privileged: bool = False,
    lower_privilege_or_sandbox: bool = False,
) -> tuple[FieldVerdict, ...]:
    """Record the four-state matrix for the current platform."""
    observed = _now()
    network = classify_network_deny(
        os_egress_block=os_egress_block, privileged=privileged
    )
    filesystem = classify_filesystem(
        lower_privilege_or_sandbox=lower_privilege_or_sandbox
    )
    notes = {
        "filesystem.read_roots": "same-user ACL cannot block the owner's agent",
        "filesystem.write_roots": "same-user ACL cannot block the owner's agent",
        "filesystem.path_escape": "dot-dot/absolute/symlink/junction rejected in argv",
        "executables.allowlist": "argument-array only; no shell strings",
        "executables.no_shell_strings": "argument-array only; no shell strings",
        "network.loopback": "loopback mock-provider is not OS egress proof",
        "network.egress": "hard deny requires OS-level egress block",
        "secrets.environment_allow_list": "canaries stripped before child env",
        "secrets.canary": "Hermes-side redaction; vendor sanitizers unused",
        "browser.isolated_profile": "--isolated is MCP temp profile, not OS isolation",
        "browser.mcp_tool_allow": "closed MCP argv; rejected overrides",
        "browser.cleanup": "temporary MCP profile cleaned on close",
        "resources.timeout": "external wall-clock deadline",
        "resources.output_cap": "Hermes byte cap",
        "resources.cancel": "external cancellation token",
        "resources.process_tree": "Job Object / process group plus zero-survivor scan",
        "side_effects.git": "no-.git snapshot; Host has no Git authority",
        "side_effects.ports": "Host-reserved loopback only",
        "side_effects.child_processes": "fenced tree; zero survivors",
        "side_effects.external_writes": "state-root only",
    }
    rows: list[FieldVerdict] = []
    for field in CAPABILITY_FIELDS:
        if field.startswith("filesystem."):
            verdict: Verdict = filesystem
        elif field == "network.egress":
            verdict = network
        else:
            verdict = "OBSERVED_ONLY"
        rows.append(
            FieldVerdict(
                field=field,
                platform=PLATFORM,
                verdict=verdict,
                observed_at_utc=observed,
                note=notes[field],
            )
        )
    return tuple(rows)


def e2e_browser_composition(matrix: tuple[FieldVerdict, ...]) -> bool:
    """True when the composed e2e-browser profile does not re-widen."""
    by_field = {row.field: row.verdict for row in matrix}
    if by_field.get("network.egress") == "ENFORCED":
        return False
    if by_field.get("executables.no_shell_strings") == "ENFORCED":
        return True
    return by_field.get("network.egress") == "UNSUPPORTED_RUNTIME"
