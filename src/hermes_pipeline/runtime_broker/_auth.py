"""Custodian authorization validation for the Sandbox Host.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from hermes_pipeline.runtime_broker._acl import protect_owner_only, verify_owner_only
from hermes_pipeline.runtime_broker._codes import DEPENDENCY_UNAVAILABLE
from hermes_pipeline.runtime_broker._digest import (
    digest_hex,
    file_digest,
    object_digest,
)
from hermes_pipeline.runtime_broker._snapshot import snapshot_tree_digest

RECORD_FIELDS = (
    "schema_version",
    "planning_base_sha",
    "candidate_sha",
    "candidate_tree_digest",
    "integration_base_sha",
    "integration_candidate_sha",
    "integration_candidate_tree_digest",
    "source_tree_digest",
    "tool_lock_digest",
    "selected_platform",
    "selected_tool_lock_entries",
    "custodian_origin",
)
BINDING_FIELDS = (
    "schema_version",
    "planning_base_sha",
    "candidate_sha",
    "candidate_tree_digest",
    "integration_base_sha",
    "integration_candidate_sha",
    "integration_candidate_tree_digest",
    "source_tree_digest",
    "tool_lock_digest",
    "tool_record_digest",
    "custodian_origin",
    "run_id",
    "issued_at_utc",
    "expires_at_utc",
    "single_use_nonce",
)
GATE_FIELDS = ("schema_version", "run_binding_digest")
FORBIDDEN_RECORD_FIELDS = (
    "version_output",
    "capability_probe_result",
    "observed_at_utc",
    "asset_verification_result",
    "run_binding_digest",
)
ENTRY_FIELDS = ("tool", "platform", "asset", "integrity")
CUSTODIAN_ORIGIN = "git-custodian"
REQUIRED_FLAGS = (
    "--state-root",
    "--candidate-sha",
    "--source-tree-digest",
    "--tool-lock",
    "--tool-record",
    "--host-gate",
    "--run-binding",
)


class AuthorizationError(ValueError):
    """Missing or invalid Custodian authorization."""

    def __init__(self, code: str = DEPENDENCY_UNAVAILABLE) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class HostInputs:
    """The seven mandatory Host CLI inputs."""

    state_root: Path
    candidate_sha: str
    source_tree_digest: str
    tool_lock: Path
    tool_record: Path
    host_gate: Path
    run_binding: Path


def parse_host_argv(argv: list[str]) -> tuple[str, HostInputs]:
    """Parse optional subcommand plus the seven required flags."""
    rest = list(argv)
    mode = "bootstrap"
    known = {
        "verify",
        "selfcheck",
        "probe-codex",
        "probe-opencode",
        "bootstrap",
    }
    if rest and not rest[0].startswith("-") and rest[0] in known:
        mode = rest.pop(0)
    values: dict[str, str] = {}
    index = 0
    while index < len(rest):
        token = rest[index]
        if token in REQUIRED_FLAGS and index + 1 < len(rest):
            if token in values:
                raise AuthorizationError
            values[token] = rest[index + 1]
            index += 2
            continue
        raise AuthorizationError
    missing = [flag for flag in REQUIRED_FLAGS if flag not in values]
    if missing:
        raise AuthorizationError
    return mode, HostInputs(
        state_root=Path(values["--state-root"]),
        candidate_sha=values["--candidate-sha"],
        source_tree_digest=values["--source-tree-digest"],
        tool_lock=Path(values["--tool-lock"]),
        tool_record=Path(values["--tool-record"]),
        host_gate=Path(values["--host-gate"]),
        run_binding=Path(values["--run-binding"]),
    )


def _load_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AuthorizationError
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorizationError from exc
    if not isinstance(loaded, dict):
        raise AuthorizationError
    return cast(dict[str, Any], loaded)


def _require_exact_keys(payload: dict[str, Any], fields: tuple[str, ...]) -> None:
    if set(payload) != set(fields):
        raise AuthorizationError
    if payload.get("schema_version") != 1:
        raise AuthorizationError


def _require_origin(payload: dict[str, Any]) -> None:
    if payload.get("custodian_origin") != CUSTODIAN_ORIGIN:
        raise AuthorizationError


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise AuthorizationError
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AuthorizationError from exc
    if parsed.tzinfo is None:
        raise AuthorizationError
    return parsed.astimezone(UTC)


def snapshot_path(tool_record: Path) -> Path:
    """dirname(abspath(--tool-record))/integration-candidate-snapshot/."""
    return tool_record.resolve().parent / "integration-candidate-snapshot"


def inspect_snapshot(path: Path, expected_digest: str) -> str:
    """Hash the snapshot tree and require a byte-identical binding digest."""
    if not path.is_dir():
        raise AuthorizationError
    if (path / ".git").exists():
        raise AuthorizationError
    if not expected_digest:
        raise AuthorizationError
    digest = snapshot_tree_digest(path)
    if digest != expected_digest:
        raise AuthorizationError
    return digest


def consume_host_gate(state_root: Path, run_binding_digest: str) -> None:
    """Atomically record a single-use gate; replay fails closed."""
    store = state_root / "tools" / "used-host-gates"
    store.mkdir(parents=True, exist_ok=True)
    marker = store / digest_hex(run_binding_digest)
    try:
        handle = marker.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise AuthorizationError from exc
    with handle:
        handle.write(run_binding_digest)
        handle.write("\n")
    protect_owner_only(marker)


def validate_authorization(
    inputs: HostInputs,
    *,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Validate the seven inputs and snapshot handoff. Never starts a child."""
    if not inputs.tool_lock.is_file():
        raise AuthorizationError
    record = _load_object(inputs.tool_record)
    binding = _load_object(inputs.run_binding)
    gate = _load_object(inputs.host_gate)
    for forbidden in FORBIDDEN_RECORD_FIELDS:
        if forbidden in record:
            raise AuthorizationError
    _require_exact_keys(record, RECORD_FIELDS)
    _require_exact_keys(binding, BINDING_FIELDS)
    _require_exact_keys(gate, GATE_FIELDS)
    _require_origin(record)
    _require_origin(binding)
    entries = record["selected_tool_lock_entries"]
    if not isinstance(entries, list):
        raise AuthorizationError
    for raw_entry in cast(list[object], entries):
        if not isinstance(raw_entry, dict):
            raise AuthorizationError
        entry = cast(dict[str, Any], raw_entry)
        if set(entry) != set(ENTRY_FIELDS):
            raise AuthorizationError
    lock_bytes = inputs.tool_lock.read_bytes()
    lock_digest = file_digest(lock_bytes)
    if record["tool_lock_digest"] != lock_digest:
        raise AuthorizationError
    if binding["tool_lock_digest"] != lock_digest:
        raise AuthorizationError
    record_digest = object_digest(record)
    if binding["tool_record_digest"] != record_digest:
        raise AuthorizationError
    binding_digest = object_digest(binding)
    if gate["run_binding_digest"] != binding_digest:
        raise AuthorizationError
    shared_digest = record["source_tree_digest"]
    if shared_digest != binding["source_tree_digest"]:
        raise AuthorizationError
    if shared_digest != binding["integration_candidate_tree_digest"]:
        raise AuthorizationError
    if shared_digest != inputs.source_tree_digest:
        raise AuthorizationError
    if record["candidate_sha"] != inputs.candidate_sha:
        raise AuthorizationError
    if binding["candidate_sha"] != inputs.candidate_sha:
        raise AuthorizationError
    now = (clock or (lambda: datetime.now(tz=UTC)))()
    issued = _parse_utc(binding["issued_at_utc"])
    expires = _parse_utc(binding["expires_at_utc"])
    if now < issued or now >= expires:
        raise AuthorizationError
    try:
        verify_owner_only(inputs.host_gate)
    except OSError as exc:
        raise AuthorizationError from exc
    discovered = snapshot_path(inputs.tool_record)
    inspect_snapshot(discovered, shared_digest)
    consume_host_gate(inputs.state_root, binding_digest)
    return {
        "record": record,
        "binding": binding,
        "gate": gate,
        "tool_record_digest": record_digest,
        "run_binding_digest": binding_digest,
        "snapshot": discovered,
    }
