from __future__ import annotations

from pathlib import Path

from hermes_pipeline.runtime_broker.binding import (
    AgentBinding,
    BindingNotFound,
    BindingTable,
    BoundRuntimeBroker,
)
from hermes_pipeline.runtime_broker.codex_adapter import CodexAdapter
from hermes_pipeline.runtime_broker.fake import FakeRuntimeBroker
from hermes_pipeline.runtime_broker.opencode_adapter import OpenCodeAdapter
from hermes_pipeline.runtime_broker.ports import RuntimeLaunchRequest


def test_resolve_planner_and_executor_bindings() -> None:
    table = BindingTable(
        {
            "planner": AgentBinding("planner", "opencode", "grok-4.6"),
            "executor": AgentBinding("executor", "codex", "gpt-5.6-luna"),
        }
    )
    assert table.resolve("planner") == AgentBinding("planner", "opencode", "grok-4.6")
    assert table.resolve("executor").model == "gpt-5.6-luna"


def test_claude_binding_loads() -> None:
    table = BindingTable.load({"planner": {"runtime": "claude", "model": "opus"}})
    assert table.resolve("planner").runtime == "claude"


def test_missing_role_fails_closed() -> None:
    table = BindingTable({"planner": AgentBinding("planner", "codex", "gpt-5.6-sol")})
    try:
        table.resolve("executor")
    except BindingNotFound:
        return
    raise AssertionError("expected BindingNotFound")


def test_bound_broker_routes_planner_to_opencode_model(tmp_path: Path) -> None:
    script = tmp_path / "fake_opencode.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    table = BindingTable({"planner": AgentBinding("planner", "opencode", "grok-4.6")})
    opencode = OpenCodeAdapter(executable=str(script))
    broker = BoundRuntimeBroker(
        table, {"opencode": opencode, "fake": FakeRuntimeBroker()}
    )
    handle = broker.launch(RuntimeLaunchRequest(runtime_id="rt-p", role="planner"))
    assert handle.status == "COMPLETED"
    assert "--model" in opencode.last_argv
    assert "grok-4.6" in opencode.last_argv


def test_bound_broker_forwards_prompt(tmp_path: Path) -> None:
    script = tmp_path / "fake_opencode.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    table = BindingTable({"planner": AgentBinding("planner", "opencode", "grok-4.6")})
    opencode = OpenCodeAdapter(executable=str(script), cwd=str(tmp_path))
    broker = BoundRuntimeBroker(
        table, {"opencode": opencode, "fake": FakeRuntimeBroker()}
    )
    handle = broker.launch(
        RuntimeLaunchRequest(runtime_id="rt-fwd", role="planner", prompt="Write a PRD")
    )
    assert handle.status == "COMPLETED"
    assert opencode.last_argv[-1] == "Write a PRD"


def test_opencode_nonzero_exit_is_failed(tmp_path: Path) -> None:
    script = tmp_path / "fake_opencode.py"
    script.write_text("raise SystemExit(1)\n", encoding="utf-8")
    adapter = OpenCodeAdapter(executable=str(script), cwd=str(tmp_path))
    handle = adapter.launch(RuntimeLaunchRequest(runtime_id="rt-fail"))
    assert handle.status == "FAILED"


def test_opencode_passes_prompt_as_run_message(tmp_path: Path) -> None:
    script = tmp_path / "fake_opencode.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    adapter = OpenCodeAdapter(executable=str(script), cwd=str(tmp_path))
    handle = adapter.launch(
        RuntimeLaunchRequest(
            runtime_id="rt-msg",
            role="planner",
            model="opencode-go/deepseek-v4-flash",
            prompt="Write a PRD",
        )
    )
    assert handle.status == "COMPLETED"
    assert "--auto" in adapter.last_argv
    assert adapter.last_argv[-1] == "Write a PRD"
    assert "input" not in " ".join(adapter.last_argv)


def test_bound_broker_routes_executor_to_codex_model(tmp_path: Path) -> None:
    script = tmp_path / "fake_codex.py"
    script.write_text(
        "import json\n"
        "print(json.dumps({'type':'turn.completed','status':'completed',"
        "'text':'done'}))\n",
        encoding="utf-8",
    )
    table = BindingTable(
        {"executor": AgentBinding("executor", "codex", "gpt-5.6-luna")}
    )
    codex = CodexAdapter(executable=str(script))
    broker = BoundRuntimeBroker(table, {"codex": codex})
    handle = broker.launch(RuntimeLaunchRequest(runtime_id="rt-e", role="executor"))
    assert handle.status == "COMPLETED"
    assert "--model" in codex.last_argv
    assert "gpt-5.6-luna" in codex.last_argv


def test_unbound_role_is_unsupported() -> None:
    broker = BoundRuntimeBroker(BindingTable({}), {"fake": FakeRuntimeBroker()})
    handle = broker.launch(RuntimeLaunchRequest(runtime_id="rt-x", role="planner"))
    assert handle.status == "UNSUPPORTED"


def test_real_opencode_name_is_not_blocked(tmp_path: Path) -> None:
    exe = tmp_path / "opencode"
    exe.write_text("print('ok')\n", encoding="utf-8")
    adapter = OpenCodeAdapter(executable=str(exe), cwd=str(tmp_path))
    handle = adapter.launch(RuntimeLaunchRequest(runtime_id="rt-real", role="executor"))
    assert handle.status != "UNSUPPORTED"


def test_missing_opencode_binary_is_unsupported() -> None:
    adapter = OpenCodeAdapter(executable=None)
    handle = adapter.launch(RuntimeLaunchRequest(runtime_id="rt-miss", role="executor"))
    assert handle.status == "UNSUPPORTED"
