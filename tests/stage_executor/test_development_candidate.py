from __future__ import annotations

from pathlib import Path

import pytest

from hermes_pipeline.artifacts import LocalCasArtifacts
from hermes_pipeline.operations.baseline import SolutionApproval
from hermes_pipeline.operations.projects import ProjectRegistry
from hermes_pipeline.repository.worktree import SECRET_CANARY, ManagedWorktree
from hermes_pipeline.runtime_broker.binding import AgentBinding, BindingTable
from hermes_pipeline.runtime_broker.ports import (
    RuntimeHandle,
    RuntimeLaunchRequest,
    RuntimeOutcome,
    RuntimeSignalReceipt,
    RuntimeSnapshot,
)
from hermes_pipeline.stage_executor.development import (
    IMPL_BYTES,
    CandidateGate,
    DevelopmentStage,
)


def _stage(
    tmp_path: Path,
) -> tuple[DevelopmentStage, SolutionApproval, LocalCasArtifacts]:
    registry = ProjectRegistry()
    registry.register("prj_demo", "Demo")
    registry.admit("prj_demo", "approver", "ADMIN")
    approval = SolutionApproval(registry)
    approval.designate("pl_demo", "prj_demo", "approver")
    approval.approve(
        pipeline_id="pl_demo",
        project_id="prj_demo",
        actor_id="approver",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    artifacts = LocalCasArtifacts(tmp_path / "cas")
    bindings = BindingTable({"executor": AgentBinding("executor", "fake", "fake-dev")})
    stage = DevelopmentStage(
        bindings, approval, artifacts, ManagedWorktree(tmp_path / "wt")
    )
    return stage, approval, artifacts


def test_fresh_baseline_writes_worktree_and_candidate(tmp_path: Path) -> None:
    stage, approval, artifacts = _stage(tmp_path)
    result = stage.run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert result.status == "COMPLETED"
    assert result.artifact_id is not None
    assert result.candidate is not None
    assert len(result.candidate.sha) == 64
    assert artifacts.open(result.artifact_id) == IMPL_BYTES
    assert (tmp_path / "wt" / "src" / "app.py").read_bytes() == IMPL_BYTES
    assert (
        CandidateGate(approval, artifacts)
        .evaluate(
            pipeline_id="pl_demo",
            prd_id="art_prd",
            design_id="art_design",
            testplan_id="art_test",
            result=result,
        )
        .status
        == "PASS"
    )


def test_stale_baseline_or_missing_executor_is_denied(tmp_path: Path) -> None:
    stage, approval, artifacts = _stage(tmp_path)
    stale = stage.run(
        pipeline_id="pl_demo",
        prd_id="art_prd_v2",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert stale.status == "DENIED"
    empty = DevelopmentStage(
        BindingTable({}),
        approval,
        artifacts,
        ManagedWorktree(tmp_path / "wt2"),
    )
    assert (
        empty.run(
            pipeline_id="pl_demo",
            prd_id="art_prd",
            design_id="art_design",
            testplan_id="art_test",
        ).status
        == "DENIED"
    )


class _WritingExecutor:
    def __init__(self, worktree: ManagedWorktree) -> None:
        self._worktree = worktree

    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        del request
        self._worktree.write("src/real.py", b"print('from-executor')\n")
        return RuntimeHandle(runtime_id="dev", status="COMPLETED")

    def signal(self, runtime_id: str) -> RuntimeSignalReceipt:
        del runtime_id
        return RuntimeSignalReceipt(ok=True, code="CANCELLED")

    def inspect(self, runtime_id: str) -> RuntimeSnapshot:
        return RuntimeSnapshot(runtime_id=runtime_id, status="COMPLETED")

    def collect(self, runtime_id: str) -> RuntimeOutcome:
        return RuntimeOutcome(runtime_id=runtime_id, status="COMPLETED")


class _FailingExecutor(_WritingExecutor):
    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        del request
        return RuntimeHandle(runtime_id="dev", status="FAILED")


def test_bound_executor_must_write_worktree(tmp_path: Path) -> None:
    _built, approval, artifacts = _stage(tmp_path)
    del _built
    worktree = ManagedWorktree(tmp_path / "wt-real")
    bindings = BindingTable(
        {"executor": AgentBinding("executor", "opencode", "grok-4.6")}
    )
    real = DevelopmentStage(
        bindings,
        approval,
        artifacts,
        worktree,
        executor=_WritingExecutor(worktree),
    )
    result = real.run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert result.status == "COMPLETED"
    assert result.candidate is not None
    assert result.candidate.relative_path == "src/real.py"
    assert artifacts.open(result.artifact_id or "") == b"print('from-executor')\n"
    assert not (tmp_path / "wt-real" / "src" / "app.py").exists()


def test_bound_executor_prefers_src_over_prd(tmp_path: Path) -> None:
    _built, approval, artifacts = _stage(tmp_path)
    del _built
    worktree = ManagedWorktree(tmp_path / "wt-mix")
    worktree.write("PRD.md", b"# leftover prd\n")

    class _MixedExecutor(_WritingExecutor):
        def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
            del request
            self._worktree.write("src/app.py", b"print('parking-login')\n")
            return RuntimeHandle(runtime_id="dev", status="COMPLETED")

    result = DevelopmentStage(
        BindingTable({"executor": AgentBinding("executor", "opencode", "grok-4.6")}),
        approval,
        artifacts,
        worktree,
        executor=_MixedExecutor(worktree),
    ).run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert result.status == "COMPLETED"
    assert result.candidate is not None
    assert result.candidate.relative_path == "src/app.py"
    assert artifacts.open(result.artifact_id or "") == b"print('parking-login')\n"


def test_bound_executor_failure_is_denied_without_fixture(tmp_path: Path) -> None:
    _built, approval, artifacts = _stage(tmp_path)
    del _built
    worktree = ManagedWorktree(tmp_path / "wt-fail")
    bindings = BindingTable(
        {"executor": AgentBinding("executor", "opencode", "grok-4.6")}
    )
    denied = DevelopmentStage(
        bindings,
        approval,
        artifacts,
        worktree,
        executor=_FailingExecutor(worktree),
    ).run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert denied.status == "DENIED"
    assert list(worktree.files()) == []


def test_timeout_with_only_prd_or_readme_is_denied(tmp_path: Path) -> None:
    _built, approval, artifacts = _stage(tmp_path)
    del _built
    worktree = ManagedWorktree(tmp_path / "wt-notes")

    class _NotesOnly(_WritingExecutor):
        def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
            del request
            self._worktree.write("PRD.md", b"# leftover prd\n")
            self._worktree.write("README.md", b"notes\n")
            return RuntimeHandle(runtime_id="dev", status="FAILED")

    denied = DevelopmentStage(
        BindingTable({"executor": AgentBinding("executor", "opencode", "grok-4.6")}),
        approval,
        artifacts,
        worktree,
        executor=_NotesOnly(worktree),
    ).run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert denied.status == "DENIED"
    assert denied.candidate is None


def test_bound_executor_timeout_still_harvests_src(tmp_path: Path) -> None:
    _built, approval, artifacts = _stage(tmp_path)
    del _built
    worktree = ManagedWorktree(tmp_path / "wt-timeout")

    class _TimeoutWriter(_WritingExecutor):
        def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
            del request
            self._worktree.write("src/app.py", b"print('parking-login')\n")
            return RuntimeHandle(runtime_id="dev", status="FAILED")

    result = DevelopmentStage(
        BindingTable({"executor": AgentBinding("executor", "opencode", "grok-4.6")}),
        approval,
        artifacts,
        worktree,
        executor=_TimeoutWriter(worktree),
    ).run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert result.status == "COMPLETED"
    assert result.candidate is not None
    assert result.candidate.relative_path == "src/app.py"


def test_failing_self_test_is_denied_with_feedback(tmp_path: Path) -> None:
    _built, approval, artifacts = _stage(tmp_path)
    del _built
    worktree = ManagedWorktree(tmp_path / "wt-self-fail")

    class _BadApp(_WritingExecutor):
        def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
            del request
            self._worktree.write("src/app.py", b"raise SystemExit(1)\n")
            return RuntimeHandle(runtime_id="dev", status="COMPLETED")

    denied = DevelopmentStage(
        BindingTable({"executor": AgentBinding("executor", "opencode", "grok-4.6")}),
        approval,
        artifacts,
        worktree,
        executor=_BadApp(worktree),
    ).run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert denied.status == "DENIED"
    assert denied.feedback
    assert (
        CandidateGate(approval, artifacts)
        .evaluate(
            pipeline_id="pl_demo",
            prd_id="art_prd",
            design_id="art_design",
            testplan_id="art_test",
            result=denied,
        )
        .status
        == "FAIL"
    )


def test_self_test_fail_relaunches_with_feedback(tmp_path: Path) -> None:
    _built, approval, artifacts = _stage(tmp_path)
    del _built
    worktree = ManagedWorktree(tmp_path / "wt-self-fix")

    class _FixOnFeedback(_WritingExecutor):
        def __init__(self, tree: ManagedWorktree) -> None:
            super().__init__(tree)
            self.prompts: list[str] = []

        def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
            self.prompts.append(request.prompt)
            if "FEEDBACK FROM LAST GATE" in request.prompt:
                self._worktree.write("src/app.py", b"print('login-ok')\n")
            else:
                self._worktree.write("src/app.py", b"raise SystemExit(1)\n")
            return RuntimeHandle(runtime_id="dev", status="COMPLETED")

    executor = _FixOnFeedback(worktree)
    result = DevelopmentStage(
        BindingTable({"executor": AgentBinding("executor", "opencode", "grok-4.6")}),
        approval,
        artifacts,
        worktree,
        executor=executor,
    ).run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
        prompt="Implement the approved solution.",
    )
    assert result.status == "COMPLETED"
    assert len(executor.prompts) == 2
    assert "FEEDBACK FROM LAST GATE" in executor.prompts[1]


def test_failing_pytest_is_denied_with_feedback(tmp_path: Path) -> None:
    _built, approval, artifacts = _stage(tmp_path)
    del _built
    worktree = ManagedWorktree(tmp_path / "wt-pytest")

    class _BadTests(_WritingExecutor):
        def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
            del request
            self._worktree.write("src/app.py", b"print('ok')\n")
            self._worktree.write(
                "tests/test_app.py",
                b"def test_fail() -> None:\n    assert False\n",
            )
            return RuntimeHandle(runtime_id="dev", status="COMPLETED")

    denied = DevelopmentStage(
        BindingTable({"executor": AgentBinding("executor", "opencode", "grok-4.6")}),
        approval,
        artifacts,
        worktree,
        executor=_BadTests(worktree),
    ).run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert denied.status == "DENIED"
    assert "assert" in denied.feedback.lower() or "fail" in denied.feedback.lower()


def test_secret_or_escape_is_denied(tmp_path: Path) -> None:
    stage, _approval, _artifacts = _stage(tmp_path)
    secret = stage.run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
        payload=f"token={SECRET_CANARY}".encode(),
    )
    assert secret.status == "DENIED"
    escape = stage.run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
        relative_path="../escape.py",
    )
    assert escape.status == "DENIED"


def test_prefix_sibling_write_is_escape(tmp_path: Path) -> None:
    tree = ManagedWorktree(tmp_path / "wt")
    with pytest.raises(ValueError, match="path escape"):
        tree.write("../wt2/x.py", b"print(1)\n")


def test_github_token_in_src_is_denied(tmp_path: Path) -> None:
    _built, approval, artifacts = _stage(tmp_path)
    del _built
    worktree = ManagedWorktree(tmp_path / "wt-tok")

    class _Token(_WritingExecutor):
        def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
            del request
            self._worktree.write("src/app.py", b"GITHUB_TOKEN=ghp_example\n")
            return RuntimeHandle(runtime_id="dev", status="COMPLETED")

    denied = DevelopmentStage(
        BindingTable({"executor": AgentBinding("executor", "opencode", "grok-4.6")}),
        approval,
        artifacts,
        worktree,
        executor=_Token(worktree),
    ).run(
        pipeline_id="pl_demo",
        prd_id="art_prd",
        design_id="art_design",
        testplan_id="art_test",
    )
    assert denied.status == "DENIED"
