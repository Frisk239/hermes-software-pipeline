"""Deterministic Interaction Adapter that cannot accept approval.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import Actor, ControllerCommand
from hermes_pipeline.interaction.ports import ApprovalRejected, InteractionReceipt

PROBE_COMMAND_ID = "cmd_00-07-probe"


class FakeInteraction:
    def deliver(self, text: str) -> InteractionReceipt:
        return InteractionReceipt(ok=bool(text))

    def ingest(self, event: str) -> ControllerCommand:
        if "approve" in event:
            raise ApprovalRejected("interaction fake cannot accept an approval")
        return ControllerCommand(
            schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
            schema_version=FixedV1Integer(1),
            command_id=PROBE_COMMAND_ID,
            idempotency_key="slice-00-07-probe-key",
            workspace_id="ws_probe",
            project_id="prj_probe",
            pipeline_id="pl_probe",
            expected_revision=0,
            actor=Actor(
                principal_id="system",
                provider="SYSTEM",
                provider_actor_id="slice-00-07",
            ),
            ingress="SYSTEM_RECONCILER",
            command_type="SPIKE_INCREMENT",
            payload={"event": event},
            correlation_id="corr-00-07",
            submitted_at=UtcTimestampRef("2026-01-01T00:00:00Z"),
        )


__all__ = ["PROBE_COMMAND_ID", "FakeInteraction"]
