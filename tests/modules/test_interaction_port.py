"""Shared contract tests for the Interaction Interface fake."""

from __future__ import annotations

import pytest

from hermes_pipeline.interaction import (
    ApprovalRejected,
    FakeInteraction,
    InteractionPort,
)
from hermes_pipeline.interaction.fake import PROBE_COMMAND_ID


def test_fake_is_an_interaction_port() -> None:
    assert isinstance(FakeInteraction(), InteractionPort)


def test_deliver_and_ingest_fixture_command() -> None:
    fake = FakeInteraction()
    assert fake.deliver("hello").ok is True
    command = fake.ingest("probe-event")
    assert command.command_id == PROBE_COMMAND_ID
    assert command.command_id == "cmd_00-07-probe"


def test_ingest_rejects_approval() -> None:
    with pytest.raises(ApprovalRejected):
        FakeInteraction().ingest("please approve this merge")
