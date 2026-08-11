"""Managed-runtime provision harness acceptance (slice-00-05, AC-04).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

The three contract verification commands (``runtime-provision``,
``runtime-provision-offline``, ``runtime-selfcheck``) run the cross-
platform harness from clean checkouts into fresh state roots: controlled
``uv sync`` argv with ``UV_PROJECT_ENVIRONMENT`` beneath the state root,
interpreter and ``sys.prefix`` proof (never ``runtime-env/.venv``), offline
re-materialization, self-check through the state-root interpreter, an
unknown-secret canary absent from every child, and the full loopback
protocol matrix against the real FastAPI/Uvicorn surface.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from tests.spike.runtime._harness import (
    managed_sys_prefix,
    provision,
    start_runtime,
    stop_runtime,
    wait_for_descriptor,
    wait_runtime_ready,
)

CANARY = "UNKNOWN_SECRET_CANARY"
CANARY_VALUE = "slice-00-05-canary-9f31"

EXPECTED_DESCRIPTOR_FIELDS = {
    "descriptor_version",
    "protocol_version",
    "pid",
    "start_identity",
    "creation_time",
    "process_start_marker",
    "port",
    "token",
    "token_generation",
    "release",
    "state_root_identity",
}


# The loopback probe client never traverses an HTTP proxy (the shim client
# also binds an empty ProxyHandler; a system proxy could observe or rewrite
# the bearer token).
_PROBE_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _http(
    port: int,
    token: str,
    path: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    protocol: str = "1",
    auth_token: str | None = None,
    no_auth: bool = False,
    origin: str | None = None,
    host: str | None = None,
) -> tuple[int, dict[str, Any] | None]:
    headers = {
        "X-Hermes-Pipeline-Protocol": protocol,
        "Accept": "application/json",
    }
    if not no_auth:
        effective = token if auth_token is None else auth_token
        headers["Authorization"] = f"Bearer {effective}"
    if origin is not None:
        headers["Origin"] = origin
    if host is not None:
        headers["Host"] = host
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = body
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with _PROBE_OPENER.open(request, timeout=10) as response:
            raw = response.read()
            return int(response.status), json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return int(exc.code), json.loads(raw) if raw else None


def test_provisions_fresh_state_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """runtime-provision: fresh state root, online-fallback provision,
    sys.prefix proof, canary absence, descriptor, and the full loopback
    protocol matrix against the real FastAPI/Uvicorn runtime."""
    monkeypatch.setenv(CANARY, CANARY_VALUE)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")

    interpreter = provision(tmp_path, offline=False)
    assert interpreter.is_file()

    # sys.prefix must be the state-root target, never runtime-env/.venv.
    prefix = managed_sys_prefix(tmp_path)
    assert os.path.normcase(prefix) == os.path.normcase(
        str(tmp_path / "runtimes" / "0.1.0")
    ), f"sys.prefix {prefix} must be the state-root target"
    assert "runtime-env" not in os.path.normcase(prefix)

    # Canary absent from the managed interpreter's environment.
    proc_env = _managed_env_probe(interpreter)
    assert CANARY not in proc_env, "secret canary reached the managed interpreter"

    proc = start_runtime(tmp_path)
    try:
        document = wait_for_descriptor(tmp_path)
        wait_runtime_ready(tmp_path)
        port = int(document["port"])
        token = str(document["token"])
        assert set(document) == EXPECTED_DESCRIPTOR_FIELDS
        assert len(document["start_identity"]) == 32
        assert len(token) == 64
        assert document["protocol_version"] == 1
        assert document["release"].startswith("hermes-pipeline-0.1.0")
        assert document["state_root_identity"]

        # Livez / readyz / version.
        status, body = _http(port, token, "/livez")
        assert (status, body) == (200, {"status": "alive"})
        status, body = _http(port, token, "/readyz")
        assert status == 200 and body is not None and body["ready"] is True
        status, body = _http(port, token, "/v1/version")
        assert status == 200
        assert body is not None
        assert body["protocol_version"] == 1
        assert body["runtime_version"] == "0.1.0"
        assert body["release"] == document["release"]
        assert body["state_root_identity"] == document["state_root_identity"]

        # Fake command happy path + dedup.
        envelope = json.dumps(
            {"command_id": "cmd_provision_1", "payload": {"op": "fake"}}
        ).encode()
        status, body = _http(port, token, "/v1/commands", method="POST", body=envelope)
        assert status == 202
        assert body is not None and body["receipt"]["deduplicated"] is False
        status, body = _http(port, token, "/v1/commands", method="POST", body=envelope)
        assert status == 202
        # The duplicate returns the original receipt unchanged.
        assert body is not None and body["receipt"]["deduplicated"] is False
        assert body["receipt"]["effect_count"] == 1

        # Fixed failure matrix over the real surface.
        cases = [
            (
                "bad-token",
                _http(port, token, "/v1/version", auth_token="deadbeef"),
                (401, "AUTHENTICATION_FAILED"),
            ),
            (
                "no-auth",
                _http(port, token, "/v1/version", no_auth=True),
                (401, "AUTHENTICATION_FAILED"),
            ),
            (
                "bad-protocol",
                _http(port, token, "/v1/version", protocol="0"),
                (400, "VALIDATION_ERROR"),
            ),
            (
                "missing-protocol",
                _http(port, token, "/v1/version", protocol=""),
                (400, "VALIDATION_ERROR"),
            ),
            (
                "bad-host",
                _http(port, token, "/v1/version", host="127.0.0.1:1"),
                (400, "POLICY_REJECTED"),
            ),
            (
                "bad-origin",
                _http(port, token, "/v1/version", origin="http://evil.example"),
                (403, "POLICY_REJECTED"),
            ),
            ("unknown-path", _http(port, token, "/nope"), (404, "NOT_FOUND")),
        ]
        for name, (status, body), (expected_status, expected_code) in cases:
            assert status == expected_status, name
            assert body is not None and body["code"] == expected_code, name
            text = json.dumps(body).lower()
            assert "traceback" not in text and "exception" not in text, name

        # Oversize body over the real surface (413).
        big = json.dumps(
            {"command_id": "big", "payload": {"pad": "x" * 70_000}}
        ).encode()
        status, body = _http(port, token, "/v1/commands", method="POST", body=big)
        assert status == 413
        assert body is not None and body["code"] == "VALIDATION_ERROR"

        # Rate limit over the real surface: 60 allowed, 61st rejected
        # (health probes are exempt).
        for _ in range(60):
            _http(port, token, "/v1/version")
        status, body = _http(port, token, "/v1/version")
        assert status == 429
        assert body is not None and body["code"] == "RATE_LIMITED"
    finally:
        stop_runtime(proc, tmp_path)


def test_reprovisions_fresh_state_root_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """runtime-provision-offline: a second fresh state root materializes
    fully offline (uv cache from the bootstrap stage) and proves the
    target interpreter."""
    monkeypatch.setenv(CANARY, CANARY_VALUE)
    interpreter = provision(tmp_path, offline=True)
    prefix = managed_sys_prefix(tmp_path)
    assert os.path.normcase(prefix) == os.path.normcase(
        str(tmp_path / "runtimes" / "0.1.0")
    )
    proc_env = _managed_env_probe(interpreter)
    assert CANARY not in proc_env


def test_runs_selfcheck_in_managed_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """runtime-selfcheck: the state-root interpreter self-checks the
    declared package without PYTHONPATH manipulation.

    The self-check child runs with the fixture-built allow-list environment
    (never a copy of ``os.environ``), so an injected secret canary in the
    parent cannot be inherited by the child.
    """
    monkeypatch.setenv(CANARY, CANARY_VALUE)
    interpreter = provision(tmp_path, offline=False)
    import subprocess

    from hermes_shim._provision import build_child_env

    env = build_child_env({})
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # The allow-list environment never carries the canary into the child.
    assert CANARY not in env, "allow-list environment contains the canary"
    proc = subprocess.run(
        [
            str(interpreter),
            "-c",
            "import os, sys, hermes_pipeline; "
            "print(sys.prefix); print(hermes_pipeline.__version__); "
            "print('UNKNOWN_SECRET_CANARY' in os.environ)",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert len(lines) == 3
    assert os.path.normcase(lines[0]) == os.path.normcase(
        str(tmp_path / "runtimes" / "0.1.0")
    )
    assert lines[1] == "0.1.0"
    assert lines[2] == "False", "secret canary reached the self-check child"


def _managed_env_probe(interpreter: Path) -> dict[str, str]:
    """Print the managed interpreter's environment through an allow-list
    child (used to prove canary absence)."""
    import subprocess

    from hermes_shim._provision import build_child_env

    env = build_child_env({})
    proc = subprocess.run(
        [
            str(interpreter),
            "-c",
            "import os, json; print(json.dumps(dict(os.environ)))",
        ],
        env=env,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    return json.loads(proc.stdout.decode("utf-8"))
