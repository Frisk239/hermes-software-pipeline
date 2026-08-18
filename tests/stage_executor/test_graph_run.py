from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from hermes_pipeline.controller import KernelController, PipelineQuery
from hermes_pipeline.persistence.kernel_memory import MemoryKernelStore
from hermes_pipeline.persistence.kernel_sqlite import SqliteKernelStore
from hermes_pipeline.stage_executor.graph_run import GraphStageExecutor, command_id_for
from hermes_pipeline.stage_executor.ports import (
    ExecutionCancelRequest,
    ExecutionInput,
    ResumeInput,
    StageExecutorPort,
)

_SRC = Path(__file__).resolve().parents[2] / "src" / "hermes_pipeline"
_GRAPH_RUN = _SRC / "stage_executor" / "graph_run.py"
_FAKE = _SRC / "stage_executor" / "fake.py"
_FAKE_RUN = _SRC / "stage_executor" / "fake_run.py"
_RECORDED_AT = "2026-01-01T00:00:00Z"
_WS = "ws_stage"
_PL = "pl_stage"
_RUN = "run_01"
_FORBIDDEN_SPIKES = frozenset({"_graph_spike", "spike_controller", "_persistence_port"})


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(alias.name for alias in node.names)
    return names


@pytest.fixture
def memory_stage(
    tmp_path: Path,
) -> Iterator[tuple[GraphStageExecutor, MemoryKernelStore, KernelController]]:
    store = MemoryKernelStore()
    controller = KernelController(store, recorded_at=_RECORDED_AT)
    stage = GraphStageExecutor(
        controller,
        tmp_path / "ckpt.db",
        _WS,
        _PL,
    )
    try:
        yield stage, store, controller
    finally:
        stage.close()


def test_graph_stage_executor_is_a_stage_executor_port(
    memory_stage: tuple[GraphStageExecutor, MemoryKernelStore, KernelController],
) -> None:
    stage, _store, _controller = memory_stage
    assert isinstance(stage, StageExecutorPort)


def test_start_interrupts_without_controller_event(
    memory_stage: tuple[GraphStageExecutor, MemoryKernelStore, KernelController],
) -> None:
    stage, store, controller = memory_stage
    handle = stage.start(ExecutionInput(run_id=_RUN))
    assert handle.status == "PENDING"
    assert stage.inspect(_RUN).status == "PENDING"
    assert store.counts().events == 0
    assert controller.read(PipelineQuery(pipeline_id=_PL, workspace_id=_WS)).status == (
        "UNCONFIRMED"
    )


def test_resume_submits_once_then_replay_is_stable(
    memory_stage: tuple[GraphStageExecutor, MemoryKernelStore, KernelController],
) -> None:
    stage, store, controller = memory_stage
    stage.start(ExecutionInput(run_id=_RUN))
    handle = stage.resume(ResumeInput(run_id=_RUN))
    assert handle.status == "COMPLETED"
    assert stage.inspect(_RUN).status == "COMPLETED"
    assert store.counts().events == 1
    assert controller.read(PipelineQuery(pipeline_id=_PL, workspace_id=_WS)).status == (
        "OPEN"
    )
    inbox = store.find_inbox(_WS, command_id_for(_RUN))
    assert inbox is not None
    receipt = inbox.receipt_json
    replayed = stage.resume(ResumeInput(run_id=_RUN))
    assert replayed.status == "COMPLETED"
    assert store.counts().events == 1
    replay_inbox = store.find_inbox(_WS, command_id_for(_RUN))
    assert replay_inbox is not None
    assert replay_inbox.receipt_json == receipt
    stage.start(ExecutionInput(run_id=_RUN))
    assert store.counts().events == 1
    start_inbox = store.find_inbox(_WS, command_id_for(_RUN))
    assert start_inbox is not None
    assert start_inbox.receipt_json == receipt


def test_checkpoint_file_is_not_controller_sqlite(tmp_path: Path) -> None:
    controller_db = tmp_path / "controller.db"
    checkpoint_db = tmp_path / "ckpt.db"
    store = SqliteKernelStore(str(controller_db))
    controller = KernelController(store, recorded_at=_RECORDED_AT)
    stage = GraphStageExecutor(controller, checkpoint_db, _WS, _PL)
    try:
        stage.start(ExecutionInput(run_id=_RUN))
        assert checkpoint_db.is_file()
        assert controller_db.is_file()
        assert checkpoint_db.resolve() != controller_db.resolve()
    finally:
        stage.close()
        store.close()


def test_cancel_stops_resume(
    memory_stage: tuple[GraphStageExecutor, MemoryKernelStore, KernelController],
) -> None:
    stage, store, _controller = memory_stage
    stage.start(ExecutionInput(run_id=_RUN))
    receipt = stage.cancel(ExecutionCancelRequest(run_id=_RUN))
    assert receipt.status == "CANCELLED"
    assert stage.inspect(_RUN).status == "CANCELLED"
    resumed = stage.resume(ResumeInput(run_id=_RUN))
    assert resumed.status == "CANCELLED"
    assert store.counts().events == 0
    assert stage.inspect(_RUN).status == "CANCELLED"


def test_every_graph_invoke_carries_sync_durability(
    memory_stage: tuple[GraphStageExecutor, MemoryKernelStore, KernelController],
) -> None:
    stage, store, _controller = memory_stage
    calls: list[dict[str, object]] = []
    original = stage.graph.invoke

    def recording_invoke(*args: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return original(*args, **kwargs)

    stage.graph.invoke = recording_invoke
    stage.start(ExecutionInput(run_id=_RUN))
    stage.resume(ResumeInput(run_id=_RUN))
    stage.resume(ResumeInput(run_id=_RUN))
    assert len(calls) == 3
    assert all(kwargs.get("durability") == "sync" for kwargs in calls)
    assert store.counts().events == 1


def test_inspect_unknown_is_unsupported(
    memory_stage: tuple[GraphStageExecutor, MemoryKernelStore, KernelController],
) -> None:
    stage, _store, _controller = memory_stage
    assert stage.inspect("missing").status == "UNSUPPORTED"


def test_graph_run_does_not_import_spike_surfaces() -> None:
    imported = _imported_names(_GRAPH_RUN)
    assert imported.isdisjoint(_FORBIDDEN_SPIKES)
    joined = " ".join(imported)
    assert all(name not in joined for name in _FORBIDDEN_SPIKES)


def test_fakes_do_not_import_langgraph() -> None:
    for path in (_FAKE, _FAKE_RUN):
        imported = _imported_names(path)
        assert "langgraph" not in imported
        assert all("langgraph" not in name for name in imported)
