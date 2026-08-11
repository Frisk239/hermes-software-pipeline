"""Managed Runtime provisioning for the Hermes Shim (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Cross-platform provisioning of the ADR-0028-authorized ``runtime-env/``
project into ``<state-root>/runtimes/<version>/``. The child process starts
from a fixture-built allow-list environment (never a copy of
``os.environ``), receives only the resolved executable/system essentials,
``UV_PROJECT_ENVIRONMENT``, and ``PYTHONDONTWRITEBYTECODE=1``, and runs a
controlled argv array (``[uv, sync, --frozen, --project, <repo>/runtime-env]``)
— never a shell string. The caller proves the target interpreter and
``sys.prefix`` are the state-root environment, never ``runtime-env/.venv``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ._constants import RUNTIME_VERSION, RUNTIMES_DIRNAME
from ._state import ensure_inside_state_root

# Environment allow-list: executable/system essentials only. No parent
# environment mapping is copied; role-specific values arrive via ``extra``.
ENV_ALLOWLIST_WINDOWS = ("PATH", "SystemRoot", "ComSpec", "USERPROFILE", "TEMP", "TMP")
ENV_ALLOWLIST_POSIX = ("PATH", "HOME", "TMPDIR", "TEMP", "TMP")


@dataclass(frozen=True)
class ProvisionResult:
    """One provision outcome with bounded evidence."""

    ok: bool
    environment_dir: Path
    interpreter: Path | None = None
    sys_prefix: str | None = None
    reason: str | None = None


def build_child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """A sanitized child environment: allow-list essentials + extras.

    Secret and credential variables can never reach the child because the
    mapping starts empty and only the documented keys are copied.
    """
    env: dict[str, str] = {}
    allow = ENV_ALLOWLIST_WINDOWS if os.name == "nt" else ENV_ALLOWLIST_POSIX
    for key in allow:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra:
        env.update(extra)
    return env


def runtime_environment_dir(state_root: Path) -> Path:
    """The managed environment target for the current runtime version."""
    return state_root / RUNTIMES_DIRNAME / RUNTIME_VERSION


def interpreter_path(environment_dir: Path) -> Path:
    """Per-platform interpreter inside the managed environment."""
    if os.name == "nt":
        return environment_dir / "Scripts" / "python.exe"
    return environment_dir / "bin" / "python"


def find_uv() -> str:
    """Resolve the uv executable from the current PATH (controlled argv)."""
    resolved = shutil.which("uv")
    if resolved is None:
        raise RuntimeError("uv executable not found on PATH")
    return resolved


def provision_runtime_env(
    runtime_env_project: Path,
    state_root: Path,
    *,
    offline: bool = False,
    uv_bin: str | None = None,
    env_extra: dict[str, str] | None = None,
    timeout_ms: int = 600000,
    reinstall_packages: tuple[str, ...] = ("hermes-pipeline",),
) -> ProvisionResult:
    """Provision the managed environment into a fresh state-root target.

    Uses the exact controlled argv ``[uv, sync, --frozen, (--offline),
    --project, <runtime-env>]`` with ``UV_PROJECT_ENVIRONMENT`` pointing at
    ``<state-root>/runtimes/<version>``. No ``PYTHONPATH`` manipulation.

    The path-sourced ``hermes-pipeline`` package is reinstalled on every
    sync: uv does not reliably detect working-tree changes of a path
    source under ``--frozen``, and the managed environment must always
    match the plugin checkout bytes (plugin update ⇒ runtime update).
    """
    environment_dir = runtime_environment_dir(state_root)
    try:
        ensure_inside_state_root(state_root, environment_dir)
    except Exception:
        return ProvisionResult(
            False, environment_dir, reason="environment escapes state root"
        )
    environment_dir.mkdir(parents=True, exist_ok=True)
    if uv_bin is None:
        find_uv()
    argv = ["uv", "sync", "--frozen"]
    if offline:
        argv.append("--offline")
    for package in reinstall_packages:
        argv.extend(["--reinstall-package", package])
    argv.extend(["--project", str(runtime_env_project)])
    env = build_child_env(
        {"UV_PROJECT_ENVIRONMENT": str(environment_dir), **(env_extra or {})}
    )
    try:
        proc = subprocess.run(
            argv,
            cwd=str(runtime_env_project),
            env=env,
            capture_output=True,
            timeout=timeout_ms / 1000,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ProvisionResult(False, environment_dir, reason=f"sync failed: {exc}")
    if proc.returncode != 0:
        return ProvisionResult(
            False, environment_dir, reason=f"sync exit {proc.returncode}"
        )
    interpreter = interpreter_path(environment_dir)
    if not interpreter.is_file():
        return ProvisionResult(False, environment_dir, reason="interpreter missing")
    prefix = _probe_sys_prefix(interpreter, env)
    if prefix is None:
        return ProvisionResult(False, environment_dir, reason="sys.prefix probe failed")
    if os.path.normcase(os.path.realpath(prefix)) != os.path.normcase(
        os.path.realpath(environment_dir)
    ):
        return ProvisionResult(
            False, environment_dir, reason="sys.prefix is not the state-root target"
        )
    return ProvisionResult(True, environment_dir, interpreter, prefix)


def _probe_sys_prefix(interpreter: Path, env: dict[str, str]) -> str | None:
    """Run the target interpreter and capture its sys.prefix."""
    try:
        proc = subprocess.run(
            [str(interpreter), "-c", "import sys; print(sys.prefix)"],
            env=env,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.decode("utf-8", errors="replace").strip()
    return value or None


__all__ = [
    "ProvisionResult",
    "build_child_env",
    "interpreter_path",
    "provision_runtime_env",
    "runtime_environment_dir",
]
