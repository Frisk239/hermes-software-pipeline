"""Subprocess crash worker for AC-05 (slice-00-04 spike).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

This worker drives the real ``SpikeController`` and
``SqliteControllerStore.commit_acceptance`` path.  The Adapter, not a
duplicate raw-``sqlite3`` implementation, calls ``os._exit`` at the two
durable boundaries:

- ``pre-commit``: after all five Adapter writes and before its COMMIT;
- ``post-commit``: after that same Adapter transaction committed.

Usage: python _crash_worker.py <database> <pre-commit|post-commit> <command_id>
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import Actor, ControllerCommand
from hermes_pipeline.controller.spike_controller import (
    COMMAND_TYPE,
    PAYLOAD_DELTA_FIELD,
    SpikeController,
)
from hermes_pipeline.persistence.sqlite_spike import (
    CRASH_EXIT_POST_COMMIT,
    CRASH_EXIT_PRE_COMMIT,
    SqliteControllerStore,
)

EXIT_PRE_COMMIT = CRASH_EXIT_PRE_COMMIT
EXIT_POST_COMMIT = CRASH_EXIT_POST_COMMIT


def _make_command(command_id: str) -> ControllerCommand:
    """Create the one deterministic command submitted through the actual
    Controller/Adapter path.  This is an input fixture only; it contains no
    duplicate persistence implementation."""
    return ControllerCommand(
        schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
        schema_version=FixedV1Integer(1),
        command_id=command_id,
        idempotency_key=f"spike-{command_id}-key-00000000",
        workspace_id="ws_spike",
        project_id="prj_spike",
        pipeline_id="pl_spike",
        expected_revision=0,
        actor=Actor(
            principal_id="system",
            provider="SYSTEM",
            provider_actor_id="spike-tests",
        ),
        ingress="SYSTEM_RECONCILER",
        command_type=COMMAND_TYPE,
        payload={PAYLOAD_DELTA_FIELD: 1},
        correlation_id="corr-0000",
        submitted_at=UtcTimestampRef("2026-01-01T00:00:00Z"),
    )


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "usage: _crash_worker.py <database> <pre-commit|post-commit> <command_id>"
        )
        return 2
    database, crash_point, command_id = argv
    if crash_point not in ("pre-commit", "post-commit"):
        return 2

    # The call below constructs the actual experimental Adapter and submits
    # through the actual Controller path.  The process must never return: the
    # Adapter exits at the requested durable boundary.
    store = SqliteControllerStore(database, crash_at=crash_point)
    controller = SpikeController(
        store,
        lambda: datetime(2026, 1, 1, tzinfo=UTC),
        lambda: "evt_crash",
    )
    controller.submit(_make_command(command_id))
    store.close()
    return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
