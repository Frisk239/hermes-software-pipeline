from __future__ import annotations

from pathlib import Path

import pytest

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
            "e2e": AgentBinding("e2e", "fake", "fake-e2e"),
            "reviewer": AgentBinding("reviewer", "fake", "fake-acc"),
        }
    )


def _real_both_bindings() -> BindingTable:
    return BindingTable(
        {
            "e2e": AgentBinding("e2e", "opencode", "grok-4.6"),
            "reviewer": AgentBinding("reviewer", "opencode", "grok-4.6"),
        }
    )


def _real_e2e_bindings() -> BindingTable:
    return BindingTable(
        {
            "e2e": AgentBinding("e2e", "opencode", "grok-4.6"),
            "reviewer": AgentBinding("reviewer", "fake", "fake-acc"),
        }
    )


def _flow(
    tmp_path: Path,
    *,
    e2e: RuntimeBrokerPort | None = None,
    reviewer: RuntimeBrokerPort | None = None,
    candidate_root: Path | None = None,
    bindings: BindingTable | None = None,
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
        bindings if bindings is not None else _bindings(),
        artifacts,
        chrome if e2e is None else e2e,
        _Completing() if reviewer is None else reviewer,
        FakeDelivery(),
        sandbox,
        candidate_root=candidate_root,
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


def test_sandbox_rejects_escaped_write(tmp_path: Path) -> None:
    sandbox = VerificationSandbox(tmp_path / "sandbox")
    sandbox.create("sha")
    with pytest.raises(ValueError, match="path escape"):
        sandbox.write("../escape.txt", "nope")
    assert not (tmp_path / "escape.txt").exists()


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


def test_real_e2e_prefers_check_flag(tmp_path: Path) -> None:
    work = tmp_path / "wt"
    (work / "src").mkdir(parents=True)
    (work / "src" / "app.py").write_text(
        "import sys\n"
        "if '--check' in sys.argv:\n"
        "    print('login-ok')\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit('should-not-run')\n",
        encoding="utf-8",
    )
    flow, sandbox, artifacts = _flow(
        tmp_path, candidate_root=work, bindings=_real_e2e_bindings()
    )
    result = flow.run(build_integration_candidate("c" * 64, "b" * 64))
    assert result.status == "READY"
    assert result.e2e_id is not None
    assert b"login-ok" in artifacts.open(result.e2e_id)
    assert sandbox.exists() is False


def test_real_e2e_runs_candidate_script(tmp_path: Path) -> None:
    work = tmp_path / "wt"
    (work / "src").mkdir(parents=True)
    (work / "src" / "app.py").write_text("print('2+3=5')\n", encoding="utf-8")
    flow, sandbox, artifacts = _flow(
        tmp_path,
        e2e=_Failing(),
        candidate_root=work,
        bindings=_real_e2e_bindings(),
    )
    result = flow.run(build_integration_candidate("c" * 64, "b" * 64))
    assert result.status == "READY"
    assert result.e2e_id is not None
    assert b"2+3=5" in artifacts.open(result.e2e_id)
    assert sandbox.exists() is False


def test_script_pass_skips_real_reviewer_launch(tmp_path: Path) -> None:
    work = tmp_path / "wt"
    (work / "src").mkdir(parents=True)
    (work / "src" / "app.py").write_text("print('2+3=5')\n", encoding="utf-8")
    flow, sandbox, artifacts = _flow(
        tmp_path,
        e2e=_Failing(),
        reviewer=_Failing(),
        candidate_root=work,
        bindings=_real_both_bindings(),
    )
    result = flow.run(build_integration_candidate("c" * 64, "b" * 64))
    assert result.status == "READY"
    assert result.e2e_id is not None
    assert b"2+3=5" in artifacts.open(result.e2e_id)
    assert sandbox.exists() is False


def test_real_e2e_script_failure_is_rework(tmp_path: Path) -> None:
    work = tmp_path / "wt"
    (work / "src").mkdir(parents=True)
    (work / "src" / "app.py").write_text("raise SystemExit(1)\n", encoding="utf-8")
    flow, sandbox, _artifacts = _flow(
        tmp_path, candidate_root=work, bindings=_real_e2e_bindings()
    )
    result = flow.run(build_integration_candidate("c" * 64, "b" * 64))
    assert result.status == "REWORK"
    assert result.delivered is False
    assert result.feedback
    assert sandbox.exists() is False


def test_real_e2e_without_candidate_is_rework(tmp_path: Path) -> None:
    flow, sandbox, _artifacts = _flow(tmp_path, bindings=_real_e2e_bindings())
    result = flow.run(build_integration_candidate("c" * 64, "b" * 64))
    assert result.status == "REWORK"
    assert result.delivered is False
    assert sandbox.exists() is False


def test_real_e2e_pytest_failure_is_rework(tmp_path: Path) -> None:
    work = tmp_path / "wt"
    (work / "src").mkdir(parents=True)
    (work / "tests").mkdir()
    (work / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (work / "tests" / "test_app.py").write_text(
        "def test_fail() -> None:\n    assert False\n", encoding="utf-8"
    )
    flow, sandbox, _artifacts = _flow(
        tmp_path, candidate_root=work, bindings=_real_e2e_bindings()
    )
    result = flow.run(build_integration_candidate("c" * 64, "b" * 64))
    assert result.status == "REWORK"
    assert result.feedback
    assert sandbox.exists() is False


def test_new_sha_after_pass_is_drift(tmp_path: Path) -> None:
    flow, _sandbox, _artifacts = _flow(tmp_path)
    first = build_integration_candidate("c" * 64, "b" * 64)
    assert flow.run(first).status == "READY"
    second = build_integration_candidate("d" * 64, "b" * 64)
    assert flow.run(second).status == "DRIFT"
