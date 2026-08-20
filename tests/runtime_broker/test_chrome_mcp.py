from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Literal

from hermes_pipeline.contracts.runtime import CapabilityProfile
from hermes_pipeline.runtime_broker.binding import (
    AgentBinding,
    BindingTable,
    BoundRuntimeBroker,
)
from hermes_pipeline.runtime_broker.capability import compile_profile
from hermes_pipeline.runtime_broker.chrome_mcp import (
    ALLOWED_TOOLS,
    ChromeMcpRuntime,
    closed_mcp_argv,
)
from hermes_pipeline.runtime_broker.fake import FakeRuntimeBroker
from hermes_pipeline.runtime_broker.opencode_adapter import OpenCodeAdapter
from hermes_pipeline.runtime_broker.ports import (
    RuntimeBrokerPort,
    RuntimeLaunchRequest,
)

_SRC = Path(__file__).resolve().parents[2] / "src" / "hermes_pipeline"
_RUNTIME = _SRC / "runtime_broker" / "chrome_mcp.py"
_CONTROLLER = _SRC / "controller"
_FORBIDDEN_SPIKES = frozenset(
    {
        "hermes_pipeline.runtime_broker._e2e",
        "hermes_pipeline.runtime_broker._host",
        "hermes_pipeline.runtime_broker.controlled_e2e",
        "hermes_pipeline.runtime_broker._identity",
        "_e2e",
        "_host",
        "controlled_e2e",
        "_identity",
    }
)
_NAV = "chrome-devtools_navigate_page"
_EVAL = "chrome-devtools_evaluate_script"


class _FakeMcp:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def call(self, name: str, arguments: dict[str, object]) -> str:
        del arguments
        self.calls.append(name)
        return "ok"


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


def _e2e_profile(
    *, browser: Literal["NONE", "CHROME_DEVTOOLS_MCP"]
) -> CapabilityProfile:
    return compile_profile(
        write_roots=["/work"],
        browser=browser,
        stage_type="E2E",
    )


def test_runtime_is_a_runtime_broker_port() -> None:
    assert isinstance(ChromeMcpRuntime(), RuntimeBrokerPort)


def test_e2e_binds_to_opencode_model(tmp_path: Path) -> None:
    script = tmp_path / "fake_opencode.py"
    script.write_text(
        "import json\nprint(json.dumps({'type':'session.status','status':'idle'}))\n",
        encoding="utf-8",
    )
    table = BindingTable({"e2e": AgentBinding("e2e", "opencode", "grok-4.6")})
    opencode = OpenCodeAdapter(executable=str(script))
    broker = BoundRuntimeBroker(
        table, {"opencode": opencode, "fake": FakeRuntimeBroker()}
    )
    handle = broker.launch(RuntimeLaunchRequest(runtime_id="rt-e2e", role="e2e"))
    assert handle.status == "COMPLETED"
    assert "--model" in opencode.last_argv
    assert "grok-4.6" in opencode.last_argv


def test_browser_none_is_unsupported_and_does_not_spawn() -> None:
    runtime = ChromeMcpRuntime(profile=_e2e_profile(browser="NONE"), mcp=_FakeMcp())
    handle = runtime.launch(RuntimeLaunchRequest(runtime_id="rt-none"))
    assert handle.status == "UNSUPPORTED"
    assert runtime.spawned is False
    assert runtime.calls == []
    assert runtime.inspect("rt-none").status == "UNSUPPORTED"
    assert runtime.collect("rt-none").status == "UNSUPPORTED"
    assert runtime.collect("rt-none").detail == "browser not allowed"


def test_chrome_profile_without_fake_mcp_is_unsupported() -> None:
    runtime = ChromeMcpRuntime(profile=_e2e_profile(browser="CHROME_DEVTOOLS_MCP"))
    handle = runtime.launch(RuntimeLaunchRequest(runtime_id="rt-bare"))
    assert handle.status == "UNSUPPORTED"
    assert runtime.spawned is False
    assert runtime.calls == []
    assert runtime.last_argv == []
    assert runtime.collect("rt-bare").detail == "no_official_checksum"


def test_injected_fake_mcp_records_allowed_calls() -> None:
    mcp = _FakeMcp()
    runtime = ChromeMcpRuntime(
        profile=_e2e_profile(browser="CHROME_DEVTOOLS_MCP"), mcp=mcp
    )
    handle = runtime.launch(RuntimeLaunchRequest(runtime_id="rt-ok"))
    assert handle.status == "COMPLETED"
    assert runtime.spawned is False
    assert runtime.calls == [_NAV, _EVAL]
    assert mcp.calls == [_NAV, _EVAL]
    assert runtime.collect("rt-ok").status == "COMPLETED"


def test_injected_script_records_allowed_calls(tmp_path: Path) -> None:
    script = tmp_path / "fake_mcp.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    runtime = ChromeMcpRuntime(
        profile=_e2e_profile(browser="CHROME_DEVTOOLS_MCP"),
        executable=str(script),
    )
    handle = runtime.launch(RuntimeLaunchRequest(runtime_id="rt-script"))
    assert handle.status == "COMPLETED"
    assert runtime.spawned is True
    assert runtime.calls == [_NAV, _EVAL]
    assert _EVAL in runtime.last_argv


def test_other_tool_names_are_denied() -> None:
    mcp = _FakeMcp()
    runtime = ChromeMcpRuntime(
        profile=_e2e_profile(browser="CHROME_DEVTOOLS_MCP"), mcp=mcp
    )
    assert runtime.authorize(_NAV) is True
    assert runtime.authorize(_EVAL) is True
    assert runtime.authorize("chrome-devtools_take_screenshot") is False
    assert runtime.authorize("bash") is False
    assert runtime.invoke("chrome-devtools_take_screenshot") is False
    assert runtime.invoke("bash") is False
    assert runtime.calls == []
    assert mcp.calls == []
    assert runtime.spawned is False
    assert {_NAV, _EVAL} == ALLOWED_TOOLS


def test_e2e_opencode_plus_optional_chrome(tmp_path: Path) -> None:
    script = tmp_path / "fake_opencode.py"
    script.write_text(
        "import json\nprint(json.dumps({'type':'session.status','status':'idle'}))\n",
        encoding="utf-8",
    )
    table = BindingTable({"e2e": AgentBinding("e2e", "opencode", "grok-4.6")})
    opencode = OpenCodeAdapter(executable=str(script))
    broker = BoundRuntimeBroker(table, {"opencode": opencode})
    chrome = ChromeMcpRuntime(
        profile=_e2e_profile(browser="CHROME_DEVTOOLS_MCP"), mcp=_FakeMcp()
    )
    agent = broker.launch(RuntimeLaunchRequest(runtime_id="rt-agent", role="e2e"))
    browser = chrome.launch(RuntimeLaunchRequest(runtime_id="rt-browser"))
    assert agent.status == "COMPLETED"
    assert browser.status == "COMPLETED"
    assert "grok-4.6" in opencode.last_argv
    assert chrome.calls == [_NAV, _EVAL]


def test_planner_binding_is_unchanged(tmp_path: Path) -> None:
    script = tmp_path / "fake_opencode.py"
    script.write_text(
        "import json\nprint(json.dumps({'type':'session.status','status':'idle'}))\n",
        encoding="utf-8",
    )
    table = BindingTable({"planner": AgentBinding("planner", "opencode", "grok-4.6")})
    opencode = OpenCodeAdapter(executable=str(script))
    broker = BoundRuntimeBroker(table, {"opencode": opencode})
    handle = broker.launch(RuntimeLaunchRequest(runtime_id="rt-p", role="planner"))
    assert handle.status == "COMPLETED"
    assert "grok-4.6" in opencode.last_argv


def _place_closed_tools(root: Path) -> None:
    if sys.platform == "win32":
        node = root / "tools/node/windows-x64/node-v22.23.2-win-x64/node.exe"
        chrome = (
            root
            / "tools/browser-runtime/chrome-for-testing/win64/chrome-win64/chrome.exe"
        )
    else:
        node = root / "tools/node/linux-x64/node-v22.23.2-linux-x64/bin/node"
        chrome = (
            root
            / "tools/browser-runtime/chrome-for-testing/linux64/chrome-linux64/chrome"
        )
    mcp = (
        root
        / "tools/browser-runtime/project/node_modules/"
        / "chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js"
    )
    for path in (node, chrome, mcp):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")


def test_closed_argv_uses_locked_paths(tmp_path: Path) -> None:
    _place_closed_tools(tmp_path)
    argv = closed_mcp_argv(tmp_path, 4317)
    assert argv is not None
    assert argv[2:] == [
        "--headless",
        "--isolated",
        "--executable-path",
        argv[5],
        "--allowed-url-pattern",
        "http://127.0.0.1:4317/*",
        "--no-usage-statistics",
        "--no-performance-crux",
    ]
    assert argv[0].endswith("node.exe") or argv[0].endswith("node")
    assert argv[1].endswith("chrome-devtools-mcp.js")
    assert "chrome" in Path(argv[5]).name.lower()


def test_closed_argv_missing_tools_is_none(tmp_path: Path) -> None:
    assert closed_mcp_argv(tmp_path, 80) is None


def test_runtime_does_not_import_keep_marked_probes() -> None:
    imported = _imported_names(_RUNTIME)
    assert imported.isdisjoint(_FORBIDDEN_SPIKES)
    joined = " ".join(imported)
    assert all(name not in joined for name in _FORBIDDEN_SPIKES)


def test_controller_does_not_import_chrome_mcp() -> None:
    for path in _CONTROLLER.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        imported = _imported_names(path)
        joined = " ".join(imported)
        assert "chrome_mcp" not in imported
        assert "chrome_mcp" not in joined
