"""Shared managed-runtime provision harness for slice-00-05 spike tests.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Reuses the shim's cross-platform provision logic (controlled argv, fixture-
built allow-list child environment, ``UV_PROJECT_ENVIRONMENT`` beneath the
state root) and adds test-side conveniences: start the runtime process,
wait for the atomically written descriptor and readiness, and probe the
managed interpreter. The offline provision requires the uv cache populated
by an earlier online materialization (the workflow's dependency-bootstrap
stage); the unknown-secret canary never reaches any child because every
child environment starts from the allow-list, never a copy of
``os.environ``.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, cast

from hermes_shim._provision import (
    build_child_env,
    interpreter_path,
    provision_runtime_env,
    runtime_environment_dir,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ENV_DIR = REPO_ROOT / "runtime-env"

# Bounded wait budgets for the fake runtime lifecycle.
DESCRIPTOR_WAIT_SECONDS = 30
READY_WAIT_SECONDS = 30


def provision(state_root: Path, *, offline: bool = False) -> Path:
    """Provision the managed environment and return the interpreter path.

    ``offline=False`` uses an offline-first strategy with an online
    fallback: when the uv cache is already populated (a previous online
    materialization during dependency bootstrap) the sync completes
    offline; when the cache is missing the sync falls back online. This
    makes the first materialization the only network-dependent step, and
    every later materialization (including the second, fresh state-root
    run) offline — matching the contract's dependency-bootstrap boundary.

    ``offline=True`` forces the offline sync (cache must exist). Raises
    AssertionError with the bounded reason when provisioning fails.
    """
    if offline:
        result = provision_runtime_env(
            RUNTIME_ENV_DIR, state_root, offline=True, timeout_ms=600000
        )
        assert result.ok, f"offline provision failed: {result.reason}"
        assert result.interpreter is not None
        return result.interpreter
    result = provision_runtime_env(
        RUNTIME_ENV_DIR, state_root, offline=True, timeout_ms=600000
    )
    if not result.ok:
        result = provision_runtime_env(
            RUNTIME_ENV_DIR, state_root, offline=False, timeout_ms=600000
        )
        assert result.ok, f"provision failed: {result.reason}"
    assert result.interpreter is not None
    return result.interpreter


def start_runtime(
    state_root: Path,
    *,
    env_extra: dict[str, str] | None = None,
    extra_argv: list[str] | None = None,
) -> subprocess.Popen[bytes]:
    """Start the fake runtime as an independent interpreter process.

    NOTE: on Windows the venv ``python.exe`` is a launcher stub whose
    child is the real interpreter, so the Popen handle's PID differs from
    the runtime's own ``os.getpid()``. The descriptor records the real
    PID; ``stop_runtime`` terminates that PID, never just the handle.
    """
    interpreter = interpreter_path(runtime_environment_dir(state_root))
    assert interpreter.is_file(), "managed environment not provisioned"
    argv = [
        str(interpreter),
        "-u",  # unbuffered stdio so a stuck start is diagnosable from the log
        "-m",
        "hermes_pipeline.transport",
        "--state-root",
        str(state_root),
        *(extra_argv or []),
    ]
    env = build_child_env(
        {"HERMES_PIPELINE_STATE_ROOT": str(state_root), **(env_extra or {})}
    )
    # Runtime stdout/stderr go to the disposable state-root log so a stuck
    # or failed start is diagnosable from the test artifact.
    log_dir = state_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = (log_dir / "runtime.log").open("ab")
    return subprocess.Popen(
        argv,
        env=env,
        stdout=log_file,
        stderr=log_file,
    )


def stop_runtime(
    proc: subprocess.Popen[bytes],
    state_root: Path,
    timeout: float = 15.0,
) -> None:
    """Terminate the real runtime interpreter and its launcher handle.

    The descriptor's PID is the real interpreter; the Popen handle may be
    a venv launcher stub. On Windows the process tree is terminated with
    ``taskkill /T /F`` (controlled argv) because ``os.kill`` semantics for
    dead PIDs are unreliable on some hosts; POSIX uses terminate/kill.
    """
    import signal

    real_pid: int | None = None
    try:
        document = json.loads(
            (state_root / "descriptor" / "runtime.json").read_text("utf-8")
        )
        real_pid = int(document["pid"])
    except (OSError, ValueError, KeyError):
        pass

    if os.name == "nt":
        # os.kill(SIGTERM) maps to TerminateProcess and is reliable here;
        # taskkill /T /F additionally tears down the launcher process tree.
        # The round is retried because the descriptor may be rewritten by
        # the runtime between reads on slow hosts.
        for _round in range(3):
            real_pid = None
            try:
                document = json.loads(
                    (state_root / "descriptor" / "runtime.json").read_text("utf-8")
                )
                real_pid = int(document["pid"])
            except (OSError, ValueError, KeyError):
                pass
            import contextlib

            if real_pid is not None:
                with contextlib.suppress(OSError):
                    os.kill(real_pid, signal.SIGTERM)
            if proc.poll() is None:
                with contextlib.suppress(OSError):
                    proc.terminate()
            targets = {str(p) for p in (real_pid, proc.pid) if p is not None}
            for target in sorted(targets):
                with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                    subprocess.run(
                        ["taskkill", "/PID", target, "/T", "/F"],
                        capture_output=True,
                        timeout=timeout,
                    )
            if _pid_gone(real_pid, wait_seconds=5.0):
                break
        # Confirm the state-root singleton lock is released before the next
        # start (the previous runtime's process tree is gone).
        _wait_lock_released(state_root, timeout)
        return

    import contextlib

    if real_pid is not None and real_pid != proc.pid:
        with contextlib.suppress(OSError):
            os.kill(real_pid, signal.SIGTERM)
    if proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            with contextlib.suppress(OSError):
                proc.kill()
    if real_pid is not None:
        import contextlib

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with contextlib.suppress(OSError):
                os.kill(real_pid, 0)
            if not _pid_alive(real_pid):
                return
            time.sleep(0.1)


def wait_for_descriptor(
    state_root: Path, timeout: float = DESCRIPTOR_WAIT_SECONDS
) -> dict[str, Any]:
    """Wait for a valid descriptor whose recorded process is alive.

    A stale descriptor left by a previous runtime (its PID no longer
    exists) is skipped so the wait converges on the fresh runtime's
    descriptor; asserts bounded readiness.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            document = json.loads(
                (state_root / "descriptor" / "runtime.json").read_text("utf-8")
            )
            if isinstance(document, dict):
                document = cast(dict[str, Any], document)
                if document.get("port") and _pid_alive(int(document["pid"])):
                    return document
        except (OSError, ValueError, KeyError, TypeError):
            pass
        time.sleep(0.25)
    raise AssertionError("descriptor not written within the bounded wait")


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness probe (Windows tasklist, POSIX os.kill)."""
    if os.name == "nt":
        try:
            probe = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                timeout=10,
            )
            return str(pid) in probe.stdout.decode("utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired):
            return True  # cannot probe: do not reject the descriptor
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _pid_gone(pid: int | None, wait_seconds: float) -> bool:
    """True when the PID no longer appears in tasklist (bounded wait)."""
    if pid is None:
        return True
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        try:
            probe = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return True  # cannot probe: treat as gone
        if str(pid) not in probe.stdout.decode("utf-8", errors="replace"):
            return True
        time.sleep(0.2)
    return False


def _wait_lock_released(state_root: Path, timeout: float) -> None:
    """Wait until the state-root singleton lock can be acquired."""
    from hermes_pipeline.transport._lock import StateRootLock, StateRootLockError

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        lock = StateRootLock(state_root)
        try:
            lock.acquire()
            lock.release()
            return
        except StateRootLockError:
            time.sleep(0.2)


def wait_runtime_ready(state_root: Path, timeout: float = READY_WAIT_SECONDS) -> None:
    """Poll /readyz (authenticated) until the runtime reports ready.

    Connection refusals during startup are expected (the runtime may not
    have bound its loopback socket yet) and are retried until the bounded
    deadline; only a deadline expiry fails.
    """
    from hermes_shim import _client

    document = wait_for_descriptor(state_root, timeout)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            probe = _client.readyz(int(document["port"]), str(document["token"]))
        except _client.RuntimeUnavailableError:
            time.sleep(0.25)
            continue
        if probe.ok:
            return
        time.sleep(0.25)
    raise AssertionError("runtime did not become ready within the bounded wait")


def managed_sys_prefix(state_root: Path) -> str:
    """Prove the managed interpreter's sys.prefix is the state-root target."""
    interpreter = interpreter_path(runtime_environment_dir(state_root))
    env = build_child_env({})
    proc = subprocess.run(
        [str(interpreter), "-c", "import sys; print(sys.prefix)"],
        env=env,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, "managed interpreter probe failed"
    return proc.stdout.decode("utf-8").strip()
