"""Generic host CLI spawn in the managed worktree."""

from __future__ import annotations

import subprocess
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


class ProcessAdapter:
    def __init__(self, executable: str | None = None, *, cwd: str = ".") -> None:
        self._executable = executable
        self._cwd = cwd
        self._runs: dict[str, _Run] = {}

    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        runtime_id = request.runtime_id
        raw = self._executable
        if raw is None or not Path(raw).is_file():
            self._runs[runtime_id] = _Run(status="UNSUPPORTED", detail="error")
            return RuntimeHandle(runtime_id=runtime_id, status="UNSUPPORTED")
        argv = [raw]
        if request.model:
            argv.extend(["--model", request.model])
        try:
            completed = subprocess.run(
                argv,
                cwd=self._cwd,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            detail = (
                "timeout" if isinstance(exc, subprocess.TimeoutExpired) else "error"
            )
            self._runs[runtime_id] = _Run(status="FAILED", detail=detail)
            return RuntimeHandle(runtime_id=runtime_id, status="FAILED")
        status: RuntimeStatus = "COMPLETED" if completed.returncode == 0 else "FAILED"
        self._runs[runtime_id] = _Run(
            status=status, detail="ok" if status == "COMPLETED" else "error"
        )
        return RuntimeHandle(runtime_id=runtime_id, status=status)

    def signal(self, runtime_id: str) -> RuntimeSignalReceipt:
        run = self._runs.get(runtime_id)
        if run is None:
            return RuntimeSignalReceipt(ok=False, code="UNSUPPORTED")
        run.status = "CANCELLED"
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
            runtime_id=runtime_id, status=run.status, detail=run.detail
        )


__all__ = ["ProcessAdapter"]
