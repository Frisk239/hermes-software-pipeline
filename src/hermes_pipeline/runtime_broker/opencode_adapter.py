"""OpenCode Adapter: same RuntimeBrokerPort, model taken from the binding."""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from hermes_pipeline.contracts.runtime import CapabilityProfile
from hermes_pipeline.runtime_broker._opencode import classify_opencode_events
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
_PROMPT_FILE = ".hermes-stage-prompt.txt"


@dataclass
class _Run:
    status: RuntimeStatus
    detail: str = ""
    final_text: str = ""
    cancel: threading.Event = field(default_factory=threading.Event)


class OpenCodeAdapter:
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
        self.spawned = False

    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        runtime_id = request.runtime_id
        if not self._may_launch():
            status: RuntimeStatus = (
                "FAILED" if self._profile is not None else "UNSUPPORTED"
            )
            if self._executable is None or not Path(self._executable).is_file():
                status = "UNSUPPORTED"
            self._runs[runtime_id] = _Run(status=status, detail="error")
            return RuntimeHandle(runtime_id=runtime_id, status=status)
        argv = self._build_argv(request.model, request.prompt)
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
            self.spawned = True
            run.detail = "error"
            return RuntimeHandle(runtime_id=runtime_id, status="FAILED")
        self.spawned = True
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
        if result.returncode != 0:
            run.detail = "error"
            run.final_text = text
            return RuntimeHandle(runtime_id=runtime_id, status="FAILED")
        classified = classify_opencode_events(text)
        if not classified.events:
            run.detail = "error"
            run.final_text = text
            return RuntimeHandle(runtime_id=runtime_id, status="FAILED")
        if classified.outcome != "idle":
            run.detail = classified.outcome
            run.final_text = classified.final_text or text
            return RuntimeHandle(runtime_id=runtime_id, status="FAILED")
        run.status = "COMPLETED"
        run.detail = "ok"
        run.final_text = classified.final_text or text
        return RuntimeHandle(runtime_id=runtime_id, status="COMPLETED")

    def signal(self, runtime_id: str) -> RuntimeSignalReceipt:
        run = self._runs.get(runtime_id)
        if run is None:
            return RuntimeSignalReceipt(ok=False, code="UNSUPPORTED")
        run.cancel.set()
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
        if not Path(raw).is_file():
            return False
        if self._profile is None:
            return True
        return evaluate(
            self._profile, CapabilityRequest("EXECUTABLE", "opencode")
        ).allowed

    def _build_argv(self, model: str, prompt: str) -> list[str]:
        executable = self._executable
        if executable is None:
            return []
        prefix = (
            [sys.executable, executable]
            if executable.lower().endswith(".py")
            else [executable]
        )
        folder = str(Path(self._cwd))
        argv = [*prefix, "run", "--auto", "--format", "json", "--dir", folder]
        if model:
            argv.extend(["--model", model])
        if prompt:
            (Path(self._cwd) / _PROMPT_FILE).write_text(prompt, encoding="utf-8")
            argv.append(_PROMPT_FILE)
        return argv


__all__ = ["OpenCodeAdapter"]
