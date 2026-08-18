"""KernelController submit tests (slice 01-02)."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import Actor, ControllerCommand
from hermes_pipeline.controller import KernelController, PipelineQuery
from hermes_pipeline.controller.ports import ControllerPort
from hermes_pipeline.controller.transaction_store import (
    ControllerTransactionStore,
    StoreCounts,
)
from hermes_pipeline.persistence.kernel_memory import MemoryKernelStore
from hermes_pipeline.persistence.kernel_sqlite import SqliteKernelStore

_SRC = Path(__file__).resolve().parents[2] / "src" / "hermes_pipeline"
_KERNEL = _SRC / "controller" / "kernel.py"
_PORT = _SRC / "controller" / "transaction_store.py"
_FORBIDDEN = frozenset(
    {
        "sqlalchemy",
        "sqlite3",
        "CounterSpike",
        "counter_spike",
        "spike_controller",
        "sqlite_spike",
        "_persistence_port",
    }
)
_RECORDED_AT = "2026-01-01T00:00:00Z"
_EVENT_ID = re.compile(r"^evt_[A-Za-z0-9_-]+$")


def _command(
    *,
    command_id: str = "cmd_01-02-a",
    command_type: str = "CONFIRM_REQUIREMENT",
    payload: dict[str, object] | None = None,
    expected_revision: int = 0,
    pipeline_id: str = "pl_01-02",
    workspace_id: str = "ws_01-02",
    correlation_id: str = "corr-01-02",
    idempotency_key: str = "slice-01-02-idem-key",
) -> ControllerCommand:
    if payload is None:
        payload = {"text": "need a login page"}
    return ControllerCommand(
        schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
        schema_version=FixedV1Integer(1),
        command_id=command_id,
        idempotency_key=idempotency_key,
        workspace_id=workspace_id,
        project_id="prj_01-02",
        pipeline_id=pipeline_id,
        expected_revision=expected_revision,
        actor=Actor(
            principal_id="system",
            provider="SYSTEM",
            provider_actor_id="slice-01-02",
        ),
        ingress="SYSTEM_RECONCILER",
        command_type=command_type,
        payload=payload,
        correlation_id=correlation_id,
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


def test_kernel_controller_is_a_controller_port(
    store: ControllerTransactionStore,
) -> None:
    assert isinstance(_controller(store), ControllerPort)


def test_accept_confirm_persists_inbox_event_and_open_pipeline(
    store: ControllerTransactionStore,
) -> None:
    receipt = _controller(store).submit(_command())
    assert receipt.status == "ACCEPTED"
    assert receipt.observed_revision == 1
    assert len(receipt.event_ids) == 1
    assert _EVENT_ID.match(receipt.event_ids[0])
    assert receipt.error.message == ""
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1)
    snapshot = store.load_pipeline("ws_01-02", "pl_01-02")
    assert snapshot is not None
    assert snapshot.status == "OPEN"
    assert snapshot.revision == 1
    assert snapshot.text == "need a login page"


def test_accept_reject_persists_rejected_pipeline(
    store: ControllerTransactionStore,
) -> None:
    receipt = _controller(store).submit(
        _command(
            command_id="cmd_01-02-reject",
            command_type="REJECT_REQUIREMENT",
            payload={"reason": "out of scope"},
        )
    )
    assert receipt.status == "ACCEPTED"
    assert receipt.observed_revision == 1
    snapshot = store.load_pipeline("ws_01-02", "pl_01-02")
    assert snapshot is not None
    assert snapshot.status == "REJECTED"
    assert snapshot.revision == 1
    assert snapshot.text == ""


def test_empty_requirement_is_rejected_without_durable_write(
    store: ControllerTransactionStore,
) -> None:
    receipt = _controller(store).submit(_command(payload={"text": "   "}))
    assert receipt.status == "REJECTED"
    assert receipt.error.code == "VALIDATION_ERROR"
    assert receipt.error.message == "empty requirement"
    assert receipt.error.retryable is False
    assert store.counts() == StoreCounts(inbox=0, events=0, pipelines=0)


def test_invalid_transition_is_rejected_without_second_event(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    first = controller.submit(_command())
    assert first.status == "ACCEPTED"
    second = controller.submit(
        _command(
            command_id="cmd_01-02-again",
            payload={"text": "again"},
            expected_revision=1,
        )
    )
    assert second.status == "REJECTED"
    assert second.error.code == "VALIDATION_ERROR"
    assert second.error.message == "invalid transition"
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1)


def test_unsupported_command_type_is_rejected_without_write(
    store: ControllerTransactionStore,
) -> None:
    receipt = _controller(store).submit(
        _command(command_type="CANCEL_PIPELINE", payload={"stage": "prd"})
    )
    assert receipt.status == "REJECTED"
    assert receipt.error.code == "VALIDATION_ERROR"
    assert receipt.error.message == "unsupported command"
    assert store.counts() == StoreCounts(inbox=0, events=0, pipelines=0)


def test_missing_or_wrong_payload_type_is_unsupported(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    missing = controller.submit(_command(payload={"reason": "x"}))
    wrong = controller.submit(
        _command(command_id="cmd_01-02-wrong", payload={"text": 1})
    )
    reject_missing = controller.submit(
        _command(
            command_id="cmd_01-02-rej-miss",
            command_type="REJECT_REQUIREMENT",
            payload={"text": "x"},
        )
    )
    assert missing.error.message == "unsupported command"
    assert wrong.error.message == "unsupported command"
    assert reject_missing.error.message == "unsupported command"
    assert store.counts() == StoreCounts(inbox=0, events=0, pipelines=0)


def test_identity_conflict_same_id_different_payload(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    first = controller.submit(_command())
    assert first.status == "ACCEPTED"
    conflict = controller.submit(_command(payload={"text": "a different requirement"}))
    assert conflict.status == "CONFLICT"
    assert conflict.error.code == "CONFLICT"
    assert conflict.error.message == "command identity conflict"
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1)


def test_identity_conflict_same_id_different_command_field(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    first = controller.submit(_command())
    assert first.status == "ACCEPTED"
    conflict = controller.submit(_command(correlation_id="corr-other"))
    assert conflict.status == "CONFLICT"
    assert conflict.error.code == "CONFLICT"
    assert conflict.error.message == "command identity conflict"
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1)


def test_revision_conflict_before_apply(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    first = controller.submit(_command())
    assert first.status == "ACCEPTED"
    conflict = controller.submit(
        _command(
            command_id="cmd_01-02-stale",
            payload={"text": "stale"},
            expected_revision=0,
        )
    )
    assert conflict.status == "CONFLICT"
    assert conflict.error.code == "CONFLICT"
    assert conflict.error.message == "expected revision conflict"
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1)


def test_same_identity_returns_stored_receipt_not_deduplicated(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    first = controller.submit(_command())
    second = controller.submit(_command())
    assert second == first
    assert second.status == "ACCEPTED"
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1)


def test_restart_duplicate_returns_stored_receipt(tmp_path: Path) -> None:
    path = tmp_path / "kernel.db"
    store = SqliteKernelStore(str(path))
    try:
        first = KernelController(store, recorded_at=_RECORDED_AT).submit(_command())
        assert first.status == "ACCEPTED"
    finally:
        store.close()
    store2 = SqliteKernelStore(str(path))
    try:
        replayed = KernelController(store2, recorded_at=_RECORDED_AT).submit(_command())
        assert replayed == first
        assert replayed.status == "ACCEPTED"
        assert store2.counts() == StoreCounts(inbox=1, events=1, pipelines=1)
    finally:
        store2.close()


def test_cross_workspace_same_command_id_both_accepted(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    first = controller.submit(
        _command(workspace_id="ws_01-02-a", pipeline_id="pl_01-02-a")
    )
    second = controller.submit(
        _command(workspace_id="ws_01-02-b", pipeline_id="pl_01-02-b")
    )
    assert first.status == "ACCEPTED"
    assert second.status == "ACCEPTED"
    assert store.counts() == StoreCounts(inbox=2, events=2, pipelines=2)


def test_persistence_unavailable_rolls_back(
    store: ControllerTransactionStore,
) -> None:
    assert isinstance(store, MemoryKernelStore | SqliteKernelStore)
    store.trip_commit_failure()
    receipt = _controller(store).submit(_command())
    assert receipt.status == "REJECTED"
    assert receipt.error.code == "INTERNAL_ERROR"
    assert receipt.error.message == "persistence unavailable"
    assert receipt.error.retryable is True
    assert "sql" not in receipt.error.message.lower()
    assert "\\" not in receipt.error.message
    assert "/" not in receipt.error.message
    assert store.counts() == StoreCounts(inbox=0, events=0, pipelines=0)


def test_read_returns_unknown_fixture(store: ControllerTransactionStore) -> None:
    view = _controller(store).read(PipelineQuery(pipeline_id="pl_01-02"))
    assert view.pipeline_id == "pl_01-02"
    assert view.revision == 0
    assert view.status == "UNKNOWN"


def test_kernel_import_boundary() -> None:
    violations: list[str] = []
    for path in (_KERNEL, _PORT):
        source = path.read_text(encoding="utf-8")
        assert "datetime.now" not in source
        tree = ast.parse(source)
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module, *[alias.name for alias in node.names]]
            lineno = getattr(node, "lineno", 0)
            for name in names:
                if any(part in _FORBIDDEN for part in name.split(".")):
                    violations.append(f"{path.name}:{lineno}:{name}")
    assert violations == [], f"forbidden kernel imports: {violations}"
