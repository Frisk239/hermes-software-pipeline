"""KernelController lease and fencing tests (slice 01-05)."""

from __future__ import annotations

import ast
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

_SRC = Path(__file__).resolve().parents[2] / "src" / "hermes_pipeline"
_KERNEL = _SRC / "controller" / "kernel.py"
_PORT = _SRC / "controller" / "transaction_store.py"
_FORBIDDEN = frozenset(
    {
        "sqlalchemy",
        "sqlite3",
        "os",
        "pathlib",
        "leases",
        "sqlite_spike",
        "_persistence_port",
        "spike_controller",
    }
)
_RECORDED_AT = "2026-01-01T00:00:00Z"
_NOW = 1_700_000_000
_TTL = 60


def _command(
    *,
    command_id: str = "cmd_01-05-a",
    command_type: str = "CONFIRM_REQUIREMENT",
    payload: dict[str, object] | None = None,
    expected_revision: int = 0,
    pipeline_id: str = "pl_01-05",
    workspace_id: str = "ws_01-05",
) -> ControllerCommand:
    if payload is None:
        payload = {"text": "need a login page"}
    return ControllerCommand(
        schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
        schema_version=FixedV1Integer(1),
        command_id=command_id,
        idempotency_key="slice-01-05-idem-key",
        workspace_id=workspace_id,
        project_id="prj_01-05",
        pipeline_id=pipeline_id,
        expected_revision=expected_revision,
        actor=Actor(
            principal_id="system",
            provider="SYSTEM",
            provider_actor_id="slice-01-05",
        ),
        ingress="SYSTEM_RECONCILER",
        command_type=command_type,
        payload=payload,
        correlation_id="corr-01-05",
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


def test_acquire_starts_at_generation_one(store: ControllerTransactionStore) -> None:
    lease = _controller(store).acquire_lease(
        "ws_01-05", "pl_01-05", "holder-a", _NOW, ttl_seconds=_TTL
    )
    assert lease.generation == 1
    assert lease.holder == "holder-a"
    assert lease.attempt_id.startswith("att_")
    assert lease.run_id.startswith("run_")
    assert lease.expires_at == _NOW + _TTL
    loaded = store.load_lease("ws_01-05", "pl_01-05")
    assert loaded == lease
    assert store.load_lease("", "pl_01-05") is None


def test_current_generation_confirm_opens_pipeline(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    lease = controller.acquire_lease("ws_01-05", "pl_01-05", "holder-a", _NOW)
    receipt = controller.submit_with_lease(
        _command(), "holder-a", lease.generation, _NOW
    )
    assert receipt.status == "ACCEPTED"
    view = controller.read(
        PipelineQuery(pipeline_id="pl_01-05", workspace_id="ws_01-05")
    )
    assert view.status == "OPEN"
    assert view.revision == 1
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1, outbox=1)


def test_takeover_fences_stale_generation(store: ControllerTransactionStore) -> None:
    controller = _controller(store)
    first = controller.acquire_lease("ws_01-05", "pl_01-05", "holder-a", _NOW)
    assert (
        controller.submit_with_lease(
            _command(), "holder-a", first.generation, _NOW
        ).status
        == "ACCEPTED"
    )
    second = controller.acquire_lease("ws_01-05", "pl_01-05", "holder-b", _NOW)
    assert second.generation == 2
    assert second.holder == "holder-b"
    stale = controller.submit_with_lease(
        _command(
            command_id="cmd_01-05-reject",
            command_type="REJECT_REQUIREMENT",
            payload={"reason": "too late"},
            expected_revision=1,
        ),
        "holder-a",
        first.generation,
        _NOW,
    )
    assert stale.status == "CONFLICT"
    assert stale.error.code == "LEASE_STALE"
    view = controller.read(
        PipelineQuery(pipeline_id="pl_01-05", workspace_id="ws_01-05")
    )
    assert view.status == "OPEN"
    assert view.revision == 1
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1, outbox=1)
    assert store.find_inbox("ws_01-05", "cmd_01-05-reject") is None


def test_expired_generation_cannot_change_state(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    lease = controller.acquire_lease(
        "ws_01-05", "pl_01-05", "holder-a", _NOW, ttl_seconds=_TTL
    )
    assert (
        controller.submit_with_lease(
            _command(), "holder-a", lease.generation, _NOW
        ).status
        == "ACCEPTED"
    )
    late = controller.submit_with_lease(
        _command(
            command_id="cmd_01-05-late",
            command_type="REJECT_REQUIREMENT",
            payload={"reason": "expired"},
            expected_revision=1,
        ),
        "holder-a",
        lease.generation,
        _NOW + _TTL + 1,
    )
    assert late.status == "CONFLICT"
    assert late.error.code == "LEASE_STALE"
    view = controller.read(
        PipelineQuery(pipeline_id="pl_01-05", workspace_id="ws_01-05")
    )
    assert view.status == "OPEN"
    assert view.revision == 1
    assert store.counts() == StoreCounts(inbox=1, events=1, pipelines=1, outbox=1)
    assert store.find_inbox("ws_01-05", "cmd_01-05-late") is None


def test_forged_future_generation_is_rejected(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    lease = controller.acquire_lease("ws_01-05", "pl_01-05", "holder-a", _NOW)
    forged = controller.submit_with_lease(
        _command(), "holder-a", lease.generation + 1, _NOW
    )
    assert forged.status == "CONFLICT"
    assert forged.error.code == "LEASE_STALE"
    view = controller.read(
        PipelineQuery(pipeline_id="pl_01-05", workspace_id="ws_01-05")
    )
    assert view.status == "UNCONFIRMED"
    assert view.revision == 0
    assert store.counts() == StoreCounts(inbox=0, events=0, pipelines=0, outbox=0)
    assert store.find_inbox("ws_01-05", "cmd_01-05-a") is None


def test_heartbeat_renews_only_current_same_holder(
    store: ControllerTransactionStore,
) -> None:
    controller = _controller(store)
    first = controller.acquire_lease(
        "ws_01-05", "pl_01-05", "holder-a", _NOW, ttl_seconds=_TTL
    )
    renewed = controller.heartbeat_lease(
        "ws_01-05",
        "pl_01-05",
        "holder-a",
        first.generation,
        _NOW + 10,
        ttl_seconds=_TTL,
    )
    assert renewed.generation == first.generation
    assert renewed.holder == "holder-a"
    assert renewed.expires_at == _NOW + 10 + _TTL
    second = controller.acquire_lease("ws_01-05", "pl_01-05", "holder-b", _NOW + 20)
    with pytest.raises(LeaseError):
        controller.heartbeat_lease(
            "ws_01-05",
            "pl_01-05",
            "holder-a",
            first.generation,
            _NOW + 20,
            ttl_seconds=_TTL,
        )
    with pytest.raises(LeaseError):
        controller.heartbeat_lease(
            "ws_01-05",
            "pl_01-05",
            "holder-b",
            first.generation,
            _NOW + 20,
            ttl_seconds=_TTL,
        )
    current = store.load_lease("ws_01-05", "pl_01-05")
    assert current is not None
    assert current.generation == second.generation
    assert current.holder == "holder-b"
    assert current.expires_at == second.expires_at


def test_expired_heartbeat_is_rejected(store: ControllerTransactionStore) -> None:
    controller = _controller(store)
    lease = controller.acquire_lease(
        "ws_01-05", "pl_01-05", "holder-a", _NOW, ttl_seconds=_TTL
    )
    with pytest.raises(LeaseError):
        controller.heartbeat_lease(
            "ws_01-05",
            "pl_01-05",
            "holder-a",
            lease.generation,
            _NOW + _TTL + 1,
            ttl_seconds=_TTL,
        )
    loaded = store.load_lease("ws_01-05", "pl_01-05")
    assert loaded is not None
    assert loaded.expires_at == _NOW + _TTL


def test_restart_keeps_current_lease_and_rejects_stale(tmp_path: Path) -> None:
    path = tmp_path / "kernel.db"
    store = SqliteKernelStore(str(path))
    try:
        controller = KernelController(store, recorded_at=_RECORDED_AT)
        first = controller.acquire_lease("ws_01-05", "pl_01-05", "holder-a", _NOW)
        assert (
            controller.submit_with_lease(
                _command(), "holder-a", first.generation, _NOW
            ).status
            == "ACCEPTED"
        )
        second = controller.acquire_lease("ws_01-05", "pl_01-05", "holder-b", _NOW)
        assert second.generation == 2
    finally:
        store.close()
    store2 = SqliteKernelStore(str(path))
    try:
        controller = KernelController(store2, recorded_at=_RECORDED_AT)
        loaded = store2.load_lease("ws_01-05", "pl_01-05")
        assert loaded is not None
        assert loaded.generation == 2
        assert loaded.holder == "holder-b"
        stale = controller.submit_with_lease(
            _command(
                command_id="cmd_01-05-after-restart",
                command_type="REJECT_REQUIREMENT",
                payload={"reason": "stale"},
                expected_revision=1,
            ),
            "holder-a",
            1,
            _NOW,
        )
        assert stale.status == "CONFLICT"
        assert stale.error.code == "LEASE_STALE"
        view = controller.read(
            PipelineQuery(pipeline_id="pl_01-05", workspace_id="ws_01-05")
        )
        assert view.status == "OPEN"
        assert view.revision == 1
        assert store2.counts() == StoreCounts(inbox=1, events=1, pipelines=1, outbox=1)
    finally:
        store2.close()


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
