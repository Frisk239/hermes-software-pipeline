from __future__ import annotations

import ast
from pathlib import Path

from hermes_pipeline.runtime_broker.capability import compile_profile
from hermes_pipeline.runtime_broker.codex_adapter import CodexAdapter
from hermes_pipeline.runtime_broker.ports import (
    RuntimeBrokerPort,
    RuntimeLaunchRequest,
)

_SRC = Path(__file__).resolve().parents[2] / "src" / "hermes_pipeline"
_ADAPTER = _SRC / "runtime_broker" / "codex_adapter.py"
_CONTROLLER = _SRC / "controller"
_FORBIDDEN_SPIKES = frozenset(
    {
        "hermes_pipeline.runtime_broker._codex",
        "hermes_pipeline.runtime_broker._identity",
        "hermes_pipeline.runtime_broker._e2e",
        "_codex",
        "_identity",
        "_e2e",
    }
)
_OK_SCRIPT = """\
import json
print(json.dumps({
    "type": "item.completed",
    "status": "completed",
    "item": {"content": [{"type": "output_text", "text": "hello-final"}]},
}))
"""
_CRED_SCRIPT = """\
import json
print(json.dumps({"type": "error", "error": {"message": "missing credential"}}))
"""
_DANGEROUS = "--dangerously-bypass-approvals-and-sandbox"


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(alias.name for alias in node.names)
    return names


def _write_script(path: Path, body: str) -> str:
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_adapter_is_a_runtime_broker_port() -> None:
    assert isinstance(CodexAdapter(executable=None), RuntimeBrokerPort)


def test_missing_executable_is_unsupported_and_does_not_spawn(tmp_path: Path) -> None:
    adapter = CodexAdapter(executable=str(tmp_path / "missing-codex"))
    handle = adapter.launch(RuntimeLaunchRequest(runtime_id="rt-missing"))
    assert handle.status == "UNSUPPORTED"
    assert adapter.spawned is False
    assert adapter.last_argv == []
    assert adapter.inspect("rt-missing").status == "UNSUPPORTED"
    assert adapter.collect("rt-missing").status == "UNSUPPORTED"


def test_jsonl_completed_collects_final_text(tmp_path: Path) -> None:
    script = _write_script(tmp_path / "fake_codex.py", _OK_SCRIPT)
    adapter = CodexAdapter(executable=script)
    handle = adapter.launch(RuntimeLaunchRequest(runtime_id="rt-ok"))
    assert handle.status == "COMPLETED"
    assert adapter.spawned is True
    outcome = adapter.collect("rt-ok")
    assert outcome.status == "COMPLETED"
    assert outcome.final_text == "hello-final"
    assert outcome.detail == "ok"


def test_jsonl_credential_error_is_failed(tmp_path: Path) -> None:
    script = _write_script(tmp_path / "fake_codex.py", _CRED_SCRIPT)
    adapter = CodexAdapter(executable=script)
    handle = adapter.launch(RuntimeLaunchRequest(runtime_id="rt-cred"))
    assert handle.status == "FAILED"
    outcome = adapter.collect("rt-cred")
    assert outcome.status == "FAILED"
    assert outcome.detail == "no_credential"


def test_signal_marks_cancelled(tmp_path: Path) -> None:
    script = _write_script(tmp_path / "fake_codex.py", _OK_SCRIPT)
    adapter = CodexAdapter(executable=script)
    adapter.launch(RuntimeLaunchRequest(runtime_id="rt-stop"))
    receipt = adapter.signal("rt-stop")
    assert receipt.ok is True
    assert adapter.inspect("rt-stop").status == "CANCELLED"
    assert adapter.collect("rt-stop").status == "CANCELLED"
    assert adapter.collect("rt-stop").detail == "cancelled"


def test_argv_requires_json_and_sandbox(tmp_path: Path) -> None:
    script = _write_script(tmp_path / "fake_codex.py", _OK_SCRIPT)
    adapter = CodexAdapter(executable=script)
    adapter.launch(RuntimeLaunchRequest(runtime_id="rt-argv"))
    assert "--json" in adapter.last_argv
    assert "--sandbox" in adapter.last_argv
    assert _DANGEROUS not in adapter.last_argv


def test_denied_profile_does_not_spawn(tmp_path: Path) -> None:
    script = _write_script(tmp_path / "fake_codex.py", _OK_SCRIPT)
    profile = compile_profile(write_roots=["/work"], executables=[])
    adapter = CodexAdapter(executable=script, profile=profile)
    handle = adapter.launch(RuntimeLaunchRequest(runtime_id="rt-deny"))
    assert handle.status == "UNSUPPORTED"
    assert adapter.spawned is False


def test_allowed_profile_can_launch_injected_script(tmp_path: Path) -> None:
    script = _write_script(tmp_path / "fake_codex.py", _OK_SCRIPT)
    profile = compile_profile(write_roots=["/work"], executables=["codex"])
    adapter = CodexAdapter(executable=script, profile=profile)
    handle = adapter.launch(RuntimeLaunchRequest(runtime_id="rt-allow"))
    assert handle.status == "COMPLETED"
    assert adapter.spawned is True


def test_adapter_does_not_import_keep_marked_probes() -> None:
    imported = _imported_names(_ADAPTER)
    assert imported.isdisjoint(_FORBIDDEN_SPIKES)
    joined = " ".join(imported)
    assert all(name not in joined for name in _FORBIDDEN_SPIKES)


def test_controller_does_not_import_codex_adapter() -> None:
    for path in _CONTROLLER.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        imported = _imported_names(path)
        joined = " ".join(imported)
        assert "codex_adapter" not in imported
        assert "codex_adapter" not in joined
