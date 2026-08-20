"""Generic host CLI spawn in the managed worktree."""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from hermes_pipeline.contracts.runtime import CapabilityProfile
from hermes_pipeline.runtime_broker.capability import CapabilityRequest, evaluate
from hermes_pipeline.runtime_broker.fence import decode_out, spawn_fenced
from hermes_pipeline.runtime_broker.ports import (
    RuntimeHandle,
    RuntimeLaunchRequest,
    RuntimeOutcome,
    RuntimeSignalReceipt,
    RuntimeSnapshot,
    RuntimeStatus,
)

_TIMEOUT_S = 10.0
_PROMPT_TIMEOUT_S = 300.0


@dataclass
class _Run:
    status: RuntimeStatus
    detail: str = ""
    final_text: str = ""
    cancel: threading.Event = field(default_factory=threading.Event)


class ProcessAdapter:
    def __init__(
        self,
        executable: str | None = None,
        *,
        cwd: str = ".",
        profile: CapabilityProfile | None = None,
    ) -> None:
        self._executable = executable
        self._cwd = cwd
        self._profile = profile
        self._runs: dict[str, _Run] = {}
        self.last_argv: list[str] = []

    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        runtime_id = request.runtime_id
        raw = self._executable
        if raw is None or not Path(raw).is_file():
            self._runs[runtime_id] = _Run(status="UNSUPPORTED", detail="error")
            return RuntimeHandle(runtime_id=runtime_id, status="UNSUPPORTED")
        if (
            self._profile is not None
            and not evaluate(
                self._profile, CapabilityRequest("EXECUTABLE", "process")
            ).allowed
        ):
            self._runs[runtime_id] = _Run(status="FAILED", detail="error")
            return RuntimeHandle(runtime_id=runtime_id, status="FAILED")
        argv = self._build_argv(request)
        self.last_argv = list(argv)
        run = _Run(status="FAILED")
        self._runs[runtime_id] = run
        try:
            result = spawn_fenced(
                argv,
                cwd=self._cwd,
                timeout_s=_TIMEOUT_S if not request.prompt else _PROMPT_TIMEOUT_S,
                cancel=run.cancel,
            )
        except OSError:
            run.detail = "error"
            return RuntimeHandle(runtime_id=runtime_id, status="FAILED")
        text = decode_out(result)
        if result.cancelled:
            run.status = "CANCELLED"
            run.detail = "cancelled"
            run.final_text = text
            return RuntimeHandle(runtime_id=runtime_id, status="CANCELLED")
        if result.timed_out:
            run.detail = "timeout"
            run.final_text = text
            return RuntimeHandle(runtime_id=runtime_id, status="FAILED")
        status: RuntimeStatus = "COMPLETED" if result.returncode == 0 else "FAILED"
        run.status = status
        run.detail = "ok" if status == "COMPLETED" else "error"
        run.final_text = text
        return RuntimeHandle(runtime_id=runtime_id, status=status)

    def signal(self, runtime_id: str) -> RuntimeSignalReceipt:
        run = self._runs.get(runtime_id)
        if run is None:
            return RuntimeSignalReceipt(ok=False, code="UNSUPPORTED")
        run.cancel.set()
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
            runtime_id=runtime_id,
            status=run.status,
            detail=run.detail,
            final_text=run.final_text,
        )

    def _build_argv(self, request: RuntimeLaunchRequest) -> list[str]:
        raw = self._executable
        if raw is None:
            return []
        prefix = [sys.executable, raw] if raw.lower().endswith(".py") else [raw]
        argv = list(prefix)
        if request.model:
            argv.extend(["--model", request.model])
        if request.prompt:
            argv.extend(["-p", request.prompt])
        return argv


__all__ = ["ProcessAdapter"]
