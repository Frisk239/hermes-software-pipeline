"""OpenCode Adapter: same RuntimeBrokerPort, model taken from the binding."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from hermes_pipeline.runtime_broker.ports import (
    RuntimeHandle,
    RuntimeLaunchRequest,
    RuntimeOutcome,
    RuntimeSignalReceipt,
    RuntimeSnapshot,
    RuntimeStatus,
)

_TIMEOUT_S = 10.0


@dataclass
class _Run:
    status: RuntimeStatus
    detail: str = ""
    final_text: str = ""


class OpenCodeAdapter:
    def __init__(self, executable: str | None = None, *, cwd: str = ".") -> None:
        self._executable = executable
        self._cwd = cwd
        self._runs: dict[str, _Run] = {}
        self.last_argv: list[str] = []
        self.spawned = False

    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        runtime_id = request.runtime_id
        if not self._may_launch():
            self._runs[runtime_id] = _Run(status="UNSUPPORTED", detail="error")
            return RuntimeHandle(runtime_id=runtime_id, status="UNSUPPORTED")
        argv = self._build_argv(request.model, request.prompt)
        self.last_argv = list(argv)
        try:
            completed = subprocess.run(
                argv,
                cwd=self._cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_TIMEOUT_S if not request.prompt else 120.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.spawned = True
            detail = (
                "timeout" if isinstance(exc, subprocess.TimeoutExpired) else "error"
            )
            self._runs[runtime_id] = _Run(status="FAILED", detail=detail)
            return RuntimeHandle(runtime_id=runtime_id, status="FAILED")
        self.spawned = True
        text = (completed.stdout or "").strip()
        self._runs[runtime_id] = _Run(status="COMPLETED", detail="ok", final_text=text)
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

    def _may_launch(self) -> bool:
        raw = self._executable
        if raw is None:
            return False
        return Path(raw).is_file()

    def _build_argv(self, model: str, prompt: str) -> list[str]:
        executable = self._executable
        if executable is None:
            return []
        prefix = (
            [sys.executable, executable]
            if executable.lower().endswith(".py")
            else [executable]
        )
        argv = [*prefix, "run", "--auto"]
        if model:
            argv.extend(["--model", model])
        if prompt:
            argv.append(prompt)
        return argv


__all__ = ["OpenCodeAdapter"]
