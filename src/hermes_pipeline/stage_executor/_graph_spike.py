"""LangGraph checkpoint spike graph (slice-00-04, AC-11).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Local feasibility evidence only (ADR-0023): a deterministic graph node that
calls **only** ``ControllerCommandPort.submit`` with a stable Controller
command ID. Interrupt, resume, and replay resubmit the stable command ID
and prove exactly one accepted Event and one stable receipt, including
after checkpoint loss and with an absent or stale checkpoint. Every graph
invocation (initial, resume, replay) passes ``durability="sync"``
explicitly (AC-11, rework 2 P1-2): checkpoint changes are persisted
synchronously before the next step starts, so the checkpoint-loss evidence
does not rely on SQLite ``synchronous=FULL`` alone.

Authority boundaries enforced by tests:

- the checkpoint database is a separate physical SQLite file, physically
  distinct from the Controller database, and never shares a transaction;
- one graph thread per Execution Run namespace;
- the graph code imports no private persistence port, no persistence
  Adapter, no SQLAlchemy, and no database files;
- the checkpoint database has no authority to advance Controller state; it
  cannot write Controller tables, proven by the checkpoint-authority test.
"""

from __future__ import annotations

import sqlite3
from typing import Any, TypedDict, cast

# langgraph ships no type stubs for its graph surface; the spike uses it as
# an untyped feasibility dependency (ADR-0023), so missing-stub reporting is
# disabled for this experimental module only.
# pyright: reportMissingTypeStubs=false
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import Actor, ControllerCommand
from hermes_pipeline.controller._command_port import ControllerCommandPort

#: Fixed spike command identity; the payload is the accepted delta=1.
STABLE_COMMAND_ID = "cmd_spike_langgraph_000000"
SPIKE_DELTA = 1
SPIKE_WORKSPACE = "ws_spike"
SPIKE_PROJECT = "prj_spike"
SPIKE_PIPELINE = "pl_spike"
SPIKE_ACTOR = Actor(
    principal_id="system",
    provider="SYSTEM",
    provider_actor_id="spike-stage-executor",
)


class GraphState(TypedDict, total=False):
    """One Execution Run's graph state: stable identity and receipts."""

    run_namespace: str
    command_id: str
    receipt_json: str | None
    submit_count: int
    counter_value: int
    counter_revision: int
    gate_decision: str


def build_stable_command(
    run_namespace: str, expected_revision: int
) -> ControllerCommand:
    """One deterministic Controller command with a stable identity.

    The command ID is fixed per graph (the stable Controller command ID);
    the idempotency key and correlation id vary by Run namespace only and
    do not affect command identity.
    """
    return ControllerCommand(
        schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
        schema_version=FixedV1Integer(1),
        command_id=STABLE_COMMAND_ID,
        idempotency_key=f"spike-langgraph-{run_namespace}-key-0000",
        workspace_id=SPIKE_WORKSPACE,
        project_id=SPIKE_PROJECT,
        pipeline_id=SPIKE_PIPELINE,
        expected_revision=expected_revision,
        actor=SPIKE_ACTOR,
        ingress="SYSTEM_RECONCILER",
        command_type="COUNTER_INCREMENT",
        payload={"delta": SPIKE_DELTA},
        correlation_id=f"corr-{run_namespace}",
        submitted_at=UtcTimestampRef("2026-01-01T00:00:00Z"),
    )


def _submit_node_factory(controller: ControllerCommandPort) -> Any:
    """Deterministic node factory; the node calls only the port."""

    def submit_node(state: GraphState) -> dict[str, object]:
        run_namespace = state.get("run_namespace", "run-default")
        expected = state.get("counter_revision", 0)
        receipt = controller.submit(build_stable_command(run_namespace, expected))
        payload = cast(dict[str, object], receipt.model_dump())
        revision = int(cast(int, payload.get("observed_revision", 0)))
        return {
            "receipt_json": receipt.model_dump_json(),
            "submit_count": int(state.get("submit_count", 0)) + 1,
            "counter_revision": revision,
            "counter_value": revision,
        }

    return submit_node


def _confirm_node_factory(controller: ControllerCommandPort) -> Any:
    """Interrupt/resume gate node.

    The node interrupts for a human decision; the resume path resubmits the
    identical stable command through ``ControllerCommandPort.submit``.
    Controller deduplication must return the original receipt and append no
    second Event (AC-11 replay matrix).
    """

    def confirm_node(state: GraphState) -> dict[str, object]:
        decision: str = interrupt("proceed?")
        run_namespace = state.get("run_namespace", "run-default")
        receipt = controller.submit(build_stable_command(run_namespace, 0))
        return {"gate_decision": decision, "receipt_json": receipt.model_dump_json()}

    return confirm_node


def build_counter_graph(
    controller: ControllerCommandPort, checkpoint_conn: sqlite3.Connection
) -> Any:
    """Build the compiled spike graph with one SqliteSaver checkpoint store.

    ``checkpoint_conn`` is a connection to the separate checkpoint database;
    the graph never touches the Controller database. The graph surface is
    untyped (langgraph ships no stubs), so it is handled as ``Any`` here.
    """
    checkpointer = SqliteSaver(checkpoint_conn)
    graph: Any = StateGraph(GraphState)
    graph.add_node("submit", _submit_node_factory(controller))
    graph.add_node("confirm", _confirm_node_factory(controller))
    graph.add_edge(START, "submit")
    graph.add_edge("submit", "confirm")
    graph.add_edge("confirm", END)
    return graph.compile(checkpointer=checkpointer)


def run_graph(
    compiled: Any,
    run_namespace: str,
    *,
    resume_value: str | None = None,
    thread_id: str,
) -> tuple[dict[str, Any], int]:
    """Invoke (or resume) the graph once and return (final state, submit_count).

    ``thread_id`` is the per-Run namespace thread identity; ``resume_value``
    is the human decision delivered by ``Command(resume=...)``.

    Every invocation — the initial invoke, the resume invoke, and any replay
    invoke — explicitly passes ``durability="sync"`` (LangGraph 1.2.10
    keyword-only parameter) so checkpoint changes are persisted
    synchronously before the next step starts. SQLite ``synchronous=FULL``
    on the checkpoint connection alone is not checkpoint durability (AC-11,
    rework 2 P1-2); the sync-durability regression test wraps ``invoke`` and
    asserts the parameter on every call path.
    """
    config: dict[str, dict[str, str]] = {"configurable": {"thread_id": thread_id}}
    initial: dict[str, str] = {
        "run_namespace": run_namespace,
        "command_id": STABLE_COMMAND_ID,
    }
    if resume_value is None:
        result = compiled.invoke(initial, config=config, durability="sync")
    else:
        result = compiled.invoke(
            Command(resume=resume_value), config=config, durability="sync"
        )
    submit_count = int(result.get("submit_count", 0)) if result else 0
    return result, submit_count


__all__ = [
    "SPIKE_DELTA",
    "STABLE_COMMAND_ID",
    "GraphState",
    "build_counter_graph",
    "build_stable_command",
    "run_graph",
]
