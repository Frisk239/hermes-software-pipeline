"""KernelController read and rebuildable projection tests (slice 01-03)."""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from pathlib import Path

import pytest

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import Actor, ControllerCommand
from hermes_pipeline.controller import KernelController, PipelineQuery
from hermes_pipeline.controller.transaction_store import (
    ControllerTransactionStore,
    PersistenceError,
    StoreCounts,
)
from hermes_pipeline.persistence.kernel_memory import MemoryKernelStore
from hermes_pipeline.persistence.kernel_sqlite import SqliteKernelStore

_RECORDED_AT = "2026-01-01T00:00:00Z"


def _command(
    *,
    command_id: str = "cmd_01-03-a",
    command_type: str = "CONFIRM_REQUIREMENT",
    payload: dict[str, object] | None = None,
    expected_revision: int = 0,
    pipeline_id: str = "pl_01-03",
    workspace_id: str = "ws_01-03",
) -> ControllerCommand:
    if payload is None:
        payload = {"text": "need a login page"}
    return ControllerCommand(
        schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
        schema_version=FixedV1Integer(1),
        command_id=command_id,
        idempotency_key="slice-01-03-idem-key",
        workspace_id=workspace_id,
        project_id="prj_01-03",
        pipeline_id=pipeline_id,
        expected_revision=expected_revision,
        actor=Actor(
            principal_id="system",
            provider="SYSTEM",
            provider_actor_id="slice-01-03",
        ),
        ingress="SYSTEM_RECONCILER",
        command_type=command_type,
        payload=payload,
        correlation_id="corr-01-03",
        submitted_at=UtcTimestampRef(_RECORDED_AT),
    )


@pytest.fixture(params=["memory", "sqlite"])
def store(
    request: pytest.FixtureRequest, tmp_path: Path
) -> Iterator[ControllerTransactionStore]:
    item: ControllerTransactionStore
    if request.param == "memory":
        item = MemoryKernelStore()
    else:
        item = SqliteKernelStore(str(tmp_path / "kernel.db"))
    try:
        yield item
    finally:
        item.close()


def _controller(store: ControllerTransactionStore) -> KernelController:
    return KernelController(store, recorded_at=_RECORDED_AT)


def test_unsubmitted_pipeline_is_unconfirmed(
    store: ControllerTransactionStore,
) -> None:
    view = _controller(store).read(PipelineQuery(pipeline_id="pl_never"))
    assert view.pipeline_id == "pl_never"
    assert view.revision == 0
    assert view.status == "UNCONFIRMED"
    assert set(view.__dataclass_fields__) == {"pipeline_id", "revision", "status"}


def test_confirm_then_read_is_open(store: ControllerTransactionStore) -> None:
    controller = _controller(store)
    receipt = controller.submit(_command())
    assert receipt.status == "ACCEPTED"
    view = controller.read(
        PipelineQuery(pipeline_id="pl_01-03", workspace_id="ws_01-03")
    )
    assert view.status == "OPEN"
    assert view.revision == 1
    assert view.pipeline_id == "pl_01-03"
    blank = controller.read(PipelineQuery(pipeline_id="pl_01-03"))
    assert blank.status == "UNCONFIRMED"
    assert blank.revision == 0


def test_reject_then_read_is_rejected(store: ControllerTransactionStore) -> None:
    controller = _controller(store)
    receipt = controller.submit(
        _command(
            command_id="cmd_01-03-reject",
            command_type="REJECT_REQUIREMENT",
            payload={"reason": "out of scope"},
        )
    )
    assert receipt.status == "ACCEPTED"
    view = controller.read(
        PipelineQuery(pipeline_id="pl_01-03", workspace_id="ws_01-03")
    )
    assert view.status == "REJECTED"
    assert view.revision == 1


def test_restart_new_store_instance_still_open(tmp_path: Path) -> None:
    path = tmp_path / "kernel.db"
    store = SqliteKernelStore(str(path))
    try:
        receipt = KernelController(store, recorded_at=_RECORDED_AT).submit(_command())
        assert receipt.status == "ACCEPTED"
    finally:
        store.close()
    store2 = SqliteKernelStore(str(path))
    try:
        view = KernelController(store2, recorded_at=_RECORDED_AT).read(
            PipelineQuery(pipeline_id="pl_01-03", workspace_id="ws_01-03")
        )
        assert view.status == "OPEN"
        assert view.revision == 1
        assert store2.counts() == StoreCounts(inbox=1, events=1, pipelines=1, outbox=1)
    finally:
        store2.close()


def test_delete_projection_rebuild_matches_prior_view(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    receipt = controller.submit(_command())
    assert receipt.status == "ACCEPTED"
    query = PipelineQuery(pipeline_id="pl_01-03", workspace_id="ws_01-03")
    before = controller.read(query)
    events_before = store.counts().events
    store.delete_pipeline("ws_01-03", "pl_01-03")
    store.rebuild_pipeline("ws_01-03", "pl_01-03")
    after = controller.read(query)
    assert after == before
    assert after.status == "OPEN"
    assert after.revision == 1
    assert store.counts().events == events_before
    rebuilt = controller.rebuild(query)
    assert rebuilt == before
    assert store.counts().events == events_before


def test_empty_workspace_does_not_cross_read(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    first = controller.submit(
        _command(workspace_id="ws_01-03-a", pipeline_id="pl_same")
    )
    second = controller.submit(
        _command(
            command_id="cmd_01-03-b",
            workspace_id="ws_01-03-b",
            pipeline_id="pl_same",
            payload={"text": "other workspace"},
        )
    )
    assert first.status == "ACCEPTED"
    assert second.status == "ACCEPTED"
    assert (
        controller.read(
            PipelineQuery(pipeline_id="pl_same", workspace_id="ws_01-03-a")
        ).status
        == "OPEN"
    )
    assert (
        controller.read(
            PipelineQuery(pipeline_id="pl_same", workspace_id="ws_01-03-b")
        ).status
        == "OPEN"
    )
    assert controller.read(PipelineQuery(pipeline_id="pl_same")).status == "UNCONFIRMED"


def test_read_persistence_error_is_not_unconfirmed(
    store: ControllerTransactionStore,
) -> None:
    assert isinstance(store, MemoryKernelStore | SqliteKernelStore)
    controller = _controller(store)
    assert controller.submit(_command()).status == "ACCEPTED"
    store.trip_read_failure()
    with pytest.raises(PersistenceError):
        controller.read(PipelineQuery(pipeline_id="pl_01-03", workspace_id="ws_01-03"))


def test_read_has_no_rbac_parameters() -> None:
    parameters = inspect.signature(KernelController.read).parameters
    assert list(parameters) == ["self", "query"]
    assert "actor" not in parameters
    assert "role" not in parameters
