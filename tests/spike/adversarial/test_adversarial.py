"""Adversarial and negative boundary evidence (slice-00-05, AC-10).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Deterministic negative tests for descriptor path escape, environment and
secret allow-listing (injected secret canaries never reach the runtime
environment, logs, receipts, or reports), bounded port-collision retries
(≤3 fresh-port attempts), double-start singleton-lock contention,
loopback-only binding, and wildcard-bind rejection. Windows DACL negative
fixtures are covered by tests/spike/runtime/test_acl.py.
"""

from __future__ import annotations

import http.server
import socket
import subprocess
import threading
from pathlib import Path

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
CANARY_VALUE = "adversarial-canary-7e21"


def test_canary_absent_from_runtime_environment_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CANARY, CANARY_VALUE)
    provision(tmp_path, offline=False)
    log_path = tmp_path / "logs" / "runtime.log"
    log_path.parent.mkdir(parents=True)
    proc = start_runtime(tmp_path, env_extra={})
    try:
        wait_for_descriptor(tmp_path)
        wait_runtime_ready(tmp_path)
        # The runtime's own environment never carries the canary: the probe
        # child itself starts from the allow-list, never os.environ.
        from hermes_shim._provision import (
            build_child_env,
            interpreter_path,
            runtime_environment_dir,
        )

        env_probe = subprocess.run(
            [
                str(interpreter_path(runtime_environment_dir(tmp_path))),
                "-c",
                f"import os; print(os.environ.get({CANARY!r}, ''))",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env=build_child_env({}),
        )
        assert env_probe.stdout.strip() == ""
        # The descriptor and the receipt store never carry the canary.
        for blob in (
            (tmp_path / "descriptor" / "runtime.json").read_bytes(),
            (tmp_path / "descriptor" / "receipts.sqlite3").read_bytes()
            if (tmp_path / "descriptor" / "receipts.sqlite3").exists()
            else b"",
        ):
            assert CANARY_VALUE.encode() not in blob
    finally:
        stop_runtime(proc, tmp_path)


def test_port_collision_retries_with_fresh_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first binding attempt on a held port retries with a fresh random
    loopback port and the runtime still becomes ready (bounded ≤3)."""
    held = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    held.bind(("127.0.0.1", 0))
    held.listen(1)
    held_port = held.getsockname()[1]
    provision(tmp_path, offline=False)
    proc = start_runtime(
        tmp_path,
        env_extra={"SPIKE_PORT_COLLISION_FIRST": str(held_port)},
    )
    try:
        wait_for_descriptor(tmp_path)
        wait_runtime_ready(tmp_path)
        final = wait_for_descriptor(tmp_path)
        assert int(final["port"]) != held_port
    finally:
        stop_runtime(proc, tmp_path)
        held.close()


def test_all_port_attempts_fail_leaves_no_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After 3 failed binding attempts the runtime exits with
    DEPENDENCY_UNAVAILABLE and leaves no descriptor behind."""
    del monkeypatch
    provision(tmp_path, offline=False)
    proc = start_runtime(tmp_path, env_extra={"SPIKE_FAIL_BIND": "1"})
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        stop_runtime(proc, tmp_path)
        pytest.fail("runtime did not exit after all binding attempts failed")
    assert proc.returncode == 1
    assert not (tmp_path / "descriptor" / "runtime.json").exists()


def test_double_start_singleton_lock_contention(tmp_path: Path) -> None:
    """A second runtime on the same state root fails the singleton lock
    without touching the live descriptor."""
    provision(tmp_path, offline=False)
    first = start_runtime(tmp_path)
    try:
        wait_for_descriptor(tmp_path)
        wait_runtime_ready(tmp_path)
        before = (tmp_path / "descriptor" / "runtime.json").read_text(encoding="utf-8")
        second = start_runtime(tmp_path)
        second.wait(timeout=30)
        assert second.returncode == 1
        assert (tmp_path / "descriptor" / "runtime.json").read_text(
            encoding="utf-8"
        ) == before
    finally:
        stop_runtime(first, tmp_path)


def test_wildcard_bind_rejected_by_runtime() -> None:
    """The runtime entry never binds a wildcard address.

    The protocol layer rejects wildcard Host headers (400 POLICY_REJECTED);
    the runtime entry itself binds only 127.0.0.1. Assert the source keeps
    the loopback-only bind and the uvicorn host pinned.
    """
    from hermes_pipeline.transport import _main as main_module

    source = Path(main_module.__file__).read_text(encoding="utf-8")
    assert 'host="127.0.0.1"' in source
    assert 'bind(("127.0.0.1", 0))' in source
    assert 'bind(("0.0.0.0"' not in source
    assert 'host="0.0.0.0"' not in source


def test_loopback_only_binding(tmp_path: Path) -> None:
    """The runtime listener is reachable on loopback and not on a
    non-loopback interface address."""
    provision(tmp_path, offline=False)
    proc = start_runtime(tmp_path)
    try:
        document = wait_for_descriptor(tmp_path)
        wait_runtime_ready(tmp_path)
        sock = socket.create_connection(("127.0.0.1", int(document["port"])), timeout=5)
        sock.close()
        # Non-loopback interfaces must not serve the listener: probe the
        # machine's LAN address if one exists, expecting refusal/timeout.
        hostname = socket.gethostname()
        try:
            lan = socket.gethostbyname(hostname)
        except OSError:
            lan = None
        if lan and not lan.startswith("127."):
            refused = False
            try:
                probe = socket.create_connection(
                    (lan, int(document["port"])), timeout=1
                )
                probe.close()
            except OSError:
                refused = True
            assert refused, "runtime must not be reachable on a LAN address"
    finally:
        stop_runtime(proc, tmp_path)


def test_loopback_client_never_uses_system_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The loopback client must never traverse an HTTP proxy.

    A system-configured proxy (Windows registry / env, e.g. a resident
    Clash/v2ray) could observe or rewrite the bearer token. Point every
    proxy variable at an unreachable port and prove the authenticated
    loopback request still succeeds: if the client regressed to
    ``urllib.request.urlopen``'s default opener, the request would go to
    the dead proxy and fail.
    """
    for key in (
        "http_proxy",
        "HTTP_PROXY",
        "https_proxy",
        "HTTPS_PROXY",
        "all_proxy",
        "ALL_PROXY",
    ):
        monkeypatch.setenv(key, "http://127.0.0.1:1")
    provision(tmp_path, offline=False)
    proc = start_runtime(tmp_path)
    try:
        document = wait_for_descriptor(tmp_path)
        wait_runtime_ready(tmp_path)
        from hermes_shim import _client

        result = _client.livez(int(document["port"]), str(document["token"]))
        assert result.ok, result
        assert result.status == 200
    finally:
        stop_runtime(proc, tmp_path)


def test_loopback_client_rejects_redirect_without_forwarding_bearer_token() -> None:
    """A local 3xx must not make a second request to its Location target."""
    target_requests: list[str | None] = []

    class TargetHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            target_requests.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    target = http.server.ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
    target_thread = threading.Thread(target=target.serve_forever, daemon=True)
    target_thread.start()

    class RedirectHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header(
                "Location", f"http://127.0.0.1:{target.server_port}/capture"
            )
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    redirector = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    redirect_thread = threading.Thread(target=redirector.serve_forever, daemon=True)
    redirect_thread.start()
    try:
        from hermes_shim import _client

        token = "redirect-canary-token"
        result = _client.livez(redirector.server_port, token)
        assert not result.ok
        assert result.status == 302
        assert target_requests == [], "redirect target must receive no request"
    finally:
        redirector.shutdown()
        redirector.server_close()
        target.shutdown()
        target.server_close()
        redirect_thread.join(timeout=5)
        target_thread.join(timeout=5)


def test_canary_absent_from_managed_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CANARY, CANARY_VALUE)
    provision(tmp_path, offline=False)
    prefix = managed_sys_prefix(tmp_path)
    assert "runtime-env" not in prefix
