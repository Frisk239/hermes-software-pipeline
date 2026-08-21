from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import Actor, ControllerCommand
from hermes_pipeline.controller import KernelController
from hermes_pipeline.persistence.kernel_sqlite import SqliteKernelStore
from hermes_pipeline.transport.kernel_bridge import (
    KernelBridge,
    architecture_prompt,
    implement_prompt,
    prd_prompt,
)


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
    assert int(again["revision"]) >= 1
    assert not (tmp_path / "descriptor" / "kernel.json").exists()
    assert (tmp_path / "controller.sqlite").is_file()


def test_read_keeps_prd_from_events_without_prd_json(tmp_path: Path) -> None:
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
    assert (
        bridge.process(
            "cmd_cli_one",
            {
                "text": "need a login page",
                "workspace_id": "ws_cli",
                "project_id": "prj_cli",
                "pipeline_id": "pl_cli",
                "principal_id": "operator",
            },
        )["status"]
        == "ACCEPTED"
    )
    prd_json = tmp_path / "descriptor" / "prd.json"
    if prd_json.exists():
        prd_json.unlink()
    restarted = KernelBridge(tmp_path, _Inner())
    view = restarted.process(
        "cmd_read_events",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view["status"] == "OPEN"
    assert view.get("prd_status") == "DENIED"


def test_restart_does_not_rerecord_prd(tmp_path: Path) -> None:
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
    assert (
        bridge.process(
            "cmd_cli_one",
            {
                "text": "need a login page",
                "workspace_id": "ws_cli",
                "project_id": "prj_cli",
                "pipeline_id": "pl_cli",
                "principal_id": "operator",
            },
        )["status"]
        == "ACCEPTED"
    )
    prd_json = tmp_path / "descriptor" / "prd.json"
    if prd_json.exists():
        prd_json.unlink()
    KernelBridge(tmp_path, _Inner()).process(
        "cmd_read_again",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    store = SqliteKernelStore(str(tmp_path / "controller.sqlite"))
    recorded = [
        event
        for event in store.list_events("ws_cli", "pl_cli")
        if event.event_type == "PRD_RECORDED"
    ]
    store.close()
    assert len(recorded) == 1


def test_approve_is_busy_when_lease_held(tmp_path: Path) -> None:
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
    bridge.process(
        "cmd_cli_one",
        {
            "text": "need a login page",
            "workspace_id": "ws_cli",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    store = SqliteKernelStore(str(tmp_path / "controller.sqlite"))
    KernelController(store, recorded_at="2026-01-01T00:00:00Z").acquire_lease(
        "ws_cli", "pl_cli", "other", int(time.time()), 600
    )
    store.close()
    result = bridge.process(
        "cmd_approve",
        {
            "op": "approve",
            "workspace_id": "ws_cli",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert result["ok"] is False
    assert result["error"] == "busy"


def test_approve_returns_running_when_worker_spawned(tmp_path: Path) -> None:
    marker = tmp_path / "worker.txt"
    script = tmp_path / "worker.py"
    script.write_text(
        "from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text('ok')\n",
        encoding="utf-8",
    )
    document = {
        "inbox": [],
        "events": [
            {
                "event_id": "evt_1",
                "workspace_id": "ws_local",
                "pipeline_id": "pl_run",
                "event_type": "REQUIREMENT_CONFIRMED",
                "payload_json": '{"text":"need login"}',
                "pipeline_revision": 1,
            }
        ],
        "pipelines": [
            {
                "workspace_id": "ws_local",
                "pipeline_id": "pl_run",
                "status": "OPEN",
                "revision": 1,
                "text": "need login",
            }
        ],
        "outbox": [],
        "leases": [],
    }
    (tmp_path / "descriptor").mkdir()
    (tmp_path / "descriptor" / "kernel.json").write_text(
        json.dumps(document), encoding="utf-8"
    )
    (tmp_path / "descriptor" / "prd.json").write_text(
        json.dumps(
            {
                "pl_run": {
                    "prd_id": "art_prd",
                    "prd_status": "COMPLETED",
                    "prd_gate": "PASS",
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "descriptor" / "architecture.json").write_text(
        json.dumps(
            {
                "pl_run": {
                    "design_id": "art_d",
                    "testplan_id": "art_t",
                    "arch_status": "COMPLETED",
                    "arch_gate": "PASS",
                }
            }
        ),
        encoding="utf-8",
    )
    bridge = KernelBridge(
        tmp_path,
        _Inner(),
        spawn_worker=True,
        worker_cmd=[sys.executable, str(script), str(marker)],
    )
    assert bridge.process(
        "cmd_reg", {"op": "register", "project_id": "prj_local", "name": "Cli"}
    )["ok"]
    assert bridge.process(
        "cmd_adm",
        {
            "op": "admit",
            "project_id": "prj_local",
            "principal_id": "operator",
            "role": "CONTRIBUTOR",
        },
    )["ok"]
    result = bridge.process(
        "cmd_approve",
        {
            "op": "approve",
            "workspace_id": "ws_local",
            "project_id": "prj_local",
            "pipeline_id": "pl_run",
            "principal_id": "operator",
        },
    )
    assert result["ok"] is True
    assert result.get("running") is True
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not marker.is_file():
        time.sleep(0.05)
    assert marker.read_text(encoding="utf-8") == "ok"
    view = bridge.process(
        "cmd_read_run",
        {"op": "read", "workspace_id": "ws_local", "pipeline_id": "pl_run"},
    )
    assert view["status"] == "OPEN"


def test_sqlite_kernel_imports_legacy_kernel_json(tmp_path: Path) -> None:
    document = {
        "inbox": [],
        "events": [
            {
                "event_id": "evt_1",
                "workspace_id": "ws_cli",
                "pipeline_id": "pl_legacy",
                "event_type": "REQUIREMENT_CONFIRMED",
                "payload_json": '{"text":"legacy need"}',
                "pipeline_revision": 1,
            }
        ],
        "pipelines": [
            {
                "workspace_id": "ws_cli",
                "pipeline_id": "pl_legacy",
                "status": "OPEN",
                "revision": 1,
                "text": "legacy need",
            }
        ],
        "outbox": [],
        "leases": [],
    }
    (tmp_path / "descriptor").mkdir()
    (tmp_path / "descriptor" / "kernel.json").write_text(
        json.dumps(document), encoding="utf-8"
    )
    imported = KernelBridge(tmp_path, _Inner())
    view = imported.process(
        "cmd_read_legacy",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_legacy"},
    )
    assert view["status"] == "OPEN"
    assert view["revision"] == "1" or view["revision"] == 1


def test_json_stations_import_once(tmp_path: Path) -> None:
    document = {
        "inbox": [],
        "events": [
            {
                "event_id": "evt_1",
                "workspace_id": "ws_local",
                "pipeline_id": "pl_old",
                "event_type": "REQUIREMENT_CONFIRMED",
                "payload_json": '{"text":"old need"}',
                "pipeline_revision": 1,
            }
        ],
        "pipelines": [
            {
                "workspace_id": "ws_local",
                "pipeline_id": "pl_old",
                "status": "OPEN",
                "revision": 1,
                "text": "old need",
            }
        ],
        "outbox": [],
        "leases": [],
    }
    (tmp_path / "descriptor").mkdir()
    (tmp_path / "descriptor" / "kernel.json").write_text(
        json.dumps(document), encoding="utf-8"
    )
    (tmp_path / "descriptor" / "prd.json").write_text(
        json.dumps(
            {
                "pl_old": {
                    "prd_id": "art_old",
                    "prd_status": "COMPLETED",
                    "prd_gate": "PASS",
                }
            }
        ),
        encoding="utf-8",
    )
    KernelBridge(tmp_path, _Inner())
    store = SqliteKernelStore(str(tmp_path / "controller.sqlite"))
    first = [
        event
        for event in store.list_events("ws_local", "pl_old")
        if event.event_type == "PRD_RECORDED"
    ]
    store.close()
    KernelBridge(tmp_path, _Inner())
    store = SqliteKernelStore(str(tmp_path / "controller.sqlite"))
    second = [
        event
        for event in store.list_events("ws_local", "pl_old")
        if event.event_type == "PRD_RECORDED"
    ]
    store.close()
    assert len(first) == 1
    assert len(second) == 1


def test_read_drains_publish_pr_outbox(tmp_path: Path) -> None:
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
    assert (
        bridge.process(
            "cmd_cli_one",
            {
                "text": "need a login page",
                "workspace_id": "ws_cli",
                "project_id": "prj_cli",
                "pipeline_id": "pl_cli",
                "principal_id": "operator",
            },
        )["status"]
        == "ACCEPTED"
    )
    store = SqliteKernelStore(str(tmp_path / "controller.sqlite"))
    snapshot = store.load_pipeline("ws_cli", "pl_cli")
    assert snapshot is not None
    KernelController(store, recorded_at="2026-01-01T00:00:00Z").submit(
        ControllerCommand(
            schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
            schema_version=FixedV1Integer(1),
            command_id="cmd_pl_cli_verify_1",
            idempotency_key="record-verify-drain-key",
            workspace_id="ws_cli",
            project_id="prj_cli",
            pipeline_id="pl_cli",
            expected_revision=snapshot.revision,
            actor=Actor(
                principal_id="runtime",
                provider="SYSTEM",
                provider_actor_id="test",
            ),
            ingress="SYSTEM_RECONCILER",
            command_type="RECORD_VERIFY",
            payload={
                "verify_status": "READY",
                "pipeline_id": "pl_cli",
                "project_id": "prj_cli",
                "candidate_sha": "b" * 64,
            },
            correlation_id="corr-verify-drain",
            submitted_at=UtcTimestampRef("2026-01-01T00:00:00Z"),
        )
    )
    store.close()
    view = KernelBridge(tmp_path, _Inner()).process(
        "cmd_read_drain",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view.get("action") == "RECORDED"
    store = SqliteKernelStore(str(tmp_path / "controller.sqlite"))
    assert store.list_pending_outbox("ws_cli") == []
    store.close()


def test_stage_prompts_do_not_repeat_intake_as_prd_task() -> None:
    need = "Put a short PRD in PRD.md then implement src/app.py"
    impl = implement_prompt("approved prd", "approved design", "approved tests")
    arch = architecture_prompt("approved prd")
    prd = prd_prompt(need)
    assert need not in impl
    assert "src/" in impl
    assert "BEGIN_UNTRUSTED_PRD" in impl
    assert need not in arch
    assert "ARCHITECTURE.md" in arch
    assert need in prd
    noted = implement_prompt(
        "approved prd", "approved design", "approved tests", "assert False"
    )
    assert "FEEDBACK FROM LAST GATE" in noted
    assert "assert False" in noted
    assert "FEEDBACK FROM LAST GATE" not in impl


def test_implement_duty_ignores_quoted_write_prd() -> None:
    quoted = "Write PRD.md. After approval, implement it under src/"
    impl = implement_prompt(quoted, "approved design", "approved tests")
    duty, marker, rest = impl.partition("BEGIN_UNTRUSTED_PRD")
    assert marker
    assert duty.strip().startswith("STAGE: DEVELOPMENT")
    assert "Write PRD.md" not in duty
    assert "Write PRD.md" in rest


def test_viewer_cannot_approve(tmp_path: Path) -> None:
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
        "cmd_view",
        {
            "op": "admit",
            "project_id": "prj_cli",
            "principal_id": "peek",
            "role": "VIEWER",
        },
    )
    first.process(
        "cmd_bind",
        {"op": "bind", "role": "planner", "runtime": "fake", "model": "fake-prd"},
    )
    first.process(
        "cmd_prd",
        {
            "text": "need a login page",
            "workspace_id": "ws_cli",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    denied = first.process(
        "cmd_ok",
        {
            "op": "approve",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "peek",
        },
    )
    assert denied["ok"] is False


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


def test_retry_once_after_rework(tmp_path: Path) -> None:
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
    path = tmp_path / "descriptor" / "verify.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["pl_cli"]["verify_status"] = "REWORK"
    document["pl_cli"]["verify_attempts"] = "0"
    path.write_text(json.dumps(document), encoding="utf-8")
    first = KernelBridge(tmp_path, _Inner())
    retried = first.process(
        "cmd_retry",
        {
            "op": "retry",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert retried["ok"] is True
    assert retried["verify_status"] == "READY"
    assert retried["verify_attempts"] == "1"
    again = first.process(
        "cmd_retry_2",
        {
            "op": "retry",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert again["ok"] is False
    assert again["error"] == "not rework"


def test_read_and_retry_surface_persisted_feedback(tmp_path: Path) -> None:
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
    verify_path = tmp_path / "descriptor" / "verify.json"
    document = json.loads(verify_path.read_text(encoding="utf-8"))
    document["pl_cli"]["verify_status"] = "REWORK"
    document["pl_cli"]["verify_attempts"] = "0"
    verify_path.write_text(json.dumps(document), encoding="utf-8")
    (tmp_path / "descriptor" / "feedback.json").write_text(
        json.dumps({"pl_cli": "pytest failed: assert False"}),
        encoding="utf-8",
    )
    first = KernelBridge(tmp_path, _Inner())
    view = first.process(
        "cmd_read_fb",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view["feedback"] == "pytest failed: assert False"
    retried = first.process(
        "cmd_retry_fb",
        {
            "op": "retry",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert retried["ok"] is True
    assert retried["feedback"] == ""


def test_approve_fails_when_candidate_gate_fails(tmp_path: Path) -> None:
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
    path = tmp_path / "descriptor" / "development.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["pl_cli"]["candidate_gate"] = "FAIL"
    path.write_text(json.dumps(document), encoding="utf-8")
    (tmp_path / "descriptor" / "verify.json").unlink()
    (tmp_path / "descriptor" / "feedback.json").write_text(
        json.dumps({"pl_cli": "self-test failed"}),
        encoding="utf-8",
    )
    first = KernelBridge(tmp_path, _Inner())
    approved = first.process(
        "cmd_ok_fail",
        {
            "op": "approve",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert approved["ok"] is False
    assert approved["candidate_gate"] == "FAIL"
    assert approved["feedback"] == "self-test failed"


def test_retry_after_candidate_gate_fail(tmp_path: Path) -> None:
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
    path = tmp_path / "descriptor" / "development.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["pl_cli"]["candidate_gate"] = "FAIL"
    document["pl_cli"]["rework_attempts"] = "0"
    path.write_text(json.dumps(document), encoding="utf-8")
    verify_path = tmp_path / "descriptor" / "verify.json"
    if verify_path.is_file():
        verify_path.unlink()
    first = KernelBridge(tmp_path, _Inner())
    retried = first.process(
        "cmd_retry_dev",
        {
            "op": "retry",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert retried["ok"] is True
    assert retried["candidate_gate"] != "FAIL"
    again = first.process(
        "cmd_retry_dev_2",
        {
            "op": "retry",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert again["ok"] is False
    assert again["error"] in {"not rework", "retry exhausted"}


def test_verify_oserror_is_infra_and_retry_keeps_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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

    def _boom(*_args: object, **_kwargs: object) -> object:
        raise OSError("sandbox")

    monkeypatch.setattr("hermes_pipeline.transport.kernel_bridge.VerifyFlow.run", _boom)
    approved = first.process(
        "cmd_ok",
        {
            "op": "approve",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert approved["ok"] is False
    assert approved["verify_status"] == "INFRA"
    monkeypatch.undo()
    retried = first.process(
        "cmd_retry_infra",
        {
            "op": "retry",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert retried["ok"] is True
    assert retried["verify_attempts"] == "0"


def test_retry_dev_gate_exhausted_without_verify(tmp_path: Path) -> None:
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
    path = tmp_path / "descriptor" / "development.json"
    path.write_text(
        json.dumps(
            {
                "pl_cli": {
                    "impl_id": "",
                    "candidate_sha": "",
                    "candidate_path": "",
                    "dev_status": "DENIED",
                    "candidate_gate": "FAIL",
                    "rework_attempts": "1",
                }
            }
        ),
        encoding="utf-8",
    )
    first = KernelBridge(tmp_path, _Inner())
    denied = first.process(
        "cmd_retry_ex",
        {
            "op": "retry",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert denied["ok"] is False
    assert denied["error"] == "retry exhausted"


def test_corrupt_verify_json_is_fail_closed(tmp_path: Path) -> None:
    first = KernelBridge(tmp_path, _Inner())
    first.process("cmd_reg", {"op": "register", "project_id": "prj_cli", "name": "Cli"})
    (tmp_path / "descriptor" / "verify.json").write_text("not-json", encoding="utf-8")
    second = KernelBridge(tmp_path, _Inner())
    view = second.process(
        "cmd_read_view",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view["ok"] is False
    assert view["error"] == "corrupt state"


def test_corrupt_architecture_json_is_fail_closed(tmp_path: Path) -> None:
    first = KernelBridge(tmp_path, _Inner())
    first.process("cmd_reg", {"op": "register", "project_id": "prj_cli", "name": "Cli"})
    (tmp_path / "descriptor" / "architecture.json").write_text(
        "not-json", encoding="utf-8"
    )
    second = KernelBridge(tmp_path, _Inner())
    view = second.process(
        "cmd_read_view",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view["ok"] is False
    assert view["error"] == "corrupt state"
    approved = second.process(
        "cmd_ok",
        {
            "op": "approve",
            "project_id": "prj_cli",
            "pipeline_id": "pl_cli",
            "principal_id": "operator",
        },
    )
    assert approved["ok"] is False
    assert approved["error"] == "corrupt state"


def test_stages_bundle_restores_verify_if_sidecar_missing(tmp_path: Path) -> None:
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
    (tmp_path / "descriptor" / "verify.json").unlink()
    second = KernelBridge(tmp_path, _Inner())
    view = second.process(
        "cmd_read_2",
        {"op": "read", "workspace_id": "ws_cli", "pipeline_id": "pl_cli"},
    )
    assert view["verify_status"] == "READY"
    assert view["approval_status"] == "APPROVED"


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
