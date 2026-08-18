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
    assert view["prd_status"] == "DENIED"
    assert view["prd_id"] == ""


def test_submit_with_planner_records_prd(tmp_path: Path) -> None:
    first = KernelBridge(tmp_path, _Inner())
    first.process("cmd_reg", {"op": "register", "project_id": "prj_cli", "name": "Cli"})
    first.process(
        "cmd_adm",
        {
            "op": "admit",
            "project_id": "prj_cli",
            "principal_id": "operator",
            "role": "CONTRIBUTOR",
        },
    )
    first.process(
        "cmd_bind",
        {"op": "bind", "role": "planner", "runtime": "fake", "model": "fake-prd"},
    )
    receipt = first.process(
        "cmd_prd",
        {
            "text": "need a login page",
            "workspace_id": "ws_cli",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert receipt["status"] == "ACCEPTED"
    view = first.process(
        "cmd_read_view",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view["status"] == "OPEN"
    assert view["prd_status"] == "COMPLETED"
    assert view["prd_gate"] == "PASS"
    assert str(view["prd_id"]).startswith("art_")
    assert view["arch_status"] == "COMPLETED"
    assert view["arch_gate"] == "PASS"
    assert str(view["design_id"]).startswith("art_")
    assert str(view["testplan_id"]).startswith("art_")
    second = KernelBridge(tmp_path, _Inner())
    again = second.process(
        "cmd_read_2",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert again["prd_id"] == view["prd_id"]
    assert again["prd_status"] == "COMPLETED"
    assert again["design_id"] == view["design_id"]
    assert again["arch_status"] == "COMPLETED"
    assert view["dev_status"] == "DENIED"


def test_submit_with_executor_records_candidate(tmp_path: Path) -> None:
    first = KernelBridge(tmp_path, _Inner())
    first.process("cmd_reg", {"op": "register", "project_id": "prj_cli", "name": "Cli"})
    first.process(
        "cmd_adm",
        {
            "op": "admit",
            "project_id": "prj_cli",
            "principal_id": "operator",
            "role": "CONTRIBUTOR",
        },
    )
    first.process(
        "cmd_bind_p",
        {"op": "bind", "role": "planner", "runtime": "fake", "model": "fake-prd"},
    )
    first.process(
        "cmd_bind_e",
        {"op": "bind", "role": "executor", "runtime": "fake", "model": "fake-dev"},
    )
    first.process(
        "cmd_dev",
        {
            "text": "need a login page",
            "workspace_id": "ws_cli",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    view = first.process(
        "cmd_read_view",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view["dev_status"] == "COMPLETED"
    assert view["candidate_gate"] == "PASS"
    assert len(str(view["candidate_sha"])) == 64
    assert view["candidate_path"] == "src/app.py"
    second = KernelBridge(tmp_path, _Inner())
    again = second.process(
        "cmd_read_2",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert again["candidate_sha"] == view["candidate_sha"]


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


def test_deliver_persists_and_read_shows_pr(tmp_path: Path) -> None:
    first = KernelBridge(tmp_path, _Inner())
    recorded = first.process(
        "cmd_deliver",
        {
            "op": "deliver",
            "sha": "c" * 64,
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
        },
    )
    assert recorded["ok"] is True
    assert recorded["branch"] == "hermes/prj_cli/pl_cli"
    assert recorded["pr_number"] == 1
    assert recorded["head_sha"] == "c" * 64
    again = first.process(
        "cmd_deliver",
        {
            "op": "deliver",
            "sha": "c" * 64,
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
        },
    )
    assert again["pr_number"] == 1
    second = KernelBridge(tmp_path, _Inner())
    view = second.process(
        "cmd_read_view",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view["branch"] == "hermes/prj_cli/pl_cli"
    assert view["head_sha"] == "c" * 64


def test_observe_events_persist_and_dedupe(tmp_path: Path) -> None:
    first = KernelBridge(tmp_path, _Inner())
    first.process(
        "cmd_deliver",
        {
            "op": "deliver",
            "sha": "c" * 64,
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
        },
    )
    seen = first.process(
        "cmd_obs",
        {
            "op": "deliver",
            "pipeline_id": "pl_cli",
            "event_id": "evt_1",
            "check_status": "success",
            "review_status": "approved",
            "queue_status": "queued",
        },
    )
    assert seen["check_status"] == "success"
    first.process(
        "cmd_dup",
        {
            "op": "deliver",
            "pipeline_id": "pl_cli",
            "event_id": "evt_1",
            "check_status": "failure",
        },
    )
    second = KernelBridge(tmp_path, _Inner())
    view = second.process(
        "cmd_read_view",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view["check_status"] == "success"
    assert view["review_status"] == "approved"
    assert view["queue_status"] == "queued"


def test_legacy_payload_delegates(tmp_path: Path) -> None:
    bridge = KernelBridge(tmp_path, _Inner())
    reply = bridge.process("cmd_legacy", {"delta": 1})
    assert reply["legacy"] is True
