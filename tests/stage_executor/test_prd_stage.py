from __future__ import annotations

import ast
from pathlib import Path

from hermes_pipeline.artifacts import LocalCasArtifacts
from hermes_pipeline.artifacts.ports import ArtifactPutRequest
from hermes_pipeline.contracts.runtime import Actor
from hermes_pipeline.controller import KernelController
from hermes_pipeline.operations.projects import ProjectRegistry, RequirementIntake
from hermes_pipeline.persistence.kernel_memory import MemoryKernelStore
from hermes_pipeline.runtime_broker.binding import (
    AgentBinding,
    BindingTable,
    RuntimeFamily,
)
from hermes_pipeline.runtime_broker.ports import (
    RuntimeHandle,
    RuntimeLaunchRequest,
    RuntimeOutcome,
    RuntimeSignalReceipt,
    RuntimeSnapshot,
)
from hermes_pipeline.stage_executor.contracts import PRD_CONTRACT
from hermes_pipeline.stage_executor.prd import PRD_BYTES, PrdGate, PrdStage

_RECORDED = "2026-01-01T00:00:00Z"
_SRC = Path(__file__).resolve().parents[2] / "src" / "hermes_pipeline"
_PRD = _SRC / "stage_executor" / "prd.py"
_CONTROLLER = _SRC / "controller"
_FORBIDDEN = frozenset({"langgraph", "subprocess", "os", "codex", "opencode", "chrome"})


def _actor(principal_id: str) -> Actor:
    return Actor(
        principal_id=principal_id,
        provider="CLI",
        provider_actor_id=principal_id,
    )


def _open_pipeline() -> tuple[RequirementIntake, KernelController]:
    store = MemoryKernelStore()
    controller = KernelController(store, recorded_at=_RECORDED)
    registry = ProjectRegistry()
    registry.register("prj_demo", "Demo")
    registry.admit("prj_demo", "alice", "CONTRIBUTOR")
    intake = RequirementIntake(registry, controller, recorded_at=_RECORDED)
    receipt = intake.confirm(
        workspace_id="ws_demo",
        project_id="prj_demo",
        pipeline_id="pl_demo",
        actor=_actor("alice"),
        text="need a login page",
        command_id="cmd_intake_alice",
    )
    assert receipt.status == "ACCEPTED"
    return intake, controller


def _planner(runtime: RuntimeFamily = "fake", model: str = "fake-prd") -> BindingTable:
    return BindingTable({"planner": AgentBinding("planner", runtime, model)})


def _cas_ids(root: Path) -> list[str]:
    manifests = root / "manifests"
    if not manifests.is_dir():
        return []
    return sorted(path.stem for path in manifests.glob("art_*.json"))


def test_open_pipeline_writes_prd_and_gate_passes(tmp_path: Path) -> None:
    intake, controller = _open_pipeline()
    artifacts = LocalCasArtifacts(tmp_path)
    stage = PrdStage(_planner(), artifacts)
    result = stage.run("pl_demo", "ws_demo", "prj_demo")
    assert result.status == "COMPLETED"
    assert result.artifact_id is not None
    assert artifacts.open(result.artifact_id) == PRD_BYTES
    assert artifacts.verify(result.artifact_id).ok is True
    verdict = PrdGate(controller, artifacts).evaluate(
        pipeline_id="pl_demo",
        workspace_id="ws_demo",
        artifact_id=result.artifact_id,
    )
    assert verdict.status == "PASS"
    assert intake.read("pl_demo", "ws_demo").status == "OPEN"


class _TextPlanner:
    def __init__(self, text: str) -> None:
        self.text = text
        self.prompts: list[str] = []

    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        self.prompts.append(request.prompt)
        return RuntimeHandle(runtime_id=request.runtime_id, status="COMPLETED")

    def signal(self, runtime_id: str) -> RuntimeSignalReceipt:
        del runtime_id
        return RuntimeSignalReceipt(ok=False, code="UNSUPPORTED")

    def inspect(self, runtime_id: str) -> RuntimeSnapshot:
        return RuntimeSnapshot(runtime_id=runtime_id, status="COMPLETED")

    def collect(self, runtime_id: str) -> RuntimeOutcome:
        return RuntimeOutcome(
            runtime_id=runtime_id, status="COMPLETED", final_text=self.text
        )


def test_opencode_planner_without_broker_is_denied(tmp_path: Path) -> None:
    artifacts = LocalCasArtifacts(tmp_path)
    result = PrdStage(_planner("opencode", "grok-4.6"), artifacts).run(
        "pl_demo", "ws_demo", "prj_demo"
    )
    assert result.status == "DENIED"
    assert result.artifact_id is None
    assert _cas_ids(tmp_path) == []


def test_bound_planner_stdout_without_named_file_is_denied(tmp_path: Path) -> None:
    artifacts = LocalCasArtifacts(tmp_path)
    planner = _TextPlanner("real prd body")
    result = PrdStage(_planner("opencode", "grok-4.6"), artifacts, planner).run(
        "pl_demo", "ws_demo", "prj_demo", prompt="Write a PRD"
    )
    assert result.status == "DENIED"
    assert result.artifact_id is None
    assert _cas_ids(tmp_path) == []
    assert planner.prompts == ["Write a PRD"]


def test_bound_planner_named_file_harvested_after_failed_launch(
    tmp_path: Path,
) -> None:
    artifacts = LocalCasArtifacts(tmp_path / "cas")
    folder = tmp_path / "plans"
    folder.mkdir()

    class _FailThenFile(_TextPlanner):
        def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
            (folder / "PRD.md").write_text("# harvested\n", encoding="utf-8")
            return RuntimeHandle(runtime_id=request.runtime_id, status="FAILED")

    result = PrdStage(
        _planner("opencode", "grok-4.6"), artifacts, _FailThenFile(""), folder
    ).run("pl_demo", "ws_demo", "prj_demo")
    assert result.status == "COMPLETED"
    assert result.artifact_id is not None
    assert b"# harvested" in artifacts.open(result.artifact_id)


def test_bound_planner_file_becomes_prd_when_stdout_empty(tmp_path: Path) -> None:
    artifacts = LocalCasArtifacts(tmp_path / "cas")
    folder = tmp_path / "plans"
    folder.mkdir()
    (folder / "PRD.md").write_text("file prd", encoding="utf-8")
    result = PrdStage(
        _planner("opencode", "grok-4.6"), artifacts, _TextPlanner(""), folder
    ).run("pl_demo", "ws_demo", "prj_demo")
    assert result.status == "COMPLETED"
    assert result.artifact_id is not None
    assert artifacts.open(result.artifact_id) == b"file prd"


def test_missing_planner_binding_is_fail_closed(tmp_path: Path) -> None:
    artifacts = LocalCasArtifacts(tmp_path)
    result = PrdStage(BindingTable({}), artifacts).run("pl_demo", "ws_demo", "prj_demo")
    assert result.status == "DENIED"
    assert result.artifact_id is None
    assert _cas_ids(tmp_path) == []


def test_gate_fails_when_prd_is_duty_echo(tmp_path: Path) -> None:
    _, controller = _open_pipeline()
    artifacts = LocalCasArtifacts(tmp_path)
    record = artifacts.put(ArtifactPutRequest(payload=PRD_CONTRACT.encode("utf-8")))
    verdict = PrdGate(controller, artifacts).evaluate(
        pipeline_id="pl_demo",
        workspace_id="ws_demo",
        artifact_id=record.artifact_id,
    )
    assert verdict.status == "FAIL"


def test_gate_fails_without_artifact(tmp_path: Path) -> None:
    _, controller = _open_pipeline()
    verdict = PrdGate(controller, LocalCasArtifacts(tmp_path)).evaluate(
        pipeline_id="pl_demo",
        workspace_id="ws_demo",
        artifact_id=None,
    )
    assert verdict.status == "FAIL"


def test_gate_fails_when_verify_fails(tmp_path: Path) -> None:
    _, controller = _open_pipeline()
    artifacts = LocalCasArtifacts(tmp_path)
    result = PrdStage(_planner(), artifacts).run("pl_demo", "ws_demo", "prj_demo")
    assert result.artifact_id is not None
    digest = result.artifact_id.removeprefix("art_")
    (tmp_path / "blobs" / digest).write_bytes(b"tampered")
    verdict = PrdGate(controller, artifacts).evaluate(
        pipeline_id="pl_demo",
        workspace_id="ws_demo",
        artifact_id=result.artifact_id,
    )
    assert verdict.status == "FAIL"


def test_gate_fails_when_pipeline_is_not_open(tmp_path: Path) -> None:
    store = MemoryKernelStore()
    controller = KernelController(store, recorded_at=_RECORDED)
    artifacts = LocalCasArtifacts(tmp_path)
    result = PrdStage(_planner(), artifacts).run("pl_demo", "ws_demo", "prj_demo")
    verdict = PrdGate(controller, artifacts).evaluate(
        pipeline_id="pl_demo",
        workspace_id="ws_demo",
        artifact_id=result.artifact_id,
    )
    assert verdict.status == "FAIL"


def test_new_store_on_same_cas_root_still_passes(tmp_path: Path) -> None:
    _, controller = _open_pipeline()
    first = LocalCasArtifacts(tmp_path)
    result = PrdStage(_planner(), first).run("pl_demo", "ws_demo", "prj_demo")
    del first
    second = LocalCasArtifacts(tmp_path)
    verdict = PrdGate(controller, second).evaluate(
        pipeline_id="pl_demo",
        workspace_id="ws_demo",
        artifact_id=result.artifact_id,
    )
    assert verdict.status == "PASS"
    assert result.artifact_id is not None
    assert second.open(result.artifact_id) == PRD_BYTES


def test_prd_does_not_import_langgraph_subprocess_os_or_vendors() -> None:
    tree = ast.parse(_PRD.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint(_FORBIDDEN)


def test_controller_does_not_import_prd_pathlib_or_cas() -> None:
    forbidden = ("prd", "pathlib", "local_cas")
    for path in _CONTROLLER.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            assert all(token not in name for token in forbidden for name in names)
