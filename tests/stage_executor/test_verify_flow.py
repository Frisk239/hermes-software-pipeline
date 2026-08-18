from __future__ import annotations

from pathlib import Path

from hermes_pipeline.artifacts import LocalCasArtifacts
from hermes_pipeline.delivery.fake import FakeDelivery
from hermes_pipeline.repository.integration import (
    VerificationSandbox,
    build_integration_candidate,
)
from hermes_pipeline.runtime_broker.binding import AgentBinding, BindingTable
from hermes_pipeline.runtime_broker.capability import compile_profile
from hermes_pipeline.runtime_broker.chrome_mcp import ChromeMcpRuntime
from hermes_pipeline.runtime_broker.ports import (
    RuntimeBrokerPort,
    RuntimeHandle,
    RuntimeLaunchRequest,
    RuntimeOutcome,
    RuntimeSignalReceipt,
    RuntimeSnapshot,
)
from hermes_pipeline.stage_executor.verify import ACCEPT_BYTES, E2E_BYTES, VerifyFlow


class _FakeMcp:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def call(self, name: str, arguments: dict[str, object]) -> str:
        del arguments
        self.calls.append(name)
        return "ok"


class _Completing:
    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        return RuntimeHandle(runtime_id=request.runtime_id, status="COMPLETED")

    def signal(self, runtime_id: str) -> RuntimeSignalReceipt:
        return RuntimeSignalReceipt(ok=True, code="CANCELLED")

    def inspect(self, runtime_id: str) -> RuntimeSnapshot:
        return RuntimeSnapshot(runtime_id=runtime_id, status="COMPLETED")

    def collect(self, runtime_id: str) -> RuntimeOutcome:
        return RuntimeOutcome(runtime_id=runtime_id, status="COMPLETED")


class _Failing(_Completing):
    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        return RuntimeHandle(runtime_id=request.runtime_id, status="FAILED")


def _bindings() -> BindingTable:
    return BindingTable(
        {
            "e2e": AgentBinding("e2e", "opencode", "grok-4.6"),
            "reviewer": AgentBinding("reviewer", "fake", "fake-accept"),
        }
    )


def _flow(
    tmp_path: Path,
    *,
    e2e: RuntimeBrokerPort | None = None,
    reviewer: RuntimeBrokerPort | None = None,
) -> tuple[VerifyFlow, VerificationSandbox, LocalCasArtifacts]:
    artifacts = LocalCasArtifacts(tmp_path / "cas")
    sandbox = VerificationSandbox(tmp_path / "sandbox")
    chrome = ChromeMcpRuntime(
        profile=compile_profile(
            write_roots=["/work"],
            browser="CHROME_DEVTOOLS_MCP",
            stage_type="E2E",
        ),
        mcp=_FakeMcp(),
    )
    flow = VerifyFlow(
        _bindings(),
        artifacts,
        chrome if e2e is None else e2e,
        _Completing() if reviewer is None else reviewer,
        FakeDelivery(),
        sandbox,
    )
    return flow, sandbox, artifacts


def test_pass_delivers_and_cleans_sandbox(tmp_path: Path) -> None:
    flow, sandbox, artifacts = _flow(tmp_path)
    integration = build_integration_candidate("c" * 64, "b" * 64)
    result = flow.run(integration)
    assert result.status == "READY"
    assert result.delivered is True
    assert result.delivery is not None
    assert result.delivery.branch == "hermes/prj_local/pl_local"
    assert result.delivery.head_sha == integration.sha
    assert result.e2e_id is not None
    assert result.acceptance_id is not None
    assert artifacts.open(result.e2e_id) == E2E_BYTES
    assert artifacts.open(result.acceptance_id) == ACCEPT_BYTES
    assert sandbox.exists() is False


def test_e2e_failure_is_rework_without_delivery(tmp_path: Path) -> None:
    flow, sandbox, _artifacts = _flow(tmp_path, e2e=_Failing())
    result = flow.run(build_integration_candidate("c" * 64, "b" * 64))
    assert result.status == "REWORK"
    assert result.delivered is False
    assert sandbox.exists() is False


def test_missing_binding_is_denied(tmp_path: Path) -> None:
    artifacts = LocalCasArtifacts(tmp_path / "cas")
    sandbox = VerificationSandbox(tmp_path / "sandbox")
    flow = VerifyFlow(
        BindingTable({}),
        artifacts,
        _Completing(),
        _Completing(),
        FakeDelivery(),
        sandbox,
    )
    result = flow.run(build_integration_candidate("c" * 64, "b" * 64))
    assert result.status == "DENIED"


def test_new_sha_after_pass_is_drift(tmp_path: Path) -> None:
    flow, _sandbox, _artifacts = _flow(tmp_path)
    first = build_integration_candidate("c" * 64, "b" * 64)
    assert flow.run(first).status == "READY"
    second = build_integration_candidate("d" * 64, "b" * 64)
    assert flow.run(second).status == "DRIFT"
