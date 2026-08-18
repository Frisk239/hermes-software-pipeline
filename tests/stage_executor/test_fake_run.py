from __future__ import annotations

import ast
from pathlib import Path

from hermes_pipeline.artifacts import LocalCasArtifacts
from hermes_pipeline.runtime_broker import FakeRuntimeBroker
from hermes_pipeline.runtime_broker.capability import compile_profile
from hermes_pipeline.stage_executor.fake_run import FAKE_STAGE_BYTES, FakeStageRun
from hermes_pipeline.stage_executor.ports import (
    ExecutionCancelRequest,
    ExecutionInput,
    StageExecutorPort,
)

_SRC = Path(__file__).resolve().parents[2] / "src" / "hermes_pipeline"
_FAKE_RUN = _SRC / "stage_executor" / "fake_run.py"
_CONTROLLER = _SRC / "controller"
_FORBIDDEN = frozenset({"langgraph", "subprocess", "os", "codex", "opencode", "chrome"})


def _allowed_run(cas_root: Path) -> FakeStageRun:
    broker = FakeRuntimeBroker()
    artifacts = LocalCasArtifacts(cas_root)
    profile = compile_profile(
        write_roots=[str(cas_root)],
        side_effects=["LOCAL_TEST"],
        stage_type="DEVELOPMENT",
    )
    return FakeStageRun(broker, artifacts, profile)


def _cas_artifact_ids(root: Path) -> list[str]:
    manifests = root / "manifests"
    if not manifests.is_dir():
        return []
    return sorted(path.stem for path in manifests.glob("art_*.json"))


def test_fake_stage_run_is_a_stage_executor_port(tmp_path: Path) -> None:
    stage = FakeStageRun(
        FakeRuntimeBroker(),
        LocalCasArtifacts(tmp_path),
        compile_profile(write_roots=[str(tmp_path)]),
    )
    assert isinstance(stage, StageExecutorPort)


def test_allowed_profile_launches_once_writes_cas_and_completes(tmp_path: Path) -> None:
    broker = FakeRuntimeBroker()
    artifacts = LocalCasArtifacts(tmp_path)
    profile = compile_profile(
        write_roots=[str(tmp_path)],
        side_effects=["LOCAL_TEST"],
        stage_type="DEVELOPMENT",
    )
    stage = FakeStageRun(broker, artifacts, profile)
    handle = stage.start(ExecutionInput(run_id="run_01"))
    assert handle.status == "COMPLETED"
    assert broker.launched == ["run_01"]
    assert broker.inspect("run_01").status == "FAKE"
    ids = _cas_artifact_ids(tmp_path)
    assert len(ids) == 1
    assert artifacts.verify(ids[0]).ok is True
    assert artifacts.open(ids[0]) == FAKE_STAGE_BYTES
    assert stage.inspect("run_01").status == "COMPLETED"


def test_denied_side_effect_is_fail_closed(tmp_path: Path) -> None:
    broker = FakeRuntimeBroker()
    artifacts = LocalCasArtifacts(tmp_path)
    profile = compile_profile(write_roots=[str(tmp_path)], stage_type="DEVELOPMENT")
    stage = FakeStageRun(broker, artifacts, profile)
    handle = stage.start(ExecutionInput(run_id="run_01"))
    assert handle.status == "DENIED"
    assert stage.inspect("run_01").status == "DENIED"
    assert broker.launched == []
    assert _cas_artifact_ids(tmp_path) == []


def test_cancel_marks_cancelled(tmp_path: Path) -> None:
    stage = _allowed_run(tmp_path)
    stage.start(ExecutionInput(run_id="run_01"))
    receipt = stage.cancel(ExecutionCancelRequest(run_id="run_01"))
    assert receipt.status == "CANCELLED"
    assert stage.inspect("run_01").status == "CANCELLED"


def test_cancel_after_completed_stays_cancelled(tmp_path: Path) -> None:
    stage = _allowed_run(tmp_path)
    assert stage.start(ExecutionInput(run_id="run_01")).status == "COMPLETED"
    stage.cancel(ExecutionCancelRequest(run_id="run_01"))
    assert stage.inspect("run_01").status == "CANCELLED"
    stage.cancel(ExecutionCancelRequest(run_id="run_01"))
    assert stage.inspect("run_01").status == "CANCELLED"


def test_inspect_unknown_is_unsupported(tmp_path: Path) -> None:
    assert _allowed_run(tmp_path).inspect("missing").status == "UNSUPPORTED"


def test_fake_run_does_not_import_langgraph_subprocess_os_or_vendors() -> None:
    tree = ast.parse(_FAKE_RUN.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint(_FORBIDDEN)


def test_controller_does_not_import_fake_run() -> None:
    for path in _CONTROLLER.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            assert all("fake_run" not in name for name in names)
