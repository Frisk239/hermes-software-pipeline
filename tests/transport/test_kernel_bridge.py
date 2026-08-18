from __future__ import annotations

from pathlib import Path

from hermes_pipeline.transport.kernel_bridge import KernelBridge


class _Inner:
    def process(self, command_id: str, payload: dict[str, object]) -> dict[str, object]:
        return {"command_id": command_id, "legacy": True, "keys": sorted(payload)}


def test_submit_without_project_is_not_found(tmp_path: Path) -> None:
    bridge = KernelBridge(tmp_path, _Inner())
    receipt = bridge.process(
        "cmd_cli_one",
        {
            "text": "need a login page",
            "workspace_id": "ws_cli",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert receipt["status"] == "REJECTED"
    assert receipt["error"]["code"] == "NOT_FOUND"


def test_register_admit_submit_read(tmp_path: Path) -> None:
    bridge = KernelBridge(tmp_path, _Inner())
    assert bridge.process(
        "cmd_reg", {"op": "register", "project_id": "prj_cli", "name": "Cli"}
    )["ok"]
    assert bridge.process(
        "cmd_adm",
        {
            "op": "admit",
            "project_id": "prj_cli",
            "principal_id": "operator",
            "role": "CONTRIBUTOR",
        },
    )["ok"]
    receipt = bridge.process(
        "cmd_cli_one",
        {
            "text": "need a login page",
            "workspace_id": "ws_cli",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert receipt["status"] == "ACCEPTED"
    view = bridge.process(
        "cmd_read_view",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view["status"] == "OPEN"


def test_bindings_persist(tmp_path: Path) -> None:
    first = KernelBridge(tmp_path, _Inner())
    bound = first.process(
        "cmd_bind",
        {
            "op": "bind",
            "role": "planner",
            "runtime": "opencode",
            "model": "grok-4.6",
        },
    )
    assert bound["ok"] is True
    second = KernelBridge(tmp_path, _Inner())
    listed = second.process("cmd_list", {"op": "bindings"})
    assert listed["bindings"]["planner"]["model"] == "grok-4.6"


def test_legacy_payload_delegates(tmp_path: Path) -> None:
    bridge = KernelBridge(tmp_path, _Inner())
    reply = bridge.process("cmd_legacy", {"delta": 1})
    assert reply["legacy"] is True
