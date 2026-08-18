"""Chrome DevTools MCP test runtime: fail-closed unless a fake MCP is injected."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from hermes_pipeline.contracts.runtime import CapabilityProfile
from hermes_pipeline.runtime_broker.capability import CapabilityRequest, evaluate
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


class McpTransport(Protocol):
    def call(self, name: str, arguments: dict[str, object]) -> str: ...


@dataclass
class _Run:
    status: RuntimeStatus
    detail: str = ""
    final_text: str = ""


class ChromeMcpRuntime:
    def __init__(
        self,
        *,
        profile: CapabilityProfile | None = None,
        mcp: McpTransport | None = None,
        executable: str | None = None,
    ) -> None:
        self._profile = profile
        self._mcp = mcp
        self._executable = executable
        self._runs: dict[str, _Run] = {}
        self.calls: list[str] = []
        self.last_argv: list[str] = []
        self.spawned = False

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
        for name in _DRIVE_ORDER:
            if not self.invoke(name):
                self._runs[runtime_id] = _Run(status="FAILED", detail="error")
                return RuntimeHandle(runtime_id=runtime_id, status="FAILED")
        self._runs[runtime_id] = _Run(status="COMPLETED", detail="ok")
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
            mcp.call(tool_name, payload)
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
        return self._mcp is not None or self._may_use_executable()

    def _may_use_executable(self) -> bool:
        raw = self._executable
        if raw is None:
            return False
        path = Path(raw)
        if not path.is_file():
            return False
        return path.name.lower() not in _BLOCKED_NAMES

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


__all__ = ["ALLOWED_TOOLS", "ChromeMcpRuntime", "McpTransport"]
