"""Shim lifecycle CLI command semantics (slice-00-05, AC-07/AC-08).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

``setup``, ``doctor``, ``status``, and ``stop`` are exercised against a
temporary HERMES_HOME without a running runtime (deterministic, offline).
Every result is structured bounded JSON with stable exit codes; no
hostname, username, absolute path, environment value, token, raw
exception, or database content appears in any output (redaction assertion
with injected fake sensitive values). ``start`` idempotency with a real
runtime is covered by tests/spike/lifecycle.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from hermes_shim._client import ClientResult
from hermes_shim._lifecycle import (
    LifecycleResult,
    doctor_command,
    read_pipeline_command,
    setup_command,
    status_command,
    stop_command,
)
from hermes_shim._state import ensure_layout, state_root

# Injected fake sensitive values that must never appear in any output.
FAKE_HOSTNAME = "fake-host-7f3a"
FAKE_USERNAME = "fake-user-9b2c"
FAKE_ABSOLUTE_PATH = "C:\\fake\\absolute\\path\\9d1e"
FAKE_ENV_VALUE = "fake-env-value-41c8"
FAKE_SECRET = "fake-secret-token-71a5"


def _output_text(result: object) -> str:
    render = getattr(result, "as_json", None)
    return str(render()) if callable(render) else str(result)


def _assert_redacted(result: object) -> None:
    text = _output_text(result)
    for forbidden in (
        FAKE_HOSTNAME,
        FAKE_USERNAME,
        FAKE_ABSOLUTE_PATH,
        FAKE_ENV_VALUE,
        FAKE_SECRET,
    ):
        assert forbidden not in text, f"sensitive value leaked: {forbidden}"
    assert "Bearer " not in text
    assert "Traceback" not in text


def test_setup_creates_layout_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    first = setup_command(tmp_path)
    second = setup_command(tmp_path)
    assert first.ok and second.ok
    assert first.exit_code == 0 and second.exit_code == 0
    root = state_root(tmp_path)
    for child in ("descriptor", "runtimes", "logs"):
        assert (root / child / "OWNERSHIP").is_file()
    assert json.loads(first.as_json())["command"] == "setup"


def test_setup_reports_state_root_check(tmp_path: Path) -> None:
    result = setup_command(tmp_path)
    checks = json.loads(result.as_json())["checks"]
    assert {
        "component": "state-root",
        "status": "ok",
        "code": "STATE_ROOT_OK",
    } in checks


def test_doctor_without_runtime_reports_actionable_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    root = state_root(tmp_path)
    result = doctor_command(tmp_path, tmp_path)
    assert not result.ok
    assert result.exit_code == 1
    codes = {c["code"] for c in result.checks}
    assert "STATE_ROOT_INVALID" in codes
    assert "RUNTIME_ENV_MISSING" in codes
    assert "DESCRIPTOR_MISSING" in codes
    assert "RUNTIME_UNREACHABLE" in codes
    _assert_redacted(result)
    # doctor reports and never repairs: the missing state root stays
    # absent with zero writes.
    assert not root.exists(), "doctor must never create the state root"


def test_doctor_with_stale_descriptor_reports_descriptor_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    root = state_root(tmp_path)
    ensure_layout(root)
    # A descriptor whose PID cannot exist: stale proof via the
    # start-identity algorithm.
    descriptor = {
        "descriptor_version": 1,
        "protocol_version": 1,
        "pid": 2**31 - 1,
        "start_identity": "0" * 32,
        "creation_time": "2026-01-01T00:00:00.000000Z",
        "process_start_marker": {"value": "0", "source": "proc_stat_field22"},
        "port": 1,
        "token": "0" * 64,
        "token_generation": 1,
        "release": "hermes-pipeline-0.1.0-slice-00-05-spike",
        "state_root_identity": "0" * 64,
    }
    import json as _json

    (root / "descriptor" / "runtime.json").write_text(
        _json.dumps(descriptor), encoding="utf-8"
    )
    result = doctor_command(tmp_path, tmp_path)
    codes = {c["code"] for c in result.checks}
    assert "DESCRIPTOR_STALE" in codes
    assert "RUNTIME_UNREACHABLE" in codes
    _assert_redacted(result)


def test_status_without_runtime_fails_closed(tmp_path: Path) -> None:
    result = status_command(tmp_path)
    assert not result.ok
    assert result.exit_code == 1
    codes = {c["code"] for c in result.checks}
    assert "RUNTIME_UNAVAILABLE" in codes
    _assert_redacted(result)


def test_stop_without_runtime_is_noop_with_stable_exit(tmp_path: Path) -> None:
    result = stop_command(tmp_path)
    assert result.ok
    assert result.exit_code == 0
    codes = {c["code"] for c in result.checks}
    assert "RUNTIME_STOPPED" in codes
    _assert_redacted(result)


def test_doctor_output_never_contains_sensitive_values(tmp_path: Path) -> None:
    os.environ["HERMES_HOME"] = str(tmp_path)
    os.environ["FAKE_HOSTNAME"] = FAKE_HOSTNAME
    os.environ["FAKE_USERNAME"] = FAKE_USERNAME
    os.environ["FAKE_ENV_VALUE"] = FAKE_ENV_VALUE
    os.environ["FAKE_SECRET"] = FAKE_SECRET
    try:
        result = doctor_command(tmp_path, tmp_path)
    finally:
        for key in ("FAKE_HOSTNAME", "FAKE_USERNAME", "FAKE_ENV_VALUE", "FAKE_SECRET"):
            os.environ.pop(key, None)
    _assert_redacted(result)


def test_read_revives_runtime_when_plugin_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_command(tmp_path)
    (tmp_path / "plugins" / "hermes-software-pipeline").mkdir(parents=True)
    called: list[Path] = []

    def fake_start(home: Path, plugin_dir: Path) -> LifecycleResult:
        del home
        called.append(plugin_dir)
        return LifecycleResult(command="start", ok=False, exit_code=1)

    monkeypatch.setattr("hermes_shim._lifecycle.start_command", fake_start)
    result = read_pipeline_command(
        tmp_path, workspace_id="ws_cli", pipeline_id="pl_cli"
    )
    assert called
    assert result.ok is False


def test_read_publishes_pr_when_verify_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_command(tmp_path)
    called: list[tuple[str, str]] = []

    def fake_start(home: Path, plugin_dir: Path) -> LifecycleResult:
        del home, plugin_dir
        return LifecycleResult(command="start", ok=True, exit_code=0)

    def fake_submit(*_args: object, **_kwargs: object) -> ClientResult:
        return ClientResult(
            ok=True,
            status=202,
            body={
                "pipeline_id": "pl_cli",
                "status": "OPEN",
                "verify_status": "READY",
                "github_repo": "org/repo",
            },
        )

    def fake_publish(root: Path, project_id: str, pipeline_id: str) -> dict[str, str]:
        del root
        called.append((project_id, pipeline_id))
        return {
            "pr_number": "9",
            "pr_url": "https://github.com/org/repo/pull/9",
        }

    def fake_descriptor(_root: Path) -> dict[str, object]:
        return {"port": 1, "token": "t"}

    def fake_stale(_root: Path) -> bool:
        return False

    def fake_published(*_args: object, **_kwargs: object) -> dict[str, str]:
        return {}

    def fake_observe(*_args: object, **_kwargs: object) -> dict[str, str]:
        return {}

    monkeypatch.setattr("hermes_shim._lifecycle.start_command", fake_start)
    monkeypatch.setattr("hermes_shim._lifecycle.read_descriptor", fake_descriptor)
    monkeypatch.setattr("hermes_shim._lifecycle.is_stale", fake_stale)
    monkeypatch.setattr("hermes_shim._client.submit_command", fake_submit)
    monkeypatch.setattr("hermes_shim._lifecycle._host_github_publish", fake_publish)
    monkeypatch.setattr("hermes_shim._github.load_published", fake_published)
    monkeypatch.setattr("hermes_shim._github.observe_pr", fake_observe)
    result = read_pipeline_command(
        tmp_path, workspace_id="ws_cli", pipeline_id="pl_cli"
    )
    assert called == [("prj_local", "pl_cli")]
    assert result.ok is True
    assert result.detail.get("pr_url") == "https://github.com/org/repo/pull/9"
