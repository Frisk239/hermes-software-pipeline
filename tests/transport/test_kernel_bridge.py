from __future__ import annotations

from pathlib import Path

from hermes_pipeline.transport.kernel_bridge import KernelBridge


class _Inner:
    def process(self, command_id: str, payload: dict[str, object]) -> dict[str, object]:
        return {"command_id": command_id, "legacy": True, "keys": sorted(payload)}


def test_text_payload_confirms_and_read_is_open(tmp_path: Path) -> None:
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
    assert receipt["status"] == "ACCEPTED"
    view = bridge.process(
        "cmd_read_view",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view["status"] == "OPEN"
    assert view["revision"] == 1


def test_legacy_payload_delegates(tmp_path: Path) -> None:
    bridge = KernelBridge(tmp_path, _Inner())
    reply = bridge.process("cmd_legacy", {"delta": 1})
    assert reply["legacy"] is True
