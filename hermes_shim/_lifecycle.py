"""Lifecycle logic for the Hermes Shim (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: ADOPTED_BY_00-07

Implements the idempotent ``hermes pipeline setup|doctor|start|status|stop``
semantics for the non-production skeleton. ``start`` bootstraps the managed
environment, launches the fake runtime as an independent interpreter with a
controlled argv array (never a shell string), waits for the atomically
written descriptor and readiness, and never rewrites the descriptor (token
rotation happens only when the runtime process starts). ``stop`` validates
the start identity, terminates the process, and removes the descriptor.
All results are bounded JSON with stable exit codes and never contain
tokens, paths, environment values, or raw exceptions.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import _client
from ._constants import (
    CODE_DEPENDENCY_UNAVAILABLE,
    PROTOCOL_VERSION,
)
from ._descriptor import (
    is_stale,
    read_descriptor,
    remove_descriptor,
    render_redacted_summary,
)
from ._provision import (
    ProvisionResult,
    interpreter_path,
    provision_runtime_env,
    runtime_environment_dir,
)
from ._state import (
    StateRootBoundaryError,
    ensure_inside_state_root,
    ensure_layout,
    ownership_marker_valid,
    state_root,
)

# Bounded start budget: stale-descriptor cleanup and runtime readiness must
# complete within 30 seconds of the start invocation.
START_BUDGET_SECONDS = 30

EXIT_OK = 0
EXIT_FAIL = 1


@dataclass
class LifecycleResult:
    """One bounded lifecycle command result."""

    command: str
    ok: bool = True
    exit_code: int = EXIT_OK
    checks: list[dict[str, str]] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    def as_json(self) -> str:
        """Compact, stable, bounded JSON (no paths, tokens, or env values)."""
        document: dict[str, Any] = {
            "command": self.command,
            "ok": self.ok,
            "exit_code": self.exit_code,
            "checks": self.checks,
        }
        if self.detail:
            document["detail"] = self.detail
        return json.dumps(document, sort_keys=True, separators=(",", ":"))


def _add_check(result: LifecycleResult, component: str, status: str, code: str) -> None:
    result.checks.append({"component": component, "status": status, "code": code})


def _runtime_entry_argv(root: Path) -> list[str]:
    """Controlled argv for the managed runtime entry."""
    environment_dir = runtime_environment_dir(root)
    interpreter = interpreter_path(environment_dir)
    return [
        str(interpreter),
        "-m",
        "hermes_pipeline.transport",
        "--state-root",
        str(root),
    ]


def setup_command(home: Path) -> LifecycleResult:
    """``hermes pipeline setup``: create the state-root layout idempotently."""
    result = LifecycleResult("setup")
    root = state_root(home)
    try:
        ensure_layout(root)
    except (OSError, StateRootBoundaryError):
        _add_check(result, "state-root", "error", "STATE_ROOT_CREATE_FAILED")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    valid = ownership_marker_valid(root)
    _add_check(
        result,
        "state-root",
        "ok" if valid else "error",
        "STATE_ROOT_OK" if valid else "STATE_ROOT_INVALID",
    )
    result.ok = valid
    result.exit_code = EXIT_OK if valid else EXIT_FAIL
    return result


def doctor_command(home: Path, plugin_dir: Path) -> LifecycleResult:
    """``hermes pipeline doctor``: report component health, never repair."""
    result = LifecycleResult("doctor")
    root = state_root(home)
    if ownership_marker_valid(root):
        _add_check(result, "state-root", "ok", "STATE_ROOT_OK")
    else:
        _add_check(result, "state-root", "error", "STATE_ROOT_INVALID")

    environment_dir = runtime_environment_dir(root)
    interpreter = interpreter_path(environment_dir)
    if interpreter.is_file():
        _add_check(result, "runtime-environment", "ok", "RUNTIME_ENV_OK")
    else:
        _add_check(result, "runtime-environment", "error", "RUNTIME_ENV_MISSING")

    document = read_descriptor(root)
    if document is None:
        _add_check(result, "descriptor", "error", "DESCRIPTOR_MISSING")
        _add_check(result, "protocol", "error", "PROTOCOL_UNKNOWN")
        _add_check(result, "runtime", "error", "RUNTIME_UNREACHABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    if is_stale(root):
        _add_check(result, "descriptor", "error", "DESCRIPTOR_STALE")
        _add_check(result, "protocol", "error", "PROTOCOL_UNKNOWN")
        _add_check(result, "runtime", "error", "RUNTIME_UNREACHABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    _add_check(result, "descriptor", "ok", "DESCRIPTOR_OK")
    if int(document["protocol_version"]) == PROTOCOL_VERSION:
        _add_check(result, "protocol", "ok", "PROTOCOL_OK")
    else:
        _add_check(result, "protocol", "error", "PROTOCOL_MISMATCH")
        result.ok = False
    try:
        probe = _client.readyz(int(document["port"]), str(document["token"]))
    except _client.RuntimeUnavailableError:
        probe = _client.ClientResult(ok=False, code=CODE_DEPENDENCY_UNAVAILABLE)
    if probe.ok:
        _add_check(result, "runtime", "ok", "RUNTIME_READY")
        result.detail = {"runtime": render_redacted_summary(document)}
    else:
        _add_check(result, "runtime", "error", "RUNTIME_UNREACHABLE")
        result.ok = False
    result.exit_code = EXIT_OK if result.ok else EXIT_FAIL
    return result


def start_command(
    home: Path,
    plugin_dir: Path,
    *,
    offline: bool = False,
    env_extra: dict[str, str] | None = None,
) -> LifecycleResult:
    """``hermes pipeline start``: provision, launch, wait for readiness.

    Idempotent: a live runtime already described converges to that runtime
    without launching a second process.
    """
    result = LifecycleResult("start")
    root = state_root(home)
    try:
        ensure_layout(root)
    except (OSError, StateRootBoundaryError):
        _add_check(result, "state-root", "error", "STATE_ROOT_CREATE_FAILED")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result

    document = read_descriptor(root)
    if document is not None and not is_stale(root):
        # Idempotent path: a live runtime already described converges to
        # that runtime, but only when it is actually ready — a process that
        # exists without serving must not be reported as running.
        if _wait_for_ready(root, budget_seconds=10):
            _add_check(result, "runtime", "ok", "RUNTIME_ALREADY_RUNNING")
            result.detail = {"runtime": render_redacted_summary(document)}
            return result
        _add_check(result, "runtime", "error", "RUNTIME_NOT_READY")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    if document is not None:
        # Stale descriptor: clean via the start-identity algorithm before
        # the new runtime starts.
        remove_descriptor(root)

    runtime_env_project = plugin_dir / "runtime-env"
    provisioned: ProvisionResult | None = None
    if interpreter_path(runtime_environment_dir(root)).is_file():
        provisioned = ProvisionResult(
            True,
            runtime_environment_dir(root),
            interpreter_path(runtime_environment_dir(root)),
        )
    else:
        provisioned = provision_runtime_env(
            runtime_env_project, root, offline=offline, env_extra=env_extra
        )
    if not provisioned.ok:
        _add_check(result, "runtime-environment", "error", "RUNTIME_ENV_MISSING")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    _add_check(result, "runtime-environment", "ok", "RUNTIME_ENV_OK")

    argv = _runtime_entry_argv(root)
    log_path = root / "logs" / "runtime.log"
    try:
        ensure_inside_state_root(root, log_path)
    except StateRootBoundaryError:
        _add_check(result, "runtime", "error", "RUNTIME_LOG_FAILED")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    try:
        log_file = log_path.open("ab")
    except OSError:
        _add_check(result, "runtime", "error", "RUNTIME_LOG_FAILED")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    env = _child_env_for_runtime(root, env_extra)
    try:
        subprocess.Popen(
            argv,
            cwd=str(plugin_dir),
            env=env,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            creationflags=_detached_flags(),
            start_new_session=os.name != "nt",
        )
    except OSError:
        log_file.close()
        _add_check(result, "runtime", "error", "RUNTIME_LAUNCH_FAILED")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result

    ready = _wait_for_ready(root, budget_seconds=START_BUDGET_SECONDS)
    if not ready:
        _add_check(result, "runtime", "error", "RUNTIME_NOT_READY")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    document = read_descriptor(root)
    if document is None:
        _add_check(result, "runtime", "error", "RUNTIME_NOT_READY")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    _add_check(result, "runtime", "ok", "RUNTIME_READY")
    result.detail = {"runtime": render_redacted_summary(document)}
    return result


def status_command(home: Path) -> LifecycleResult:
    """``hermes pipeline status``: descriptor and runtime health."""
    result = LifecycleResult("status")
    root = state_root(home)
    document = read_descriptor(root)
    if document is None:
        _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    if is_stale(root):
        _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    try:
        probe = _client.livez(int(document["port"]), str(document["token"]))
    except _client.RuntimeUnavailableError:
        probe = _client.ClientResult(ok=False, code=CODE_DEPENDENCY_UNAVAILABLE)
    if probe.ok:
        _add_check(result, "runtime", "ok", "RUNTIME_ALIVE")
        result.detail = {"runtime": render_redacted_summary(document)}
        return result
    _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
    result.ok = False
    result.exit_code = EXIT_FAIL
    return result


def stop_command(home: Path) -> LifecycleResult:
    """``hermes pipeline stop``: terminate and remove the descriptor.

    ``stop`` without a running runtime is a no-op with a stable exit code.
    The descriptor is removed only after the start-identity algorithm
    proves its process is gone.
    """
    result = LifecycleResult("stop")
    root = state_root(home)
    document = read_descriptor(root)
    if document is None:
        _add_check(result, "runtime", "ok", "RUNTIME_STOPPED")
        return result
    if is_stale(root):
        remove_descriptor(root)
        _add_check(result, "runtime", "ok", "RUNTIME_STOPPED")
        return result
    pid = int(document["pid"])
    # Termination is retried (bounded total budget ~8 s): on some hosts a
    # single TerminateProcess round may race the descriptor re-read, and
    # the Windows taskkill fallback covers restricted-host cases where the
    # direct kill is intercepted.
    import contextlib
    import subprocess as _subprocess

    for _attempt in range(4):
        with contextlib.suppress(OSError):
            os.kill(pid, _terminate_signal())
        if os.name == "nt":
            with contextlib.suppress(OSError, _subprocess.TimeoutExpired):
                _subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    timeout=5,
                )
        import time

        for _ in range(20):
            if is_stale(root):
                break
            time.sleep(0.1)
        if is_stale(root):
            break
    if is_stale(root):
        remove_descriptor(root)
        _add_check(result, "runtime", "ok", "RUNTIME_STOPPED")
        return result
    _add_check(result, "runtime", "error", "RUNTIME_STOP_FAILED")
    result.ok = False
    result.exit_code = EXIT_FAIL
    return result


def _child_env_for_runtime(
    root: Path, env_extra: dict[str, str] | None
) -> dict[str, str]:
    """Allow-list environment for the runtime child."""
    from ._provision import build_child_env

    return build_child_env(
        {"HERMES_PIPELINE_STATE_ROOT": str(root), **(env_extra or {})}
    )


def _detached_flags() -> int:
    if os.name == "nt":
        return subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    return 0


def _terminate_signal() -> int:
    import signal

    return signal.SIGTERM


def _wait_for_ready(root: Path, budget_seconds: int) -> bool:
    """Poll the descriptor and /readyz within the fixed start budget.

    Connection refusals during startup are retried (the runtime may not
    have bound its loopback socket yet).
    """
    import time

    deadline = time.monotonic() + budget_seconds
    while time.monotonic() < deadline:
        document = read_descriptor(root)
        if document is not None and not is_stale(root):
            try:
                probe = _client.readyz(int(document["port"]), str(document["token"]))
            except _client.RuntimeUnavailableError:
                time.sleep(0.25)
                continue
            if probe.ok:
                return True
        time.sleep(0.25)
    return False


def submit_requirement_command(
    home: Path,
    *,
    text: str,
    command_id: str,
    workspace_id: str,
    project_id: str,
    pipeline_id: str,
    principal_id: str,
) -> LifecycleResult:
    result = LifecycleResult(command="submit")
    root = state_root(home)
    document = read_descriptor(root)
    if document is None or is_stale(root):
        _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    try:
        reply = _client.submit_command(
            int(document["port"]),
            str(document["token"]),
            command_id,
            {
                "text": text,
                "workspace_id": workspace_id,
                "project_id": project_id,
                "pipeline_id": pipeline_id,
                "principal_id": principal_id,
            },
        )
    except _client.RuntimeUnavailableError:
        _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    result.ok = reply.ok
    result.exit_code = EXIT_OK if reply.ok else EXIT_FAIL
    result.detail = {"status": (reply.body or {}).get("status", reply.code or "")}
    if reply.body and "receipt" in reply.body:
        receipt = reply.body["receipt"]
        if isinstance(receipt, dict):
            result.detail = {"status": str(receipt.get("status", ""))}
    elif reply.body and "status" in reply.body:
        result.detail = {"status": str(reply.body.get("status", ""))}
    return result


def read_pipeline_command(
    home: Path, *, workspace_id: str, pipeline_id: str
) -> LifecycleResult:
    result = LifecycleResult(command="read")
    root = state_root(home)
    document = read_descriptor(root)
    if document is None or is_stale(root):
        _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    try:
        reply = _client.submit_command(
            int(document["port"]),
            str(document["token"]),
            "cmd_read_view",
            {
                "op": "read",
                "workspace_id": workspace_id,
                "pipeline_id": pipeline_id,
            },
        )
    except _client.RuntimeUnavailableError:
        _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    result.ok = reply.ok
    result.exit_code = EXIT_OK if reply.ok else EXIT_FAIL
    body = reply.body or {}
    view = body.get("receipt") if isinstance(body.get("receipt"), dict) else body
    result.detail = {
        "pipeline_id": str(view.get("pipeline_id", pipeline_id)),
        "status": str(view.get("status", "")),
        "revision": str(view.get("revision", "")),
    }
    return result


__all__ = [
    "doctor_command",
    "read_pipeline_command",
    "setup_command",
    "start_command",
    "status_command",
    "stop_command",
    "submit_requirement_command",
]
