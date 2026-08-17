"""KernelController submit tests (slice-01-02)."""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import Actor, ControllerCommand
from hermes_pipeline.controller import KernelController, PipelineQuery
from hermes_pipeline.controller.ports import ControllerPort
from hermes_pipeline.persistence.kernel_store import KernelStore

_SRC = Path(__file__).resolve().parents[2] / "src" / "hermes_pipeline"
_KERNEL = _SRC / "controller" / "kernel.py"
_STORE = _SRC / "persistence" / "kernel_store.py"
_FORBIDDEN = frozenset(
    {
        "CounterSpike",
        "counter_spike",
        "spike_controller",
        "sqlite_spike",
    }
)
_RECORDED_AT = "2026-01-01T00:00:00Z"


def _command(
    *,
    command_id: str = "cmd_01-02-a",
    command_type: str = "CONFIRM_REQUIREMENT",
    payload: dict[str, object] | None = None,
    expected_revision: int = 0,
    pipeline_id: str = "pl_01-02",
) -> ControllerCommand:
    if payload is None:
        payload = {"text": "need a login page"}
    return ControllerCommand(
        schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
        schema_version=FixedV1Integer(1),
        command_id=command_id,
        idempotency_key="slice-01-02-idem-key",
        workspace_id="ws_01-02",
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
        correlation_id="corr-01-02",
        submitted_at=UtcTimestampRef(_RECORDED_AT),
    )


def _controller(tmp_path: Path) -> tuple[KernelController, KernelStore, Path]:
    path = tmp_path / "kernel.db"
    store = KernelStore(str(path))
    return KernelController(store, recorded_at=_RECORDED_AT), store, path


def _counts(path: Path) -> tuple[int, int, int]:
    conn = sqlite3.connect(str(path))
    try:
        inbox = conn.execute("SELECT COUNT(*) FROM inbox").fetchone()[0]
        events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        pipelines = conn.execute("SELECT COUNT(*) FROM pipelines").fetchone()[0]
        return int(inbox), int(events), int(pipelines)
    finally:
        conn.close()


def _pipeline_row(path: Path, pipeline_id: str) -> tuple[str, int, str]:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT status, revision, text FROM pipelines WHERE pipeline_id = ?",
            (pipeline_id,),
        ).fetchone()
        assert row is not None
        return str(row[0]), int(row[1]), str(row[2])
    finally:
        conn.close()


def test_kernel_controller_is_a_controller_port(tmp_path: Path) -> None:
    controller, store, _path = _controller(tmp_path)
    try:
        assert isinstance(controller, ControllerPort)
    finally:
        store.close()


def test_accept_confirm_persists_inbox_event_and_open_pipeline(
    tmp_path: Path,
) -> None:
    controller, store, path = _controller(tmp_path)
    try:
        receipt = controller.submit(_command())
        assert receipt.status == "ACCEPTED"
        assert receipt.observed_revision == 1
        assert len(receipt.event_ids) == 1
        assert receipt.error.message == ""
        store.close()
        assert _counts(path) == (1, 1, 1)
        status, revision, text = _pipeline_row(path, "pl_01-02")
        assert status == "OPEN"
        assert revision == 1
        assert text == "need a login page"
    finally:
        store.close()


def test_accept_reject_persists_rejected_pipeline(tmp_path: Path) -> None:
    controller, store, path = _controller(tmp_path)
    try:
        receipt = controller.submit(
            _command(
                command_id="cmd_01-02-reject",
                command_type="REJECT_REQUIREMENT",
                payload={"reason": "out of scope"},
            )
        )
        assert receipt.status == "ACCEPTED"
        assert receipt.observed_revision == 1
        store.close()
        status, revision, text = _pipeline_row(path, "pl_01-02")
        assert status == "REJECTED"
        assert revision == 1
        assert text == ""
    finally:
        store.close()


def test_empty_requirement_is_rejected_without_durable_write(
    tmp_path: Path,
) -> None:
    controller, store, path = _controller(tmp_path)
    try:
        receipt = controller.submit(_command(payload={"text": "   "}))
        assert receipt.status == "REJECTED"
        assert receipt.error.code == "VALIDATION_ERROR"
        assert receipt.error.message == "empty requirement"
        assert receipt.error.retryable is False
        store.close()
        assert _counts(path) == (0, 0, 0)
    finally:
        store.close()


def test_invalid_transition_is_rejected_without_second_event(
    tmp_path: Path,
) -> None:
    controller, store, path = _controller(tmp_path)
    try:
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
        store.close()
        assert _counts(path) == (1, 1, 1)
    finally:
        store.close()


def test_unsupported_command_type_is_rejected_without_write(
    tmp_path: Path,
) -> None:
    controller, store, path = _controller(tmp_path)
    try:
        receipt = controller.submit(
            _command(command_type="CANCEL_PIPELINE", payload={"stage": "prd"})
        )
        assert receipt.status == "REJECTED"
        assert receipt.error.code == "VALIDATION_ERROR"
        assert receipt.error.message == "unsupported command"
        store.close()
        assert _counts(path) == (0, 0, 0)
    finally:
        store.close()


def test_missing_or_wrong_payload_type_is_unsupported(tmp_path: Path) -> None:
    controller, store, path = _controller(tmp_path)
    try:
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
        store.close()
        assert _counts(path) == (0, 0, 0)
    finally:
        store.close()


def test_identity_conflict_same_id_different_hash(tmp_path: Path) -> None:
    controller, store, path = _controller(tmp_path)
    try:
        first = controller.submit(_command())
        assert first.status == "ACCEPTED"
        conflict = controller.submit(
            _command(payload={"text": "a different requirement"})
        )
        assert conflict.status == "CONFLICT"
        assert conflict.error.code == "CONFLICT"
        assert conflict.error.message == "command identity conflict"
        store.close()
        assert _counts(path) == (1, 1, 1)
    finally:
        store.close()


def test_revision_conflict_before_apply(tmp_path: Path) -> None:
    controller, store, path = _controller(tmp_path)
    try:
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
        store.close()
        assert _counts(path) == (1, 1, 1)
    finally:
        store.close()


def test_restart_dedup_returns_stored_receipt_and_one_event(
    tmp_path: Path,
) -> None:
    controller, store, path = _controller(tmp_path)
    try:
        first = controller.submit(_command())
        assert first.status == "ACCEPTED"
        store.close()
        store2 = KernelStore(str(path))
        replayed = KernelController(store2, recorded_at=_RECORDED_AT).submit(_command())
        assert replayed == first
        store2.close()
        assert _counts(path) == (1, 1, 1)
    finally:
        store.close()


def test_same_process_dedup_returns_stored_receipt(tmp_path: Path) -> None:
    controller, store, _path = _controller(tmp_path)
    try:
        first = controller.submit(_command())
        second = controller.submit(_command())
        assert second == first
    finally:
        store.close()


def test_persistence_unavailable_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller, store, path = _controller(tmp_path)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(store, "upsert_pipeline", boom)
    try:
        receipt = controller.submit(_command())
        assert receipt.status == "REJECTED"
        assert receipt.error.code == "INTERNAL_ERROR"
        assert receipt.error.message == "persistence unavailable"
        assert receipt.error.retryable is True
        store.close()
        assert _counts(path) == (0, 0, 0)
    finally:
        store.close()


def test_read_returns_unknown_fixture(tmp_path: Path) -> None:
    controller, store, _path = _controller(tmp_path)
    try:
        view = controller.read(PipelineQuery(pipeline_id="pl_01-02"))
        assert view.pipeline_id == "pl_01-02"
        assert view.revision == 0
        assert view.status == "UNKNOWN"
    finally:
        store.close()


def test_kernel_import_boundary() -> None:
    violations: list[str] = []
    for path in (_KERNEL, _STORE):
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
