"""Chrome DevTools MCP test runtime: fail-closed unless a fake MCP is injected."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Protocol, cast
from urllib.parse import urlparse

from hermes_pipeline.contracts.runtime import CapabilityProfile
from hermes_pipeline.runtime_broker.capability import CapabilityRequest, evaluate
from hermes_pipeline.runtime_broker.fence import cleaned_child_env
from hermes_pipeline.runtime_broker.ports import (
    RuntimeHandle,
    RuntimeLaunchRequest,
    RuntimeOutcome,
    RuntimeSignalReceipt,
    RuntimeSnapshot,
    RuntimeStatus,
)

_DRIVE_ORDER = (
    "chrome-devtools_navigate_page",
    "chrome-devtools_evaluate_script",
)
ALLOWED_TOOLS = frozenset(_DRIVE_ORDER)
_NAV = _DRIVE_ORDER[0]
_EVAL = _DRIVE_ORDER[1]
_EVAL_FN = "() => document.body ? document.body.innerText : ''"
_BLOCKED_NAMES = frozenset(
    {
        "chrome",
        "chrome.exe",
        "google-chrome",
        "google-chrome.exe",
        "node",
        "node.exe",
        "npm",
        "npm.cmd",
        "npm.exe",
        "npx",
        "npx.cmd",
        "npx.exe",
    }
)
_TIMEOUT_S = 10.0
_MCP_TIMEOUT_S = 30.0
_MCP_JS = (
    "tools/browser-runtime/project/node_modules/"
    "chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js"
)


class McpTransport(Protocol):
    def call(self, name: str, arguments: dict[str, object]) -> str: ...


@dataclass
class _Run:
    status: RuntimeStatus
    detail: str = ""
    final_text: str = ""


def closed_mcp_argv(state_root: Path, port: int) -> list[str] | None:
    root = state_root.resolve()
    if sys.platform == "win32":
        node = root / "tools/node/windows-x64/node-v22.23.2-win-x64/node.exe"
        chrome = (
            root
            / "tools/browser-runtime/chrome-for-testing/win64/chrome-win64/chrome.exe"
        )
    else:
        node = root / "tools/node/linux-x64/node-v22.23.2-linux-x64/bin/node"
        chrome = (
            root
            / "tools/browser-runtime/chrome-for-testing/linux64/chrome-linux64/chrome"
        )
    mcp = root / _MCP_JS
    for path in (node, chrome, mcp):
        try:
            resolved = path.resolve()
        except OSError:
            return None
        if not resolved.is_file():
            return None
        if not _under(root, resolved):
            return None
    return [
        str(node),
        str(mcp),
        "--headless",
        "--isolated",
        "--executable-path",
        str(chrome),
        "--allowed-url-pattern",
        f"http://127.0.0.1:{port}/*",
        "--no-usage-statistics",
        "--no-performance-crux",
    ]


def origin_port(origin: str) -> int:
    parsed = urlparse(origin)
    if parsed.port is not None:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    return 80


def _under(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


class ChromeMcpRuntime:
    def __init__(
        self,
        *,
        profile: CapabilityProfile | None = None,
        mcp: McpTransport | None = None,
        executable: str | None = None,
        state_root: Path | None = None,
    ) -> None:
        self._profile = profile
        self._mcp = mcp
        self._executable = executable
        self._state_root = state_root
        self._runs: dict[str, _Run] = {}
        self.calls: list[str] = []
        self.last_argv: list[str] = []
        self.spawned = False
        self._last_text = ""

    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        runtime_id = request.runtime_id
        if not self._browser_allowed():
            self._runs[runtime_id] = _Run(
                status="UNSUPPORTED", detail="browser not allowed"
            )
            return RuntimeHandle(runtime_id=runtime_id, status="UNSUPPORTED")
        if not self._has_transport():
            self._runs[runtime_id] = _Run(
                status="UNSUPPORTED", detail="no_official_checksum"
            )
            return RuntimeHandle(runtime_id=runtime_id, status="UNSUPPORTED")
        origin = request.origin or "http://127.0.0.1/"
        if self._mcp is None and self._executable is None:
            text = self._drive_closed(origin)
            if text is None:
                self._runs[runtime_id] = _Run(status="FAILED", detail="error")
                return RuntimeHandle(runtime_id=runtime_id, status="FAILED")
            self._runs[runtime_id] = _Run(
                status="COMPLETED", detail="ok", final_text=text
            )
            return RuntimeHandle(runtime_id=runtime_id, status="COMPLETED")
        for name in _DRIVE_ORDER:
            arguments: dict[str, object] = (
                {"url": origin} if name == _NAV else {"function": _EVAL_FN}
            )
            if not self.invoke(name, arguments):
                self._runs[runtime_id] = _Run(status="FAILED", detail="error")
                return RuntimeHandle(runtime_id=runtime_id, status="FAILED")
        self._runs[runtime_id] = _Run(
            status="COMPLETED", detail="ok", final_text=self._last_text
        )
        return RuntimeHandle(runtime_id=runtime_id, status="COMPLETED")

    def signal(self, runtime_id: str) -> RuntimeSignalReceipt:
        run = self._runs.get(runtime_id)
        if run is None:
            return RuntimeSignalReceipt(ok=False, code="UNSUPPORTED")
        run.status = "CANCELLED"
        run.detail = "cancelled"
        return RuntimeSignalReceipt(ok=True, code="CANCELLED")

    def inspect(self, runtime_id: str) -> RuntimeSnapshot:
        run = self._runs.get(runtime_id)
        if run is None:
            return RuntimeSnapshot(runtime_id=runtime_id, status="UNSUPPORTED")
        return RuntimeSnapshot(runtime_id=runtime_id, status=run.status)

    def collect(self, runtime_id: str) -> RuntimeOutcome:
        run = self._runs.get(runtime_id)
        if run is None:
            return RuntimeOutcome(runtime_id=runtime_id, status="UNSUPPORTED")
        return RuntimeOutcome(
            runtime_id=runtime_id,
            status=run.status,
            detail=run.detail,
            final_text=run.final_text,
        )

    def authorize(self, tool_name: str) -> bool:
        return tool_name in ALLOWED_TOOLS

    def invoke(
        self, tool_name: str, arguments: dict[str, object] | None = None
    ) -> bool:
        if tool_name not in ALLOWED_TOOLS:
            return False
        payload = arguments if arguments is not None else {}
        mcp = self._mcp
        if mcp is not None:
            self._last_text = mcp.call(tool_name, payload)
            self.calls.append(tool_name)
            return True
        if not self._may_use_executable():
            return False
        argv = self._build_argv(tool_name)
        self.last_argv = list(argv)
        try:
            subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.spawned = True
            return False
        self.spawned = True
        self.calls.append(tool_name)
        return True

    def _browser_allowed(self) -> bool:
        profile = self._profile
        if profile is None:
            return False
        return evaluate(
            profile, CapabilityRequest("BROWSER", "CHROME_DEVTOOLS_MCP")
        ).allowed

    def _has_transport(self) -> bool:
        return (
            self._mcp is not None
            or self._may_use_executable()
            or self._closed_argv(80) is not None
        )

    def _may_use_executable(self) -> bool:
        raw = self._executable
        if raw is None:
            return False
        path = Path(raw)
        if not path.is_file():
            return False
        return path.name.lower() not in _BLOCKED_NAMES

    def _closed_argv(self, port: int) -> list[str] | None:
        if self._state_root is None:
            return None
        return closed_mcp_argv(self._state_root, port)

    def _drive_closed(self, origin: str) -> str | None:
        argv = self._closed_argv(origin_port(origin))
        if argv is None:
            return None
        self.last_argv = list(argv)
        env = cleaned_child_env()
        env["CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS"] = "1"
        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=env,
            )
        except OSError:
            return None
        self.spawned = True
        try:
            _rpc(
                proc,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "hermes-pipeline", "version": "0.1.0"},
                },
            )
            _notify(proc, "notifications/initialized")
            _rpc(proc, "tools/call", {"name": _NAV, "arguments": {"url": origin}})
            self.calls.append(_NAV)
            result = _rpc(
                proc, "tools/call", {"name": _EVAL, "arguments": {"function": _EVAL_FN}}
            )
            self.calls.append(_EVAL)
            self._last_text = result
            return result
        except (OSError, RuntimeError, ValueError, TimeoutError):
            return None
        finally:
            proc.kill()
            proc.wait(timeout=5)

    def _build_argv(self, tool_name: str) -> list[str]:
        executable = self._executable
        if executable is None:
            return []
        prefix = (
            [sys.executable, executable]
            if executable.lower().endswith(".py")
            else [executable]
        )
        return [*prefix, tool_name]


def _rpc(proc: subprocess.Popen[bytes], method: str, params: dict[str, object]) -> str:
    if proc.stdin is None or proc.stdout is None:
        raise RuntimeError("stdio closed")
    message: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": method,
        "method": method,
        "params": params,
    }
    _write_frame(proc.stdin, message)
    reply = _read_frame(proc.stdout)
    if "error" in reply:
        raise RuntimeError("mcp error")
    result = reply.get("result", "")
    if isinstance(result, str):
        return result
    return json.dumps(result)


def _notify(proc: subprocess.Popen[bytes], method: str) -> None:
    if proc.stdin is None:
        raise RuntimeError("stdio closed")
    _write_frame(proc.stdin, {"jsonrpc": "2.0", "method": method})


def _write_frame(stream: IO[bytes], payload: dict[str, Any]) -> None:
    raw = json.dumps(payload).encode("utf-8")
    header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
    stream.write(header + raw)
    stream.flush()


def _read_frame(stream: IO[bytes]) -> dict[str, Any]:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            raise RuntimeError("eof")
        if line in (b"\r\n", b"\n"):
            if headers:
                break
            continue
        text = line.decode("ascii", errors="replace")
        key, _, value = text.partition(":")
        headers[key.strip().lower()] = value.strip()
    size = int(headers.get("content-length", "0"))
    body = stream.read(size)
    loaded = json.loads(body.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise RuntimeError("bad frame")
    return cast(dict[str, Any], loaded)


__all__ = [
    "ALLOWED_TOOLS",
    "ChromeMcpRuntime",
    "McpTransport",
    "closed_mcp_argv",
    "origin_port",
]
