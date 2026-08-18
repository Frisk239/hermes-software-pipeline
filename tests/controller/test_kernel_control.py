"""KernelController pause / cancel / cleanup and crash-injection tests (slice 01-06)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import Actor, ControllerCommand
from hermes_pipeline.controller import KernelController, PipelineQuery
from hermes_pipeline.controller.transaction_store import (
    ControllerTransactionStore,
    LeaseError,
    StoreCounts,
)
from hermes_pipeline.persistence.kernel_memory import MemoryKernelStore
from hermes_pipeline.persistence.kernel_sqlite import SqliteKernelStore

_RECORDED_AT = "2026-01-01T00:00:00Z"
_NOW = 1_700_000_000
_TTL = 60


def _command(
    *,
    command_id: str = "cmd_01-06-a",
    command_type: str = "CONFIRM_REQUIREMENT",
    payload: dict[str, object] | None = None,
    expected_revision: int = 0,
    pipeline_id: str = "pl_01-06",
    workspace_id: str = "ws_01-06",
) -> ControllerCommand:
    if payload is None:
        payload = {"text": "need a login page"}
    return ControllerCommand(
        schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
        schema_version=FixedV1Integer(1),
        command_id=command_id,
        idempotency_key="slice-01-06-idem-key",
        workspace_id=workspace_id,
        project_id="prj_01-06",
        pipeline_id=pipeline_id,
        expected_revision=expected_revision,
        actor=Actor(
            principal_id="system",
            provider="SYSTEM",
            provider_actor_id="slice-01-06",
        ),
        ingress="SYSTEM_RECONCILER",
        command_type=command_type,
        payload=payload,
        correlation_id="corr-01-06",
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


def test_pause_rejects_submit_read_stays_open(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    assert controller.submit(_command()).status == "ACCEPTED"
    controller.pause()
    blocked = controller.submit(
        _command(command_id="cmd_01-06-blocked", pipeline_id="pl_01-06-b")
    )
    assert blocked.status == "REJECTED"
    assert blocked.error.code == "POLICY_REJECTED"
    assert blocked.error.message == "controller paused"
    leased = controller.submit_with_lease(
        _command(command_id="cmd_01-06-leased", pipeline_id="pl_01-06-c"),
        "holder-a",
        1,
        _NOW,
    )
    assert leased.status == "REJECTED"
    assert leased.error.code == "POLICY_REJECTED"
    assert leased.error.message == "controller paused"
    view = controller.read(
        PipelineQuery(pipeline_id="pl_01-06", workspace_id="ws_01-06")
    )
    assert view.status == "OPEN"
    assert view.revision == 1
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1, outbox=1)
    delivered = controller.replay("ws_01-06", "cmd_01-06-a")
    assert delivered.delivery_receipt_json is not None
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1, outbox=1)


def test_resume_restores_submit(store: ControllerTransactionStore) -> None:
    controller = _controller(store)
    assert controller.submit(_command()).status == "ACCEPTED"
    controller.pause()
    controller.resume()
    resumed = controller.submit(
        _command(command_id="cmd_01-06-resume", pipeline_id="pl_01-06-b")
    )
    assert resumed.status == "ACCEPTED"
    view = controller.read(
        PipelineQuery(pipeline_id="pl_01-06-b", workspace_id="ws_01-06")
    )
    assert view.status == "OPEN"
    assert store.counts() == StoreCounts(inbox=2, events=2, pipelines=2, outbox=2)


def test_cancel_releases_lease_state_unchanged(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    assert controller.submit(_command()).status == "ACCEPTED"
    lease = controller.acquire_lease("ws_01-06", "pl_01-06", "holder-a", _NOW)
    assert store.load_lease("ws_01-06", "pl_01-06") == lease
    store.delete_lease("", "pl_01-06")
    assert store.load_lease("ws_01-06", "pl_01-06") == lease
    with pytest.raises(LeaseError):
        controller.cancel("", "pl_01-06")
    assert store.load_lease("ws_01-06", "pl_01-06") == lease
    controller.cancel("ws_01-06", "pl_01-06")
    assert store.load_lease("ws_01-06", "pl_01-06") is None
    view = controller.read(
        PipelineQuery(pipeline_id="pl_01-06", workspace_id="ws_01-06")
    )
    assert view.status == "OPEN"
    assert view.revision == 1
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1, outbox=1)
    assert len(store.list_events("ws_01-06", "pl_01-06")) == 1


def test_cleanup_drops_expired_lease_state_unchanged(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    assert controller.submit(_command()).status == "ACCEPTED"
    live = controller.acquire_lease(
        "ws_01-06", "pl_01-06-live", "holder-live", _NOW, ttl_seconds=_TTL
    )
    expired = controller.acquire_lease(
        "ws_01-06", "pl_01-06", "holder-a", _NOW, ttl_seconds=_TTL
    )
    assert expired.expires_at == _NOW + _TTL
    controller.cleanup(_NOW)
    assert store.load_lease("ws_01-06", "pl_01-06") == expired
    assert store.load_lease("ws_01-06", "pl_01-06-live") == live
    controller.cleanup(_NOW + _TTL + 1)
    assert store.load_lease("ws_01-06", "pl_01-06") is None
    assert store.load_lease("ws_01-06", "pl_01-06-live") is None
    view = controller.read(
        PipelineQuery(pipeline_id="pl_01-06", workspace_id="ws_01-06")
    )
    assert view.status == "OPEN"
    assert view.revision == 1
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1, outbox=1)
    assert len(store.list_events("ws_01-06", "pl_01-06")) == 1


def test_commit_failure_leaves_no_residue(
    store: ControllerTransactionStore, tmp_path: Path
) -> None:
    assert isinstance(store, MemoryKernelStore | SqliteKernelStore)
    store.trip_commit_failure()
    receipt = _controller(store).submit(_command())
    assert receipt.status == "REJECTED"
    assert receipt.error.code == "INTERNAL_ERROR"
    assert receipt.error.message == "persistence unavailable"
    assert store.counts() == StoreCounts(inbox=0, events=0, pipelines=0, outbox=0)
    if isinstance(store, SqliteKernelStore):
        store.close()
        reopened = SqliteKernelStore(str(tmp_path / "kernel.db"))
        try:
            assert reopened.counts() == StoreCounts(
                inbox=0, events=0, pipelines=0, outbox=0
            )
        finally:
            reopened.close()
