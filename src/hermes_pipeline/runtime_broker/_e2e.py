"""Locked controlled-E2E wiring: fixture page, mock provider, OpenCode config.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urlparse

from hermes_pipeline.runtime_broker._codex import (
    classify_codex_jsonl,
    sanctioned_codex_argv,
)
from hermes_pipeline.runtime_broker._identity import PLATFORM, mcp_argv
from hermes_pipeline.runtime_broker._opencode import classify_opencode_events
from hermes_pipeline.runtime_broker._process import run_fenced

FIXTURE_BODY = (
    "<!doctype html><html><head><title>Hermes E2E Fixture</title></head>"
    "<body><main id=hermes-proof data-proof=hermes-00-06>"
    "Hermes browser proof</main></body></html>"
)
E2E_OK = (
    "HERMES_E2E_OK title=Hermes E2E Fixture proof=hermes-00-06 "
    "text=Hermes browser proof"
)
EVAL_FN = (
    "() => ({title: document.title, "
    "proof: document.querySelector('#hermes-proof')?.dataset.proof, "
    "text: document.querySelector('#hermes-proof')?.textContent})"
)


def fixture_response(path: str) -> tuple[int, str, str]:
    """GET /page is 200; every other path is 404."""
    if path == "/page":
        return 200, "text/html", FIXTURE_BODY
    return 404, "text/plain", "not found"


class MockChatProvider:
    """OpenAI-compatible mock: exactly three /v1/chat/completions calls."""

    def __init__(self, fixture_port: int) -> None:
        self.fixture_port = fixture_port
        self.calls = 0

    def handle(self, method: str, path: str, body: bytes) -> tuple[int, str, bytes]:
        if method != "POST" or path != "/v1/chat/completions":
            return 409, "application/json", b'{"error":"conflict"}'
        self.calls += 1
        url = f"http://127.0.0.1:{self.fixture_port}/page"
        if self.calls == 1:
            payload = {
                "model": "hermes-fixture",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "chrome-devtools_navigate_page",
                                        "arguments": json.dumps({"url": url}),
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
            return 200, "application/json", json.dumps(payload).encode("utf-8")
        if self.calls == 2:
            payload = {
                "model": "hermes-fixture",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call_2",
                                    "type": "function",
                                    "function": {
                                        "name": "chrome-devtools_evaluate_script",
                                        "arguments": json.dumps({"function": EVAL_FN}),
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
            return 200, "application/json", json.dumps(payload).encode("utf-8")
        if self.calls == 3:
            payload = {
                "model": "hermes-fixture",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": E2E_OK},
                    }
                ],
            }
            return 200, "application/json", json.dumps(payload).encode("utf-8")
        return 409, "application/json", b'{"error":"conflict"}'


def mcp_config(command: list[str], environment: dict[str, str]) -> dict[str, Any]:
    """Exact locked MCP object. No extra fields."""
    return {
        "type": "local",
        "command": command,
        "environment": environment,
        "enabled": True,
        "timeout": 30000,
    }


def write_opencode_config(
    state_root: Path,
    *,
    provider_port: int,
    mcp: dict[str, Any],
) -> Path:
    """Write state-root OpenCode config. Never writes into the snapshot."""
    config_dir = state_root / "tools" / "opencode-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (state_root / "tools" / "opencode-empty-config").mkdir(parents=True, exist_ok=True)
    (state_root / "tools" / "opencode-data").mkdir(parents=True, exist_ok=True)
    (state_root / "child-home").mkdir(parents=True, exist_ok=True)
    payload = {
        "$schema": "https://opencode.ai/config.json",
        "autoupdate": False,
        "share": "disabled",
        "provider": {
            "fixture": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Hermes Fixture",
                "options": {
                    "baseURL": f"http://127.0.0.1:{provider_port}/v1",
                    "apiKey": "hermes-fixture-key",
                },
                "models": {"hermes-fixture": {"name": "Hermes Fixture"}},
            }
        },
        "mcp": {"chrome-devtools": mcp},
        "permission": {"*": "deny", "chrome-devtools_*": "allow"},
    }
    path = config_dir / "opencode.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def write_opencode_probe_config(state_root: Path, provider_port: int) -> Path:
    """Probe config: fixture provider only, no MCP."""
    config_dir = state_root / "tools" / "opencode-probe-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "$schema": "https://opencode.ai/config.json",
        "autoupdate": False,
        "share": "disabled",
        "provider": {
            "fixture": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Hermes Fixture",
                "options": {
                    "baseURL": f"http://127.0.0.1:{provider_port}/v1",
                    "apiKey": "hermes-fixture-key",
                },
                "models": {"hermes-fixture": {"name": "Hermes Fixture"}},
            }
        },
        "permission": {"*": "deny"},
    }
    path = config_dir / "opencode.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def opencode_e2e_argv(
    lock: dict[str, Any], state_root: Path, snapshot: Path
) -> list[str]:
    """Locked OpenCode E2E argv."""
    key = f"opencode-{PLATFORM}"
    executable = lock["agent_cli_executables"]["executables"][key].replace(
        "<state-root>", str(state_root)
    )
    return [
        executable,
        "run",
        "--pure",
        "--format",
        "json",
        "--model",
        "fixture/hermes-fixture",
        "--agent",
        "build",
        "--auto",
        "--dir",
        str(snapshot),
        "Use only the chrome-devtools MCP tools. Navigate to the provided "
        "loopback fixture page, read its title and #hermes-proof data-proof "
        "and text, then report them exactly.",
    ]


def e2e_success(stdout: str, provider_calls: int) -> bool:
    """Exact lock oracle. tools/list is never this oracle."""
    if provider_calls != 3:
        return False
    if "tools/list" in stdout:
        return False
    if "permission.denied" in stdout:
        return False
    nav = stdout.find("chrome-devtools_navigate_page")
    evl = stdout.find("chrome-devtools_evaluate_script")
    if nav < 0 or evl < 0 or nav > evl:
        return False
    if "http://127.0.0.1:" not in stdout:
        return False
    if "Hermes E2E Fixture" not in stdout:
        return False
    if "hermes-00-06" not in stdout:
        return False
    if "Hermes browser proof" not in stdout:
        return False
    if E2E_OK not in stdout:
        return False
    unexpected = ("bash", "shell", "edit", "write", "read")
    for name in unexpected:
        token = f'"{name}"'
        if token in stdout and f"chrome-devtools_{name}" not in stdout:
            return False
    return True


def cleanup_mcp_profile(state_root: Path) -> None:
    """Remove temporary MCP profile directories under state-root."""
    profile = state_root / "tools" / "browser-runtime" / "mcp-profile"
    if profile.exists():
        for child in profile.rglob("*"):
            if child.is_file():
                child.unlink()
        for child in sorted(profile.rglob("*"), reverse=True):
            if child.is_dir():
                child.rmdir()
        profile.rmdir()


class _Handler(BaseHTTPRequestHandler):
    fixture = True
    provider: MockChatProvider | None = None

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        status, ctype, body = fixture_response(path)
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        if self.provider is None:
            self.send_error(409)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        status, ctype, payload = self.provider.handle(
            "POST", urlparse(self.path).path, body
        )
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def start_loopback_servers(
    provider: MockChatProvider,
) -> tuple[ThreadingHTTPServer, ThreadingHTTPServer]:
    """Bind fixture and provider to Host-reserved 127.0.0.1 ports."""

    class Fixture(_Handler):
        pass

    class Provider(_Handler):
        pass

    Provider.provider = provider
    fixture = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    provider_srv = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    Thread(target=fixture.serve_forever, daemon=True).start()
    Thread(target=provider_srv.serve_forever, daemon=True).start()
    return fixture, provider_srv


def run_e2e_after_isolation(
    lock: dict[str, Any], state_root: Path, snapshot: Path
) -> dict[str, Any]:
    """Drive fixture, mock provider, and locked OpenCode after isolation."""
    provider = MockChatProvider(0)
    fixture_srv, provider_srv = start_loopback_servers(provider)
    try:
        fixture_port = int(fixture_srv.server_address[1])
        provider_port = int(provider_srv.server_address[1])
        provider.fixture_port = fixture_port
        mcp = mcp_config(
            mcp_argv(lock, state_root, fixture_port),
            dict(lock["browser_launch_policy"]["mcp_environment"]),
        )
        config = write_opencode_config(state_root, provider_port=provider_port, mcp=mcp)
        argv = opencode_e2e_argv(lock, state_root, snapshot)
        executable = Path(argv[0])
        if not executable.is_file():
            raise FileNotFoundError(argv[0])
        env = {
            "OPENCODE_CONFIG": str(config),
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
            "XDG_DATA_HOME": str(state_root / "tools" / "opencode-data"),
            "XDG_CONFIG_HOME": str(state_root / "tools" / "opencode-empty-config"),
            "HOME": str(state_root / "child-home"),
        }
        result = run_fenced(argv, cwd=str(snapshot), env=env, timeout_s=30.0)
        stdout = result.stdout.decode("utf-8", errors="replace")
        ok = (
            result.returncode == 0
            and e2e_success(stdout, provider.calls)
            and result.survivors == ()
        )
        cleanup_mcp_profile(state_root)
        return {"ok": ok, "stdout": stdout, "calls": provider.calls}
    finally:
        fixture_srv.shutdown()
        provider_srv.shutdown()


def run_opencode_probe_after_isolation(
    lock: dict[str, Any], state_root: Path, snapshot: Path
) -> dict[str, Any]:
    """Locked OpenCode real probe after isolation."""
    key = f"opencode-{PLATFORM}"
    executable = lock["agent_cli_executables"]["executables"][key].replace(
        "<state-root>", str(state_root)
    )
    if not Path(executable).is_file():
        raise FileNotFoundError(executable)
    config = write_opencode_probe_config(state_root, 9)
    argv = [
        executable,
        "run",
        "--pure",
        "--format",
        "json",
        "--model",
        "fixture/hermes-fixture",
        "--agent",
        "build",
        "--auto",
        "--dir",
        str(snapshot),
        "Reply with the single token HERMES_OPENCODE_PROBE_OK",
    ]
    env = {
        "OPENCODE_CONFIG": str(config),
        "OPENCODE_DISABLE_AUTOUPDATE": "1",
        "XDG_DATA_HOME": str(state_root / "tools" / "opencode-probe-data"),
        "XDG_CONFIG_HOME": str(state_root / "tools" / "opencode-empty-config"),
        "HOME": str(state_root / "child-home"),
    }
    result = run_fenced(argv, cwd=str(snapshot), env=env, timeout_s=30.0)
    classified = classify_opencode_events(
        result.stdout.decode("utf-8", errors="replace")
    )
    return {
        "outcome": classified.outcome,
        "final_text": classified.final_text,
        "survivors": result.survivors,
    }


def run_codex_probe_after_isolation(
    lock: dict[str, Any], state_root: Path, snapshot: Path
) -> dict[str, Any]:
    """Locked Codex real probe after isolation. Windows is rejected earlier."""
    key = f"codex-{PLATFORM}"
    executable = lock["agent_cli_executables"]["executables"][key].replace(
        "<state-root>", str(state_root)
    )
    argv = sanctioned_codex_argv(
        executable, str(snapshot), "Reply with the single token HERMES_CODEX_PROBE_OK"
    )
    if not Path(executable).is_file():
        raise FileNotFoundError(executable)
    result = run_fenced(argv, cwd=str(snapshot), timeout_s=30.0)
    classified = classify_codex_jsonl(result.stdout.decode("utf-8", errors="replace"))
    return {
        "outcome": classified.outcome,
        "final_text": classified.final_text,
        "survivors": result.survivors,
    }
