"""Shared contract tests for the Controller Interface fake."""

from __future__ import annotations

import inspect

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import Actor, CommandReceipt, ControllerCommand
from hermes_pipeline.controller import ControllerPort, FakeController, PipelineQuery
from hermes_pipeline.controller.fake import FakeController as FakeControllerImpl
from hermes_pipeline.controller.ports import ControllerPort as ControllerPortType


def _command(*, pipeline_id: str = "pl_probe") -> ControllerCommand:
    return ControllerCommand(
        schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
        schema_version=FixedV1Integer(1),
        command_id="cmd_00-07-probe",
        idempotency_key="slice-00-07-probe-key",
        workspace_id="ws_probe",
        project_id="prj_probe",
        pipeline_id=pipeline_id,
        expected_revision=0,
        actor=Actor(
            principal_id="system",
            provider="SYSTEM",
            provider_actor_id="slice-00-07",
        ),
        ingress="SYSTEM_RECONCILER",
        command_type="SPIKE_INCREMENT",
        payload={"delta": 1},
        correlation_id="corr-00-07",
        submitted_at=UtcTimestampRef("2026-01-01T00:00:00Z"),
    )


def test_fake_is_a_controller_port() -> None:
    assert isinstance(FakeController(), ControllerPort)
    assert FakeController is FakeControllerImpl
    assert ControllerPort is ControllerPortType


def test_submit_stores_last_command_and_returns_receipt() -> None:
    fake = FakeController()
    command = _command()
    receipt = fake.submit(command)
    assert isinstance(receipt, CommandReceipt)
    assert receipt.command_id == command.command_id
    assert receipt.pipeline_id == command.pipeline_id
    assert fake.last_submit is command


def test_read_unknown_id_returns_fixture_fields_only() -> None:
    view = FakeController().read(PipelineQuery(pipeline_id="pl_unknown"))
    assert view.pipeline_id == "pl_unknown"
    assert view.revision == 0
    assert view.status == "UNKNOWN"
    assert set(view.__dataclass_fields__) == {"pipeline_id", "revision", "status"}


def test_read_has_no_rbac_parameters() -> None:
    parameters = inspect.signature(FakeController.read).parameters
    assert list(parameters) == ["self", "query"]
    assert "actor" not in parameters
    assert "role" not in parameters
