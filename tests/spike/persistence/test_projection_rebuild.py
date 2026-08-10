"""Projection rebuild and Event hash-chain tests (slice-00-04, AC-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

A projection rebuilt from the authoritative Event Log (with Event
hash-chain verification) equals the live projection for the same Event set;
rebuild is deterministic. Positive: rebuild matches the live projection
across generated Event sequences. Negative: a tampered Event breaks the
hash chain and fails rebuild; a rebuild that disagrees with the live
projection fails.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

import pytest
from tests.spike.conftest import make_spike_command

from hermes_pipeline.controller._persistence_port import (
    ControllerPersistencePort,
    PersistenceError,
)
from hermes_pipeline.controller.spike_controller import SpikeController
from hermes_pipeline.persistence.in_memory import InMemoryControllerStore
from hermes_pipeline.persistence.sqlite_spike import SqliteControllerStore


@runtime_checkable
class PortProvider(Protocol):
    """Builds a fresh port for the rebuild tests."""

    def __call__(self) -> ControllerPersistencePort:
        """Build one fresh port."""
        raise NotImplementedError


@pytest.fixture(params=["in-memory", "sqlite"], ids=["in-memory", "sqlite"])
def port_provider(request: pytest.FixtureRequest, tmp_path: Path) -> PortProvider:
    def build() -> ControllerPersistencePort:
        if request.param == "in-memory":
            return InMemoryControllerStore()
        return SqliteControllerStore(tmp_path / f"rebuild-{request.param}.db")

    return build


def _run_sequence(
    provider: PortProvider,
    steps: int,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
) -> tuple[SpikeController, ControllerPersistencePort]:
    port = provider()
    controller = SpikeController(port, frozen_clock, event_id_sequence)
    for index in range(steps):
        receipt = controller.submit(
            make_spike_command(f"cmd_rebuild_{index:04d}", expected_revision=index)
        )
        assert receipt.status == "ACCEPTED"
    return controller, port


def test_rebuild_matches_live_projection_after_generated_sequences(
    port_provider: PortProvider,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
) -> None:
    """Positive: rebuild equals the live projection across generated
    sequences, and rebuild is deterministic (repeated rebuilds agree)."""
    for steps in (1, 2, 5, 17):
        _, port = _run_sequence(port_provider, steps, frozen_clock, event_id_sequence)
        live = port.load_counter()
        assert live.value == steps
        assert live.revision == steps
        rebuilt_once = port.rebuild_projection()
        rebuilt_twice = port.rebuild_projection()
        assert rebuilt_once == live
        assert rebuilt_twice == live


def test_tampered_event_breaks_hash_chain_and_fails_rebuild(
    port_provider: PortProvider,
    frozen_clock: Callable[[], datetime],
    event_id_sequence: Callable[[], str],
) -> None:
    """Negative: a tampered Event breaks the hash chain and fails rebuild."""
    _, port = _run_sequence(port_provider, 4, frozen_clock, event_id_sequence)
    _tamper_second_event_payload(port)
    with pytest.raises(PersistenceError):
        port.rebuild_projection()
    # The live projection still reads its own stored value; the tamper only
    # breaks the chain, which the rebuild surfaces.
    assert port.load_counter().revision == 4


def _tamper_second_event_payload(port: ControllerPersistencePort) -> None:
    """Rewrite the second Event's payload without updating its hash."""
    if isinstance(port, InMemoryControllerStore):
        events = port._store.events  # type: ignore[attr-defined]
        events[1]["payload_json"] = '{"value":99,"revision":99}'
        return
    if isinstance(port, SqliteControllerStore):
        conn = sqlite3.connect(port._database_path)  # type: ignore[attr-defined]
        try:
            conn.execute(
                "UPDATE spike_events SET payload_json = ? WHERE sequence = 2",
                ('{"value":99,"revision":99}',),
            )
            conn.commit()
        finally:
            conn.close()
        return
    raise AssertionError(f"unsupported port {type(port).__name__}")
