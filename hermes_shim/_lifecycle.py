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
    from ._runtimes import catalog_families, detect_runtime_executables

    detected = detect_runtime_executables()
    for family in catalog_families():
        if family in detected:
            _add_check(result, family, "ok", "AGENT_DETECTED")
        else:
            _add_check(result, family, "ok", "AGENT_MISSING")

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
    from ._runtimes import detect_runtime_executables, write_runtime_pins

    write_runtime_pins(root, detect_runtime_executables())

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


def _plugin_checkout(home: Path) -> Path:
    return home / "plugins" / "hermes-software-pipeline"


def _ensure_runtime(home: Path) -> bool:
    root = state_root(home)
    document = read_descriptor(root)
    if document is not None and not is_stale(root):
        return True
    plugin = _plugin_checkout(home)
    if not plugin.is_dir():
        return False
    return start_command(home, plugin).ok


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
    if not _ensure_runtime(home):
        _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
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
    if not _ensure_runtime(home):
        _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
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
    raw_view = body.get("receipt") if isinstance(body.get("receipt"), dict) else body
    view = raw_view if isinstance(raw_view, dict) else {}
    result.detail = {
        "pipeline_id": str(view.get("pipeline_id", pipeline_id)),
        "status": str(view.get("status", "")),
        "revision": str(view.get("revision", "")),
    }
    for key in (
        "branch",
        "pr_number",
        "head_sha",
        "action",
        "pr_url",
        "github_repo",
        "check_status",
        "review_status",
        "queue_status",
        "prd_id",
        "prd_status",
        "prd_gate",
        "design_id",
        "testplan_id",
        "arch_status",
        "arch_gate",
        "impl_id",
        "candidate_sha",
        "candidate_path",
        "dev_status",
        "candidate_gate",
        "verify_status",
        "verify_attempts",
        "e2e_id",
        "acceptance_id",
        "approval_status",
        "approver_id",
        "requirement_text",
    ):
        if key in view:
            result.detail[key] = str(view[key])
    from ._github import load_published, observe_pr

    published = load_published(root, pipeline_id)
    result.detail.update(published)
    repo = result.detail.get("github_repo", "")
    number = result.detail.get("pr_number", "")
    if repo and number:
        result.detail.update(observe_pr(repo, number))
    return result


def deliver_command(
    home: Path,
    *,
    sha: str,
    project_id: str,
    pipeline_id: str,
    event_id: str = "",
    check_status: str = "",
    review_status: str = "",
    queue_status: str = "",
) -> LifecycleResult:
    result = LifecycleResult(command="deliver")
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
            "cmd_deliver",
            {
                "op": "deliver",
                "sha": sha,
                "project_id": project_id,
                "pipeline_id": pipeline_id,
                "event_id": event_id,
                "check_status": check_status,
                "review_status": review_status,
                "queue_status": queue_status,
            },
        )
    except _client.RuntimeUnavailableError:
        _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    body = reply.body or {}
    receipt = body.get("receipt") if isinstance(body.get("receipt"), dict) else body
    result.ok = bool(reply.ok and receipt.get("ok", True))
    result.exit_code = EXIT_OK if result.ok else EXIT_FAIL
    result.detail = {key: str(value) for key, value in receipt.items()}
    return result


def approve_command(
    home: Path,
    *,
    project_id: str,
    pipeline_id: str,
    principal_id: str,
    workspace_id: str = "ws_local",
) -> LifecycleResult:
    result = LifecycleResult(command="approve")
    if not _ensure_runtime(home):
        _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
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
            "cmd_approve",
            {
                "op": "approve",
                "project_id": project_id,
                "pipeline_id": pipeline_id,
                "principal_id": principal_id,
                "workspace_id": workspace_id,
            },
        )
    except _client.RuntimeUnavailableError:
        _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    body = reply.body or {}
    receipt = body.get("receipt") if isinstance(body.get("receipt"), dict) else body
    if not isinstance(receipt, dict):
        receipt = {}
    if receipt.get("running"):
        receipt = _wait_for_verify(home, workspace_id, pipeline_id, receipt)
        document = read_descriptor(root)
        if document is None or is_stale(root):
            _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
            result.ok = False
            result.exit_code = EXIT_FAIL
            return result
    result.ok = bool(reply.ok and receipt.get("ok", True))
    result.exit_code = EXIT_OK if result.ok else EXIT_FAIL
    result.detail = {key: str(value) for key, value in receipt.items()}
    if result.ok and result.detail.get("verify_status") == "READY":
        result.detail.update(_host_github_publish(root, project_id, pipeline_id))
    return result


def _wait_for_verify(
    home: Path,
    workspace_id: str,
    pipeline_id: str,
    started: dict[str, Any],
) -> dict[str, Any]:
    import time

    deadline = time.monotonic() + 1200
    latest: dict[str, Any] = dict(started)
    while time.monotonic() < deadline:
        view = read_pipeline_command(
            home, workspace_id=workspace_id, pipeline_id=pipeline_id
        )
        detail = view.detail if view.ok else {}
        latest = {**started, **detail}
        status = str(detail.get("verify_status", ""))
        gate = str(detail.get("candidate_gate", ""))
        if status in {"READY", "REWORK", "INFRA", "DENIED", "DRIFT"}:
            latest["ok"] = status == "READY" and gate != "FAIL"
            latest["running"] = False
            return latest
        if gate == "FAIL" and status != "":
            latest["ok"] = False
            latest["running"] = False
            return latest
        time.sleep(2)
    latest["ok"] = False
    latest["error"] = "timeout"
    latest["running"] = False
    return latest


def retry_command(
    home: Path,
    *,
    project_id: str,
    pipeline_id: str,
    principal_id: str,
    workspace_id: str = "ws_local",
) -> LifecycleResult:
    result = LifecycleResult(command="retry")
    if not _ensure_runtime(home):
        _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
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
            "cmd_retry",
            {
                "op": "retry",
                "project_id": project_id,
                "pipeline_id": pipeline_id,
                "principal_id": principal_id,
                "workspace_id": workspace_id,
            },
        )
    except _client.RuntimeUnavailableError:
        _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    body = reply.body or {}
    receipt = body.get("receipt") if isinstance(body.get("receipt"), dict) else body
    if not isinstance(receipt, dict):
        receipt = {}
    if receipt.get("running"):
        receipt = _wait_for_verify(home, workspace_id, pipeline_id, receipt)
    result.ok = bool(reply.ok and receipt.get("ok", True))
    result.exit_code = EXIT_OK if result.ok else EXIT_FAIL
    result.detail = {key: str(value) for key, value in receipt.items()}
    if result.ok and result.detail.get("verify_status") == "READY":
        result.detail.update(_host_github_publish(root, project_id, pipeline_id))
    return result


def _host_github_publish(
    root: Path, project_id: str, pipeline_id: str
) -> dict[str, str]:
    from ._github import publish_with_gh, worktree_files, write_published

    path = root / "descriptor" / "github.json"
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(document, dict):
        return {}
    repo = str(document.get("repo", ""))
    base = str(document.get("base", "main"))
    files = worktree_files(root, pipeline_id)
    if not repo or not files:
        return {}
    published = publish_with_gh(
        repo=repo,
        project_id=project_id,
        pipeline_id=pipeline_id,
        sha="approved",
        files=files,
        base=base,
    )
    if published:
        write_published(root, pipeline_id, published)
    return published


def admin_command(
    home: Path,
    *,
    register: bool,
    admit: bool,
    bind: bool,
    project_id: str,
    name: str,
    principal_id: str,
    member_role: str,
    role: str,
    runtime: str,
    model: str,
    github_repo: str = "",
    runtimes: bool = False,
) -> LifecycleResult:
    result = LifecycleResult(command="admin")
    payload: dict[str, str] = {}
    if runtimes:
        payload = {"op": "runtimes"}
    elif github_repo:
        payload = {"op": "github", "repo": github_repo}
    elif register:
        payload = {"op": "register", "project_id": project_id, "name": name}
    elif admit:
        payload = {
            "op": "admit",
            "project_id": project_id,
            "principal_id": principal_id,
            "role": member_role,
        }
    elif bind:
        payload = {"op": "bind", "role": role, "runtime": runtime, "model": model}
    else:
        payload = {"op": "bindings"}
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
            "cmd_admin",
            payload,
        )
    except _client.RuntimeUnavailableError:
        _add_check(result, "runtime", "error", "RUNTIME_UNAVAILABLE")
        result.ok = False
        result.exit_code = EXIT_FAIL
        return result
    body = reply.body or {}
    receipt = body.get("receipt") if isinstance(body.get("receipt"), dict) else body
    result.ok = bool(reply.ok and receipt.get("ok", True))
    result.exit_code = EXIT_OK if result.ok else EXIT_FAIL
    result.detail = {key: str(value) for key, value in receipt.items()}
    return result


__all__ = [
    "LifecycleResult",
    "admin_command",
    "approve_command",
    "deliver_command",
    "doctor_command",
    "read_pipeline_command",
    "retry_command",
    "setup_command",
    "start_command",
    "status_command",
    "stop_command",
    "submit_requirement_command",
]
