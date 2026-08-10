"""LangGraph checkpoint spike tests (slice-00-04, AC-11).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

A separate checkpoint database (physically distinct from the Controller
database), one graph thread per Execution Run namespace, and a
deterministic node that calls only ``ControllerCommandPort.submit`` with a
stable Controller command ID. Interrupt, resume, and replay resubmit the
stable command ID and prove exactly one accepted Event and one stable
receipt, including after checkpoint loss (``sync`` durability) and with an
absent or stale checkpoint. A regression test wraps ``invoke`` and proves
every invocation path (initial, resume, replay) carries
``durability="sync"`` explicitly (AC-11, rework 2 P1-2).

Authority boundaries: the Stage Executor and graph code never import the
private persistence port, a persistence Adapter, SQLAlchemy, or database
files (enforced here and by the import-boundary tests); the checkpoint
database cannot advance Controller state (Phase risk R-04).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from tests.spike.conftest import make_spike_command

from hermes_pipeline.controller.spike_controller import SpikeController
from hermes_pipeline.persistence.sqlite_spike import SqliteControllerStore
from hermes_pipeline.stage_executor._graph_spike import (
    STABLE_COMMAND_ID,
    build_counter_graph,
    run_graph,
)


def _checkpoint_connection(path: Path) -> sqlite3.Connection:
    """A checkpoint connection with sync durability (WAL + FULL).

    LangGraph's SqliteSaver writes checkpoints from its own background
    worker threads, so the connection must allow cross-thread use
    (``check_same_thread=False``); LangGraph serializes access itself.
    """
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    return conn


def _controller_for(database: Path) -> tuple[SqliteControllerStore, SpikeController]:
    store = SqliteControllerStore(database)
    controller = SpikeController(store, lambda: datetime(2026, 1, 1), lambda: "evt_lg")
    return store, controller


def _checkpoint_tables(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    return {str(row[0]) for row in rows}


def test_interrupt_resume_replay_produce_one_event_one_receipt(
    tmp_path: Path,
) -> None:
    """AC-11: interrupt, resume, and replay yield the original receipt and a
    single Event."""
    controller_db = tmp_path / "controller.db"
    checkpoint_db = tmp_path / "checkpoint.db"
    store, controller = _controller_for(controller_db)
    conn = _checkpoint_connection(checkpoint_db)
    graph = build_counter_graph(controller, conn)

    # First invocation: the graph submits the stable command and interrupts.
    state, submit_count = run_graph(graph, "run-1", thread_id="run-1")
    assert submit_count == 1
    assert "receipt_json" in state
    first_receipt = state["receipt_json"]
    assert store.audit().event_count == 1

    # Resume with the human decision: the stable command is resubmitted and
    # deduplicated.
    resumed, _ = run_graph(graph, "run-1", resume_value="proceed", thread_id="run-1")
    assert resumed["receipt_json"] == first_receipt
    assert store.audit().event_count == 1

    # Replay of the completed thread returns the same stable receipt.
    replayed, _ = run_graph(graph, "run-1", thread_id="run-1")
    assert replayed["receipt_json"] == first_receipt
    assert store.audit().event_count == 1
    assert store.audit().receipt_count == 1

    conn.close()
    store.close()


def test_every_graph_invoke_carries_sync_durability(
    tmp_path: Path,
) -> None:
    """AC-11 (rework 2, P1-2): every graph invoke — the initial invoke, the
    resume invoke, and the replay invoke — passes ``durability="sync"``
    explicitly. SQLite ``synchronous=FULL`` on the checkpoint connection
    alone is not checkpoint durability; LangGraph's sync durability persists
    checkpoint changes synchronously before the next step starts, which is
    what the checkpoint-loss evidence relies on. The wrapper below records
    every ``invoke`` call and asserts the parameter on each path."""
    controller_db = tmp_path / "controller.db"
    checkpoint_db = tmp_path / "checkpoint.db"
    store, controller = _controller_for(controller_db)
    conn = _checkpoint_connection(checkpoint_db)
    graph = build_counter_graph(controller, conn)

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    original_invoke = graph.invoke

    def recording_invoke(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return original_invoke(*args, **kwargs)

    graph.invoke = recording_invoke  # type: ignore[method-assign]

    # Initial invoke, resume invoke, and replay invoke.
    run_graph(graph, "run-durability", thread_id="run-durability")
    run_graph(
        graph, "run-durability", resume_value="proceed", thread_id="run-durability"
    )
    run_graph(graph, "run-durability", thread_id="run-durability")

    assert len(calls) == 3
    for _args, kwargs in calls:
        if kwargs.get("durability") != "sync":
            raise AssertionError("graph invoke did not request sync durability")
    assert store.audit().event_count == 1

    conn.close()
    store.close()


def test_checkpoint_loss_still_yields_single_event(
    tmp_path: Path,
) -> None:
    """AC-11: after checkpoint loss (sync durability), re-running the graph
    still yields a single Event and the stable receipt."""
    controller_db = tmp_path / "controller.db"
    checkpoint_db = tmp_path / "checkpoint.db"
    store, controller = _controller_for(controller_db)
    conn = _checkpoint_connection(checkpoint_db)
    graph = build_counter_graph(controller, conn)

    state, submit_count = run_graph(graph, "run-2", thread_id="run-2")
    assert submit_count == 1
    first_receipt = state["receipt_json"]
    assert store.audit().event_count == 1

    # Checkpoint loss: close, delete the checkpoint database, and rebuild.
    conn.close()
    checkpoint_db.unlink()
    conn = _checkpoint_connection(checkpoint_db)
    graph = build_counter_graph(controller, conn)
    restarted, submit_count = run_graph(graph, "run-2", thread_id="run-2-new")
    assert submit_count == 1
    assert restarted["receipt_json"] == first_receipt
    assert store.audit().event_count == 1
    assert store.audit().receipt_count == 1

    conn.close()
    store.close()


def test_absent_or_stale_checkpoint_cannot_duplicate_command(
    tmp_path: Path,
) -> None:
    """AC-11: with an absent or stale checkpoint, the graph cannot append a
    second Event for the stable command ID."""
    controller_db = tmp_path / "controller.db"
    checkpoint_db = tmp_path / "checkpoint.db"
    store, controller = _controller_for(controller_db)
    conn = _checkpoint_connection(checkpoint_db)
    graph = build_counter_graph(controller, conn)

    # Absent checkpoint: a brand-new thread namespace has no checkpoint.
    state, submit_count = run_graph(graph, "run-3", thread_id="run-3")
    assert submit_count == 1
    first_receipt = state["receipt_json"]
    assert store.audit().event_count == 1

    # Stale checkpoint: another thread (different Run namespace) re-runs the
    # same graph; the stable command still deduplicates.
    stale_state, stale_count = run_graph(graph, "run-4", thread_id="run-4")
    assert stale_count == 1
    assert stale_state["receipt_json"] == first_receipt
    assert store.audit().event_count == 1

    conn.close()
    store.close()


def test_checkpoint_database_cannot_advance_controller_state(
    tmp_path: Path,
) -> None:
    """AC-11: the checkpoint database has no authority over Controller
    state; it contains no Controller tables and never writes them."""
    controller_db = tmp_path / "controller.db"
    checkpoint_db = tmp_path / "checkpoint.db"
    store, controller = _controller_for(controller_db)
    conn = _checkpoint_connection(checkpoint_db)
    graph = build_counter_graph(controller, conn)
    run_graph(graph, "run-5", thread_id="run-5")
    assert store.audit().event_count == 1

    controller_tables = {
        "spike_inbox",
        "spike_events",
        "spike_projection",
        "spike_outbox",
        "spike_receipts",
        "spike_leases",
    }
    checkpoint_tables = _checkpoint_tables(checkpoint_db)
    assert not (controller_tables & checkpoint_tables)
    # The checkpoint file is a physically distinct database.
    assert checkpoint_db.resolve() != controller_db.resolve()

    conn.close()
    store.close()


def test_graph_reaches_state_only_through_command_port(
    tmp_path: Path,
) -> None:
    """AC-11 positive: the graph's business effect goes through
    ControllerCommandPort.submit with the stable command ID; the only
    accepted Event carries the stable command's identity."""
    controller_db = tmp_path / "controller.db"
    checkpoint_db = tmp_path / "checkpoint.db"
    store, controller = _controller_for(controller_db)
    conn = _checkpoint_connection(checkpoint_db)
    graph = build_counter_graph(controller, conn)
    run_graph(graph, "run-6", thread_id="run-6")
    audit = store.audit()
    assert audit.event_count == 1
    # The stable command ID is the one persisted in the inbox.
    stored = store.find_command(STABLE_COMMAND_ID)
    assert stored is not None
    conn.close()
    store.close()


def test_replay_that_would_append_second_event_fails(
    tmp_path: Path,
) -> None:
    """AC-11 negative: a replay that appends a second Event fails (the
    deduplication contract is asserted on the controller store)."""
    controller_db = tmp_path / "controller.db"
    checkpoint_db = tmp_path / "checkpoint.db"
    store, controller = _controller_for(controller_db)
    conn = _checkpoint_connection(checkpoint_db)
    graph = build_counter_graph(controller, conn)
    run_graph(graph, "run-7", thread_id="run-7")
    event_count_before = store.audit().event_count
    assert event_count_before == 1

    # A raw resubmission of the same command through the port cannot append
    # a second Event.
    receipt = controller.submit(make_spike_command(STABLE_COMMAND_ID))
    assert receipt.status == "ACCEPTED"
    assert store.audit().event_count == 1
    assert receipt.observed_revision == 1

    conn.close()
    store.close()
