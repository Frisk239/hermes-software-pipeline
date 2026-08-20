from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

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

CodexOutcome = Literal["ok", "no_credential", "error", "timeout", "cancelled"]
_DANGEROUS = "--dangerously-bypass-approvals-and-sandbox"
_TIMEOUT_S = 10.0
_PROMPT_TIMEOUT_S = 120.0


@dataclass
class _Run:
    status: RuntimeStatus
    detail: str = ""
    final_text: str = ""
    cancel: threading.Event = field(default_factory=threading.Event)


@dataclass(frozen=True)
class _Classified:
    outcome: CodexOutcome
    final_text: str
    parsed: int = 0


class CodexAdapter:
    def __init__(
        self,
        executable: str | None = None,
        *,
        profile: CapabilityProfile | None = None,
        prompt: str = "ok",
        cwd: str = ".",
        sandbox: str = "read-only",
    ) -> None:
        self._executable = executable
        self._profile = profile
        self._prompt = prompt
        self._cwd = cwd
        self._sandbox = sandbox
        self._runs: dict[str, _Run] = {}
        self.last_argv: list[str] = []
        self.spawned = False

    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        runtime_id = request.runtime_id
        if not self._may_launch():
            missing = self._executable is None or not Path(self._executable).is_file()
            status: RuntimeStatus = "UNSUPPORTED" if missing else "FAILED"
            self._runs[runtime_id] = _Run(status=status, detail="error")
            return RuntimeHandle(runtime_id=runtime_id, status=status)
        prompt = request.prompt or self._prompt
        argv = self._build_argv(request.model, prompt)
        self.last_argv = list(argv)
        run = _Run(status="FAILED")
        self._runs[runtime_id] = run
        try:
            result = spawn_fenced(
                argv,
                cwd=self._cwd,
                timeout_s=_PROMPT_TIMEOUT_S if prompt else _TIMEOUT_S,
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
        classified = _classify(text)
        if classified.parsed == 0:
            run.detail = "error"
            run.final_text = text
            return RuntimeHandle(runtime_id=runtime_id, status="FAILED")
        status, detail = _status_for(classified.outcome)
        run.status = status
        run.detail = detail
        run.final_text = classified.final_text
        return RuntimeHandle(runtime_id=runtime_id, status=status)

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
        path = Path(raw)
        if not path.is_file():
            return False
        if self._profile is not None:
            return evaluate(
                self._profile, CapabilityRequest("EXECUTABLE", "codex")
            ).allowed
        return True

    def _build_argv(self, model: str = "", prompt: str = "") -> list[str]:
        executable = self._executable
        if executable is None:
            return []
        prefix = (
            [sys.executable, executable]
            if executable.lower().endswith(".py")
            else [executable]
        )
        argv = [
            *prefix,
            "exec",
            "--json",
            "--sandbox",
            self._sandbox,
            "-C",
            self._cwd,
        ]
        if model:
            argv.extend(["--model", model])
        argv.append(prompt or self._prompt)
        return [item for item in argv if item != _DANGEROUS]


def _classify(text: str) -> _Classified:
    outcome: CodexOutcome = "error"
    final = ""
    parsed = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        parsed += 1
        typed = cast(dict[str, Any], event)
        kind = str(typed.get("type") or typed.get("item") or "")
        error_obj = typed.get("error")
        payload = cast(dict[str, Any], error_obj) if isinstance(error_obj, dict) else {}
        message = str(payload.get("message", typed.get("message", "")))
        lowered = f"{kind} {message}".lower()
        if "auth" in message.lower() or "credential" in message.lower():
            outcome = "no_credential"
        elif "timeout" in lowered and outcome != "no_credential":
            outcome = "timeout"
        elif "cancel" in lowered and outcome not in {
            "no_credential",
            "timeout",
        }:
            outcome = "cancelled"
        text_value = typed.get("text")
        if isinstance(text_value, str) and text_value:
            final = text_value
        item = typed.get("item")
        if isinstance(item, dict):
            typed_item = cast(dict[str, Any], item)
            content = typed_item.get("content")
            if isinstance(content, list):
                for part in cast(list[object], content):
                    if not isinstance(part, dict):
                        continue
                    typed_part = cast(dict[str, Any], part)
                    if typed_part.get("type") == "output_text":
                        final = str(typed_part.get("text") or final)
        if outcome not in {"no_credential", "timeout", "cancelled"} and (
            kind.endswith("completed") or typed.get("status") == "completed"
        ):
            outcome = "ok"
    return _Classified(outcome=outcome, final_text=final, parsed=parsed)


def _status_for(outcome: CodexOutcome) -> tuple[RuntimeStatus, str]:
    if outcome == "ok":
        return "COMPLETED", "ok"
    if outcome == "cancelled":
        return "CANCELLED", "cancelled"
    if outcome == "no_credential":
        return "FAILED", "no_credential"
    if outcome == "timeout":
        return "FAILED", "timeout"
    return "FAILED", "error"


__all__ = ["CodexAdapter", "CodexOutcome"]
