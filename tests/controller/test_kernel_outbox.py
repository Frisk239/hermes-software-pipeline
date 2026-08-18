"""KernelController outbox and idempotent replay tests (slice 01-04)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import Actor, ControllerCommand
from hermes_pipeline.controller import KernelController
from hermes_pipeline.controller.transaction_store import (
    ControllerTransactionStore,
    OutboxNotFound,
    StoreCounts,
)
from hermes_pipeline.persistence.kernel_memory import MemoryKernelStore
from hermes_pipeline.persistence.kernel_sqlite import SqliteKernelStore

_RECORDED_AT = "2026-01-01T00:00:00Z"


def _command(
    *,
    command_id: str = "cmd_01-04-a",
    command_type: str = "CONFIRM_REQUIREMENT",
    payload: dict[str, object] | None = None,
    expected_revision: int = 0,
    pipeline_id: str = "pl_01-04",
    workspace_id: str = "ws_01-04",
) -> ControllerCommand:
    if payload is None:
        payload = {"text": "need a login page"}
    return ControllerCommand(
        schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
        schema_version=FixedV1Integer(1),
        command_id=command_id,
        idempotency_key="slice-01-04-idem-key",
        workspace_id=workspace_id,
        project_id="prj_01-04",
        pipeline_id=pipeline_id,
        expected_revision=expected_revision,
        actor=Actor(
            principal_id="system",
            provider="SYSTEM",
            provider_actor_id="slice-01-04",
        ),
        ingress="SYSTEM_RECONCILER",
        command_type=command_type,
        payload=payload,
        correlation_id="corr-01-04",
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


def test_accept_confirm_writes_one_pending_outbox(
    store: ControllerTransactionStore,
) -> None:
    receipt = _controller(store).submit(_command())
    assert receipt.status == "ACCEPTED"
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1, outbox=1)
    record = store.find_outbox("ws_01-04", "cmd_01-04-a")
    assert record is not None
    assert record.workspace_id == "ws_01-04"
    assert record.command_id == "cmd_01-04-a"
    assert record.effect_type
    assert record.payload_json
    assert record.delivery_receipt_json is None
    pending = store.list_pending_outbox("ws_01-04")
    assert len(pending) == 1
    assert pending[0].command_id == "cmd_01-04-a"


def test_replay_records_receipt_without_new_event(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    assert controller.submit(_command()).status == "ACCEPTED"
    replayed = controller.replay("ws_01-04", "cmd_01-04-a")
    assert replayed.delivery_receipt_json
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1, outbox=1)
    assert store.list_pending_outbox("ws_01-04") == []


def test_second_replay_returns_same_receipt(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    assert controller.submit(_command()).status == "ACCEPTED"
    first = controller.replay("ws_01-04", "cmd_01-04-a")
    second = controller.replay("ws_01-04", "cmd_01-04-a")
    assert second.delivery_receipt_json == first.delivery_receipt_json
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1, outbox=1)


def test_restart_pending_replays_and_delivered_stays_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "kernel.db"
    store = SqliteKernelStore(str(path))
    try:
        receipt = KernelController(store, recorded_at=_RECORDED_AT).submit(_command())
        assert receipt.status == "ACCEPTED"
        assert store.list_pending_outbox("ws_01-04")
    finally:
        store.close()
    store2 = SqliteKernelStore(str(path))
    try:
        controller = KernelController(store2, recorded_at="2026-02-02T00:00:00Z")
        pending = store2.list_pending_outbox("ws_01-04")
        assert len(pending) == 1
        assert pending[0].delivery_receipt_json is None
        first = controller.replay("ws_01-04", "cmd_01-04-a")
        assert first.delivery_receipt_json
        assert store2.counts().events == 1
    finally:
        store2.close()
    store3 = SqliteKernelStore(str(path))
    try:
        again = KernelController(store3, recorded_at="2026-03-03T00:00:00Z").replay(
            "ws_01-04", "cmd_01-04-a"
        )
        assert again.delivery_receipt_json == first.delivery_receipt_json
        assert store3.counts() == StoreCounts(inbox=1, events=1, pipelines=1, outbox=1)
        assert store3.list_pending_outbox("ws_01-04") == []
    finally:
        store3.close()


def test_empty_workspace_does_not_cross_read(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    assert controller.submit(_command()).status == "ACCEPTED"
    assert store.list_pending_outbox("") == []
    assert store.find_outbox("", "cmd_01-04-a") is None
    assert store.list_pending_outbox("ws_other") == []
    with pytest.raises(OutboxNotFound):
        controller.replay("", "cmd_01-04-a")
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1, outbox=1)


def test_rejected_validation_does_not_write_outbox(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    empty = controller.submit(_command(payload={"text": "   "}))
    unsupported = controller.submit(
        _command(command_id="cmd_01-04-bad", command_type="CANCEL_PIPELINE")
    )
    assert empty.status == "REJECTED"
    assert unsupported.status == "REJECTED"
    assert store.counts() == StoreCounts(inbox=0, events=0, pipelines=0, outbox=0)
    with pytest.raises(OutboxNotFound):
        controller.replay("ws_01-04", "cmd_01-04-a")


def test_replay_missing_outbox_is_typed_failure(
    store: ControllerTransactionStore,
) -> None:
    with pytest.raises(OutboxNotFound):
        _controller(store).replay("ws_01-04", "cmd_missing")
