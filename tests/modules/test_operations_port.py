"""Shared contract tests for the Operations Interface fake."""

from __future__ import annotations

from hermes_pipeline.operations import (
    FakeOperations,
    OperationsPort,
    OperationsRequest,
)


def test_fake_is_an_operations_port() -> None:
    assert isinstance(FakeOperations(), OperationsPort)


def test_doctor_health_uses_operations_health_fake() -> None:
    report = FakeOperations().health()
    assert report.ok is True
    assert report.checks == ("state-root", "runtime")


def test_backup_restore_unsupported_while_writer_active() -> None:
    fake = FakeOperations(writer_active=True)
    request = OperationsRequest(name="workspace")
    assert fake.backup(request).status == "UNSUPPORTED"
    assert fake.restore(request).status == "UNSUPPORTED"
    assert fake.reconcile(request).status == "UNSUPPORTED"
    assert fake.health().ok is False


def test_backup_restore_ok_when_writer_idle() -> None:
    fake = FakeOperations(writer_active=False)
    request = OperationsRequest(name="workspace")
    assert fake.backup(request).status == "OK"
    assert fake.restore(request).status == "OK"
