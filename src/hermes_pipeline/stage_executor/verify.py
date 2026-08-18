"""E2E + Acceptance verification flow (slice 04-01).

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from hermes_pipeline.artifacts.ports import ArtifactPutRequest, ArtifactsPort
from hermes_pipeline.delivery.ports import DeliveryPort, DeliveryRequest
from hermes_pipeline.repository.integration import (
    IntegrationCandidate,
    VerificationSandbox,
)
from hermes_pipeline.runtime_broker.binding import BindingNotFound, BindingTable
from hermes_pipeline.runtime_broker.ports import RuntimeBrokerPort, RuntimeLaunchRequest

E2E_BYTES = b"hermes-pipeline-e2e-v1\n"
ACCEPT_BYTES = b"hermes-pipeline-acceptance-v1\n"

VerifyStatus = Literal["READY", "REWORK", "DENIED", "DRIFT"]


@dataclass(frozen=True)
class VerifyResult:
    status: VerifyStatus
    e2e_id: str | None = None
    acceptance_id: str | None = None
    delivered: bool = False


class VerifyFlow:
    def __init__(
        self,
        bindings: BindingTable,
        artifacts: ArtifactsPort,
        e2e_runtime: RuntimeBrokerPort,
        reviewer_runtime: RuntimeBrokerPort,
        delivery: DeliveryPort,
        sandbox: VerificationSandbox,
    ) -> None:
        self._bindings = bindings
        self._artifacts = artifacts
        self._e2e = e2e_runtime
        self._reviewer = reviewer_runtime
        self._delivery = delivery
        self._sandbox = sandbox
        self._passed_sha: str | None = None

    def run(self, integration: IntegrationCandidate) -> VerifyResult:
        try:
            self._bindings.resolve("e2e")
            self._bindings.resolve("reviewer")
        except BindingNotFound:
            return VerifyResult(status="DENIED")
        if self._passed_sha is not None and self._passed_sha != integration.sha:
            return VerifyResult(status="DRIFT")
        self._sandbox.create(integration.sha)
        try:
            e2e_id = f"e2e-{integration.sha[:12]}"
            e2e = self._e2e.launch(RuntimeLaunchRequest(runtime_id=e2e_id, role="e2e"))
            if e2e.status != "COMPLETED":
                return VerifyResult(status="REWORK")
            e2e_art = self._artifacts.put(ArtifactPutRequest(payload=E2E_BYTES))
            accept = self._reviewer.launch(
                RuntimeLaunchRequest(
                    runtime_id=f"acc-{integration.sha[:12]}", role="reviewer"
                )
            )
            if accept.status != "COMPLETED":
                return VerifyResult(status="REWORK", e2e_id=e2e_art.artifact_id)
            acc_art = self._artifacts.put(ArtifactPutRequest(payload=ACCEPT_BYTES))
            published = self._delivery.publish(DeliveryRequest(name=integration.sha))
            self._passed_sha = integration.sha
            return VerifyResult(
                status="READY",
                e2e_id=e2e_art.artifact_id,
                acceptance_id=acc_art.artifact_id,
                delivered=published.ok,
            )
        finally:
            self._sandbox.cleanup()


__all__ = [
    "ACCEPT_BYTES",
    "E2E_BYTES",
    "VerifyFlow",
    "VerifyResult",
]
