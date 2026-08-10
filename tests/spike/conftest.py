"""Shared spike fixtures (slice-00-04).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Shared deterministic facilities for the slice-00-04 spike tests: a frozen
UTC clock, a deterministic identity sequence, and a factory for valid
``ControllerCommand`` values. No test depends on wall time, randomness,
network, or credentials.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import Actor, ControllerCommand
from hermes_pipeline.controller.spike_controller import (
    COMMAND_TYPE,
    PAYLOAD_DELTA_FIELD,
)

FROZEN_INSTANT = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

SPIKE_ACTOR = Actor(
    principal_id="system",
    provider="SYSTEM",
    provider_actor_id="spike-tests",
)


def make_spike_command(
    command_id: str,
    *,
    delta: int = 1,
    expected_revision: int = 0,
    correlation_id: str = "corr-0000",
    payload_extra: dict[str, object] | None = None,
    workspace_id: str = "ws_spike",
    project_id: str = "prj_spike",
    pipeline_id: str = "pl_spike",
) -> ControllerCommand:
    """One deterministic, schema-valid spike Controller command."""
    payload: dict[str, object] = {PAYLOAD_DELTA_FIELD: delta}
    if payload_extra:
        payload.update(payload_extra)
    return ControllerCommand(
        schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
        schema_version=FixedV1Integer(1),
        command_id=command_id,
        idempotency_key=f"spike-{command_id}-key-00000000",
        workspace_id=workspace_id,
        project_id=project_id,
        pipeline_id=pipeline_id,
        expected_revision=expected_revision,
        actor=SPIKE_ACTOR,
        ingress="SYSTEM_RECONCILER",
        command_type=COMMAND_TYPE,
        payload=payload,
        correlation_id=correlation_id,
        submitted_at=UtcTimestampRef("2026-01-01T00:00:00Z"),
    )


@pytest.fixture
def frozen_clock() -> Callable[[], datetime]:
    """A clock frozen at one fixed UTC instant; never reads wall time."""

    def clock() -> datetime:
        return FROZEN_INSTANT

    return clock


@pytest.fixture
def event_id_sequence() -> Iterator[Callable[[], str]]:
    """Deterministic event-id provider: evt-0, evt-1, ..."""
    counter = 0

    def next_event_id() -> str:
        nonlocal counter
        value = f"evt_{counter:08d}"
        counter += 1
        return value

    yield next_event_id


def make_event_id_provider(prefix: str) -> Callable[[], str]:
    """Deterministic unique event-id provider for non-fixture test code.

    The spike events table stores ``event_id`` as UNIQUE, so every accepted
    command in one store needs a distinct event id; a fixed lambda would
    make the second acceptance fail.
    """
    counter = 0

    def next_event_id() -> str:
        nonlocal counter
        value = f"{prefix}_{counter:08d}"
        counter += 1
        return value

    return next_event_id
