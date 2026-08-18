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
    restarted = KernelBridge(tmp_path, _Inner())
    again = restarted.process(
        "cmd_read_after",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert again["status"] == "OPEN"
    assert again["revision"] == "1" or again["revision"] == 1


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
    assert view["requirement_text"] == "need a login page"
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
    assert view["approval_status"] == "PENDING"
    assert "dev_status" not in view


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
    assert view["approval_status"] == "PENDING"
    assert "candidate_sha" not in view
    approved = first.process(
        "cmd_ok",
        {
            "op": "approve",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert approved["ok"] is True
    view = first.process(
        "cmd_read_after",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view["approval_status"] == "APPROVED"
    assert view["approver_id"] == "operator"
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
    assert view["verify_status"] == "DENIED"


def test_submit_with_verify_bindings_delivers(tmp_path: Path) -> None:
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
    for role, model in (
        ("planner", "fake-prd"),
        ("executor", "fake-dev"),
        ("e2e", "fake-e2e"),
        ("reviewer", "fake-acc"),
    ):
        first.process(
            f"cmd_bind_{role}",
            {"op": "bind", "role": role, "runtime": "fake", "model": model},
        )
    first.process(
        "cmd_all",
        {
            "text": "need a login page",
            "workspace_id": "ws_cli",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    first.process(
        "cmd_ok",
        {
            "op": "approve",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    view = first.process(
        "cmd_read_view",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view["verify_status"] == "READY"
    assert view["branch"] == "hermes/prj_cli/pl_cli"
    assert view["action"] == "RECORDED"
    assert len(str(view["head_sha"])) == 64
    second = KernelBridge(tmp_path, _Inner())
    again = second.process(
        "cmd_read_2",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert again["verify_status"] == "READY"
    assert again["branch"] == "hermes/prj_cli/pl_cli"


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


def test_github_repo_persists_and_mirrors_pr(tmp_path: Path) -> None:
    first = KernelBridge(tmp_path, _Inner())
    bound = first.process("cmd_gh", {"op": "github", "repo": "acme/app"})
    assert bound["ok"] is True

    def _transport(
        method: str,
        path: str,
        headers: dict[str, str],
        body: dict[str, object],
    ) -> tuple[int, object]:
        del method, path, headers, body
        return 201, {
            "number": 9,
            "html_url": "https://github.com/acme/app/pull/9",
        }

    first.enable_github("tok_secret", _transport)
    recorded = first.process(
        "cmd_deliver",
        {
            "op": "deliver",
            "sha": "c" * 64,
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
        },
    )
    assert recorded["pr_number"] == 9
    assert recorded["pr_url"] == "https://github.com/acme/app/pull/9"
    assert "tok_secret" not in str(recorded)
    second = KernelBridge(tmp_path, _Inner())
    view = second.process(
        "cmd_read_view",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view["github_repo"] == "acme/app"
    assert view["pr_url"] == "https://github.com/acme/app/pull/9"


def test_runtimes_lists_pin_names_only(tmp_path: Path) -> None:
    import json

    exe = tmp_path / "claude"
    exe.write_text("x", encoding="utf-8")
    (tmp_path / "descriptor").mkdir(parents=True)
    (tmp_path / "descriptor" / "runtimes.json").write_text(
        json.dumps({"claude": str(exe)}),
        encoding="utf-8",
    )
    bridge = KernelBridge(tmp_path, _Inner())
    listed = bridge.process("cmd_rt", {"op": "runtimes"})
    assert listed["ok"] is True
    assert listed["runtimes"] == ["claude"]
    assert "C:" not in str(listed["runtimes"])


def test_legacy_payload_delegates(tmp_path: Path) -> None:
    bridge = KernelBridge(tmp_path, _Inner())
    reply = bridge.process("cmd_legacy", {"delta": 1})
    assert reply["legacy"] is True
