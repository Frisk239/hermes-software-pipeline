"""LangGraph Stage Executor with a separate SQLite checkpointer.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, TypedDict, cast

# pyright: reportMissingTypeStubs=false
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import Actor, ControllerCommand
from hermes_pipeline.controller.ports import ControllerPort
from hermes_pipeline.stage_executor.ports import (
    CancelReceipt,
    ExecutionCancelRequest,
    ExecutionHandle,
    ExecutionInput,
    ExecutionSnapshot,
    ResumeInput,
    StageStatus,
)

_SUBMITTED_AT = "2026-01-01T00:00:00Z"
_CONFIRM_TEXT = "stage confirmed requirement"


class GraphState(TypedDict, total=False):
    run_id: str
    receipt_json: str | None


def command_id_for(run_id: str) -> str:
    return f"cmd_stage_{run_id}"


class GraphStageExecutor:
    def __init__(
        self,
        controller: ControllerPort,
        checkpoint_path: str | Path,
        workspace_id: str,
        pipeline_id: str,
        *,
        project_id: str = "prj_stage",
    ) -> None:
        self._controller = controller
        self._checkpoint_path = Path(checkpoint_path)
        self._workspace_id = workspace_id
        self._pipeline_id = pipeline_id
        self._project_id = project_id
        self._cancelled: set[str] = set()
        self._conn = sqlite3.connect(
            str(self._checkpoint_path), check_same_thread=False
        )
        self._checkpointer = SqliteSaver(self._conn)
        self._checkpointer.setup()
        self.graph: Any = self._compile()

    def start(self, execution_input: ExecutionInput) -> ExecutionHandle:
        run_id = execution_input.run_id
        existing = self._status(run_id)
        if existing != "UNSUPPORTED":
            return ExecutionHandle(run_id=run_id, status=existing)
        self._invoke({"run_id": run_id}, run_id)
        return ExecutionHandle(run_id=run_id, status=self._status(run_id))

    def resume(self, resume_input: ResumeInput) -> ExecutionHandle:
        run_id = resume_input.run_id
        status = self._status(run_id)
        if status == "CANCELLED":
            return ExecutionHandle(run_id=run_id, status="CANCELLED")
        if status == "UNSUPPORTED":
            return ExecutionHandle(run_id=run_id, status="UNSUPPORTED")
        if status == "COMPLETED":
            self._invoke({"run_id": run_id}, run_id)
            return ExecutionHandle(run_id=run_id, status=self._status(run_id))
        self._invoke(Command(resume="proceed"), run_id)
        return ExecutionHandle(run_id=run_id, status=self._status(run_id))

    def cancel(self, cancel_request: ExecutionCancelRequest) -> CancelReceipt:
        self._cancelled.add(cancel_request.run_id)
        return CancelReceipt(run_id=cancel_request.run_id, status="CANCELLED")

    def inspect(self, run_id: str) -> ExecutionSnapshot:
        return ExecutionSnapshot(run_id=run_id, status=self._status(run_id))

    def close(self) -> None:
        self._conn.close()

    def _compile(self) -> Any:
        controller = self._controller
        builder = self._command

        def gate_node(_state: GraphState) -> dict[str, object]:
            interrupt("awaiting-confirm")
            return {}

        def submit_node(state: GraphState) -> dict[str, object]:
            receipt = controller.submit(builder(str(state.get("run_id") or "")))
            return {"receipt_json": receipt.model_dump_json()}

        graph: Any = StateGraph(GraphState)
        graph.add_node("gate", gate_node)
        graph.add_node("submit", submit_node)
        graph.add_edge(START, "gate")
        graph.add_edge("gate", "submit")
        graph.add_edge("submit", END)
        return graph.compile(checkpointer=self._checkpointer)

    def _command(self, run_id: str) -> ControllerCommand:
        return ControllerCommand(
            schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
            schema_version=FixedV1Integer(1),
            command_id=command_id_for(run_id),
            idempotency_key=f"stage-graph-{run_id}-key",
            workspace_id=self._workspace_id,
            project_id=self._project_id,
            pipeline_id=self._pipeline_id,
            expected_revision=0,
            actor=Actor(
                principal_id="system",
                provider="SYSTEM",
                provider_actor_id="graph-stage-executor",
            ),
            ingress="SYSTEM_RECONCILER",
            command_type="CONFIRM_REQUIREMENT",
            payload={"text": _CONFIRM_TEXT},
            correlation_id=f"corr-{run_id}",
            submitted_at=UtcTimestampRef(_SUBMITTED_AT),
        )

    def _config(self, run_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": run_id}}

    def _invoke(self, payload: object, run_id: str) -> object:
        return self.graph.invoke(
            payload, config=self._config(run_id), durability="sync"
        )

    def _status(self, run_id: str) -> StageStatus:
        if run_id in self._cancelled:
            return "CANCELLED"
        state = self.graph.get_state(self._config(run_id))
        raw: object = state.values
        values = cast(dict[str, object], raw) if isinstance(raw, dict) else {}
        if values.get("receipt_json"):
            return "COMPLETED"
        if values.get("run_id") or state.next:
            return "PENDING"
        return "UNSUPPORTED"


__all__ = ["GraphStageExecutor", "command_id_for"]
