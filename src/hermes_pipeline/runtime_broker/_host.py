"""Shared Host CLI for tools_bootstrap and controlled_e2e.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from hermes_pipeline.runtime_broker._auth import (
    AuthorizationError,
    HostInputs,
    parse_host_argv,
    validate_authorization,
)
from hermes_pipeline.runtime_broker._codes import UNSUPPORTED_RUNTIME
from hermes_pipeline.runtime_broker._e2e import (
    run_codex_probe_after_isolation,
    run_e2e_after_isolation,
    run_opencode_probe_after_isolation,
)
from hermes_pipeline.runtime_broker._identity import (
    load_tool_lock,
    mcp_argv,
    windows_codex_unsupported,
)
from hermes_pipeline.runtime_broker._isolation import (
    IsolationError,
    prove_host_isolation,
)
from hermes_pipeline.runtime_broker._observations import envelope, write_observations
from hermes_pipeline.runtime_broker._provision import (
    load_and_materialize,
    run_npm,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def emit(payload: dict[str, Any], *, exit_code: int) -> int:
    """Write one JSON object to stdout and return the process exit code."""
    sys.stdout.write(json.dumps(payload, separators=(",", ":")))
    sys.stdout.write("\n")
    return exit_code


def reject(code: str) -> int:
    """Fail closed with the locked rejection envelope."""
    return emit({"ok": False, "code": code}, exit_code=1)


def _authorized(argv: list[str]) -> tuple[str, dict[str, Any]] | int:
    try:
        mode, inputs = parse_host_argv(argv)
        validated = validate_authorization(inputs)
        prove_host_isolation(
            state_root=inputs.state_root, snapshot=validated["snapshot"]
        )
    except AuthorizationError as exc:
        return reject(exc.code)
    except IsolationError as exc:
        return reject(exc.code)
    validated["mode"] = mode
    validated["inputs"] = inputs
    return mode, validated


def _record_observations(
    inputs: HostInputs,
    validated: dict[str, Any],
    *,
    asset: dict[str, str],
    version: dict[str, str],
    probe: dict[str, str],
    isolation: dict[str, str],
) -> None:
    write_observations(
        inputs.state_root,
        tool_record_digest=str(validated["tool_record_digest"]),
        run_binding_digest=str(validated["run_binding_digest"]),
        asset=asset,
        version=version,
        probe=probe,
        isolation=isolation,
    )


def run_bootstrap(argv: list[str]) -> int:
    """Host entry for tools_bootstrap.py."""
    authorized = _authorized(argv)
    if isinstance(authorized, int):
        return authorized
    mode, validated = authorized
    inputs = validated["inputs"]
    lock = load_tool_lock(inputs.tool_lock)
    if mode == "probe-codex" and windows_codex_unsupported(lock):
        return reject(UNSUPPORTED_RUNTIME)
    isolation = envelope(
        "ok",
        "ENFORCED",
        "identity, filesystem, and egress assertions demonstrated",
    )
    if mode == "selfcheck":
        load_and_materialize(inputs.tool_lock, REPO_ROOT, inputs.state_root)
        mcp_argv(lock, inputs.state_root, 18080)
        _record_observations(
            inputs,
            validated,
            asset=envelope("ok", "VERIFIED", "static identities"),
            version=envelope("ok", "VERSION", "identity-only"),
            probe=envelope("ok", "PROBED", "selfcheck"),
            isolation=isolation,
        )
        return emit({"ok": True, "mode": "selfcheck"}, exit_code=0)
    if mode == "verify":
        load_and_materialize(inputs.tool_lock, REPO_ROOT, inputs.state_root)
        run_npm(lock, inputs.state_root, offline=True)
        _record_observations(
            inputs,
            validated,
            asset=envelope("ok", "VERIFIED", "offline npm"),
            version=envelope("ok", "VERSION", "cutoff"),
            probe=envelope("ok", "PROBED", "verify"),
            isolation=isolation,
        )
        return emit({"ok": True, "mode": "verify"}, exit_code=0)
    if mode == "probe-opencode":
        load_and_materialize(inputs.tool_lock, REPO_ROOT, inputs.state_root)
        probed = run_opencode_probe_after_isolation(
            lock, inputs.state_root, validated["snapshot"]
        )
        _record_observations(
            inputs,
            validated,
            asset=envelope("ok", "VERIFIED", "opencode identity"),
            version=envelope("ok", "VERSION", str(probed.get("final_text", ""))),
            probe=envelope("ok", "PROBED", str(probed.get("outcome", ""))),
            isolation=isolation,
        )
        return emit({"ok": True, "mode": "probe-opencode"}, exit_code=0)
    if mode == "probe-codex":
        load_and_materialize(inputs.tool_lock, REPO_ROOT, inputs.state_root)
        probed = run_codex_probe_after_isolation(
            lock, inputs.state_root, validated["snapshot"]
        )
        _record_observations(
            inputs,
            validated,
            asset=envelope("ok", "VERIFIED", "codex identity"),
            version=envelope("ok", "VERSION", str(probed.get("final_text", ""))),
            probe=envelope("ok", "PROBED", str(probed.get("outcome", ""))),
            isolation=isolation,
        )
        return emit({"ok": True, "mode": "probe-codex"}, exit_code=0)
    load_and_materialize(inputs.tool_lock, REPO_ROOT, inputs.state_root)
    run_npm(lock, inputs.state_root, offline=False)
    _record_observations(
        inputs,
        validated,
        asset=envelope("ok", "VERIFIED", "online npm"),
        version=envelope("ok", "VERSION", "bootstrap"),
        probe=envelope("ok", "PROBED", "bootstrap"),
        isolation=isolation,
    )
    return emit({"ok": True, "mode": "bootstrap"}, exit_code=0)


def run_controlled_e2e(argv: list[str]) -> int:
    """Host entry for controlled_e2e.py."""
    authorized = _authorized(argv)
    if isinstance(authorized, int):
        return authorized
    mode, validated = authorized
    inputs = validated["inputs"]
    lock = load_and_materialize(inputs.tool_lock, REPO_ROOT, inputs.state_root)
    session = run_e2e_after_isolation(lock, inputs.state_root, validated["snapshot"])
    _record_observations(
        inputs,
        validated,
        asset=envelope("ok", "VERIFIED", "e2e identities"),
        version=envelope("ok", "VERSION", "e2e"),
        probe=envelope(
            "ok" if session["ok"] else "failed",
            "PROBED",
            f"calls={session['calls']}",
        ),
        isolation=envelope(
            "ok",
            "ENFORCED",
            "identity, filesystem, and egress assertions demonstrated",
        ),
    )
    if not session["ok"]:
        return reject("DEPENDENCY_UNAVAILABLE")
    return emit({"ok": True, "mode": mode or "controlled-e2e"}, exit_code=0)
