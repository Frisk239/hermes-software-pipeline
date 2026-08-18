from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

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

CodexOutcome = Literal["ok", "no_credential", "error", "timeout", "cancelled"]
_REAL_NAMES = frozenset({"codex", "codex.exe"})
_DANGEROUS = "--dangerously-bypass-approvals-and-sandbox"
_TIMEOUT_S = 10.0


@dataclass
class _Run:
    status: RuntimeStatus
    detail: str = ""
    final_text: str = ""


@dataclass(frozen=True)
class _Classified:
    outcome: CodexOutcome
    final_text: str


class CodexAdapter:
    def __init__(
        self,
        executable: str | None = None,
        *,
        profile: CapabilityProfile | None = None,
        prompt: str = "ok",
        cwd: str = ".",
    ) -> None:
        self._executable = executable
        self._profile = profile
        self._prompt = prompt
        self._cwd = cwd
        self._runs: dict[str, _Run] = {}
        self.last_argv: list[str] = []
        self.spawned = False

    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        runtime_id = request.runtime_id
        if not self._may_launch():
            self._runs[runtime_id] = _Run(status="UNSUPPORTED", detail="error")
            return RuntimeHandle(runtime_id=runtime_id, status="UNSUPPORTED")
        argv = self._build_argv(request.model)
        self.last_argv = list(argv)
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.spawned = True
            self._runs[runtime_id] = _Run(status="FAILED", detail="timeout")
            return RuntimeHandle(runtime_id=runtime_id, status="FAILED")
        self.spawned = True
        classified = _classify(completed.stdout)
        status, detail = _status_for(classified.outcome)
        self._runs[runtime_id] = _Run(
            status=status,
            detail=detail,
            final_text=classified.final_text,
        )
        return RuntimeHandle(runtime_id=runtime_id, status=status)

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
        path = Path(raw)
        if not path.is_file():
            return False
        if self._profile is not None:
            return evaluate(
                self._profile, CapabilityRequest("EXECUTABLE", "codex")
            ).allowed
        return path.name.lower() not in _REAL_NAMES

    def _build_argv(self, model: str = "") -> list[str]:
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
            "read-only",
            "-C",
            self._cwd,
        ]
        if model:
            argv.extend(["--model", model])
        argv.append(self._prompt)
        return [item for item in argv if item != _DANGEROUS]


def _classify(text: str) -> _Classified:
    outcome: CodexOutcome = "error"
    final = ""
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
    return _Classified(outcome=outcome, final_text=final)


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
