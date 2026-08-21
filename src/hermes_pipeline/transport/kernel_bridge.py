"""Bridge loopback commands onto KernelController + intake."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, cast

from hermes_pipeline.artifacts.local_cas import ArtifactNotFound, LocalCasArtifacts
from hermes_pipeline.contracts.definitions import FixedV1Integer, UtcTimestampRef
from hermes_pipeline.contracts.runtime import Actor, ControllerCommand
from hermes_pipeline.controller import KernelController
from hermes_pipeline.controller.transaction_store import (
    ControllerTransactionStore,
    LeaseError,
    fold_stage_projection,
)
from hermes_pipeline.delivery.fake import FakeDelivery
from hermes_pipeline.delivery.github import GitHubDelivery, GitHubTransport
from hermes_pipeline.delivery.ports import DeliveryRecord, DeliveryRequest
from hermes_pipeline.operations.baseline import SolutionApproval
from hermes_pipeline.operations.projects import ProjectRegistry, RequirementIntake
from hermes_pipeline.persistence.kernel_sqlite import SqliteKernelStore
from hermes_pipeline.repository.integration import (
    VerificationSandbox,
    build_integration_candidate,
)
from hermes_pipeline.repository.worktree import ManagedWorktree
from hermes_pipeline.runtime_broker.binding import (
    RUNTIME_FAMILIES,
    AgentBinding,
    BindingNotFound,
    BindingTable,
    BoundRuntimeBroker,
    RuntimeFamily,
    StageRole,
)
from hermes_pipeline.runtime_broker.browser_tools import (
    BrowserToolsError,
    materialize_browser_tools,
)
from hermes_pipeline.runtime_broker.capability import compile_profile
from hermes_pipeline.runtime_broker.chrome_mcp import ChromeMcpRuntime
from hermes_pipeline.runtime_broker.codex_adapter import CodexAdapter
from hermes_pipeline.runtime_broker.fake import FakeRuntimeBroker
from hermes_pipeline.runtime_broker.opencode_adapter import OpenCodeAdapter
from hermes_pipeline.runtime_broker.ports import (
    RuntimeBrokerPort,
    RuntimeHandle,
    RuntimeLaunchRequest,
    RuntimeOutcome,
    RuntimeSignalReceipt,
    RuntimeSnapshot,
)
from hermes_pipeline.runtime_broker.process_adapter import ProcessAdapter
from hermes_pipeline.stage_executor.architecture import (
    ArchitectureGate,
    ArchitectureStage,
)
from hermes_pipeline.stage_executor.contracts import (
    ARCHITECTURE_CONTRACT,
    DEVELOPMENT_CONTRACT,
    PRD_CONTRACT,
    fence,
)
from hermes_pipeline.stage_executor.development import (
    CandidateGate,
    DevelopmentStage,
)
from hermes_pipeline.stage_executor.prd import PrdGate, PrdStage
from hermes_pipeline.stage_executor.verify import VerifyFlow

_RECORDED = "2026-01-01T00:00:00Z"
_RECORD_COMMANDS = {
    "prd": "RECORD_PRD",
    "architecture": "RECORD_ARCHITECTURE",
    "development": "RECORD_DEVELOPMENT",
    "verify": "RECORD_VERIFY",
    "approval": "RECORD_APPROVAL",
}
_RECORD_EVENTS = {
    "prd": "PRD_RECORDED",
    "architecture": "ARCHITECTURE_RECORDED",
    "development": "DEVELOPMENT_RECORDED",
    "verify": "VERIFY_RECORDED",
    "approval": "APPROVAL_RECORDED",
}
_ROLES = {"ADMIN", "CONTRIBUTOR", "VIEWER"}
_STAGE_ROLES = {"planner", "executor", "reviewer", "e2e"}
_RUNTIMES = RUNTIME_FAMILIES


class KernelBridge:
    def __init__(
        self,
        state_root: Path,
        inner: Any,
        *,
        spawn_worker: bool = False,
        worker_cmd: list[str] | None = None,
    ) -> None:
        self._inner = inner
        self._spawn_worker = spawn_worker
        self._worker_cmd = worker_cmd
        self._dir = state_root / "descriptor"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._corrupt = False
        self._store = self._load_kernel()
        self._controller = KernelController(self._store, recorded_at=_RECORDED)
        self._registry = self._load_registry()
        self._bindings = self._load_bindings()
        self._intake = RequirementIntake(
            self._registry, self._controller, recorded_at=_RECORDED
        )
        self._delivery = self._load_delivery()
        self._prd = self._load_prd()
        self._arch = self._load_arch()
        self._dev = self._load_dev()
        self._verify = self._load_verify()
        self._approvals = self._load_approvals()
        self._approval = SolutionApproval(self._registry)
        self._approval.restore(self._approvals)
        self._apply_stage_bundle()
        self._approval.restore(self._approvals)
        self._github = self._load_github()
        self._runtimes = self._load_runtime_pins()
        self._requirements = self._load_requirements()
        self._feedback = self._load_feedback()
        self._github_transport: GitHubTransport | None = None
        self._github_token = ""
        self._import_json_stations()

    def enable_github(self, token: str, transport: GitHubTransport) -> None:
        self._github_token = token
        self._github_transport = transport

    def process(self, command_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._corrupt:
            return {"ok": False, "error": "corrupt state"}
        op = payload.get("op")
        if op == "register":
            record = self._registry.register(
                str(payload.get("project_id", "")), str(payload.get("name", ""))
            )
            self._save_registry()
            return {"ok": True, "project_id": record.project_id}
        if op == "admit":
            role = str(payload.get("role", ""))
            if role not in _ROLES:
                return {"ok": False, "error": "invalid role"}
            try:
                self._registry.admit(
                    str(payload.get("project_id", "")),
                    str(payload.get("principal_id", "")),
                    role,  # type: ignore[arg-type]
                )
            except KeyError:
                return {"ok": False, "error": "project not found"}
            self._save_registry()
            return {"ok": True}
        if op == "bind":
            stage = str(payload.get("role", ""))
            runtime = str(payload.get("runtime", ""))
            model = str(payload.get("model", ""))
            if stage not in _STAGE_ROLES or runtime not in _RUNTIMES or not model:
                return {"ok": False, "error": "invalid binding"}
            self._bindings.bind(
                AgentBinding(stage, runtime, model)  # type: ignore[arg-type]
            )
            self._save_bindings()
            return {"ok": True, "role": stage, "runtime": runtime, "model": model}
        if op == "bindings":
            return {"ok": True, "bindings": self._bindings.dump()}
        if op == "runtimes":
            return {"ok": True, "runtimes": sorted(self._runtimes)}
        if op == "github":
            repo = str(payload.get("repo", ""))
            if repo.count("/") != 1 or not all(repo.split("/")):
                return {"ok": False, "error": "invalid repo"}
            self._github = {"repo": repo, "base": str(payload.get("base", "main"))}
            self._save_github()
            return {"ok": True, "repo": repo}
        if op == "deliver":
            sha = str(payload.get("sha") or payload.get("name") or "")
            event_id = str(payload.get("event_id", ""))
            project_id = str(payload.get("project_id", "prj_local"))
            pipeline_id = str(payload.get("pipeline_id", "pl_local"))
            if not sha and not event_id:
                return {"ok": False, "error": "missing sha"}
            published: DeliveryRecord | None = None
            if sha:
                published = self._delivery.publish(
                    DeliveryRequest(
                        name=sha,
                        project_id=project_id,
                        pipeline_id=pipeline_id,
                    )
                )
            if event_id:
                published = self._delivery.reconcile(
                    DeliveryRequest(
                        name=sha,
                        project_id=project_id,
                        pipeline_id=pipeline_id,
                        event_id=event_id,
                        check_status=str(payload.get("check_status", "")),
                        review_status=str(payload.get("review_status", "")),
                        queue_status=str(payload.get("queue_status", "")),
                    )
                )
            if published is None:
                return {"ok": False, "error": "missing sha"}
            if sha:
                published = self._mirror_github(
                    published,
                    DeliveryRequest(
                        name=sha, project_id=project_id, pipeline_id=pipeline_id
                    ),
                )
            self._save_delivery()
            return _record_view(published)
        if op == "read":
            workspace_id = str(payload.get("workspace_id", ""))
            pipeline_id = str(payload.get("pipeline_id", ""))
            if workspace_id:
                self._drain_outbox(workspace_id)
            view = self._intake.read(pipeline_id, workspace_id)
            stored = self._delivery.lookup(pipeline_id)
            result: dict[str, Any] = {
                "pipeline_id": view.pipeline_id,
                "revision": view.revision,
                "status": view.status,
            }
            if stored is not None:
                result.update(_record_view(stored))
            planning = self._prd.get(pipeline_id)
            if planning is not None:
                result.update(planning)
            design = self._arch.get(pipeline_id)
            if design is not None:
                result.update(design)
            developed = self._dev.get(pipeline_id)
            if developed is not None:
                result.update(developed)
            verified = self._verify.get(pipeline_id)
            if verified is not None:
                result.update(verified)
                result["verify_attempts"] = str(verified.get("verify_attempts", "0"))
            decision = self._approvals.get(pipeline_id)
            if decision is not None:
                result["approval_status"] = decision.get("approval_status", "")
                result["approver_id"] = decision.get("approver_id", "")
            if self._github:
                result["github_repo"] = self._github.get("repo", "")
                result["check_status"] = ""
                result["review_status"] = ""
                result["queue_status"] = ""
            need = self._requirements.get(pipeline_id)
            if need:
                result["requirement_text"] = need
            note = self._feedback.get(pipeline_id, "")
            if note:
                result["feedback"] = note
            folded = fold_stage_projection(
                self._store.list_events(workspace_id, pipeline_id)
            )
            if folded:
                result.update(folded)
            return result
        text = payload.get("text")
        if isinstance(text, str):
            workspace_id = str(payload.get("workspace_id", "ws_local"))
            project_id = str(payload.get("project_id", "prj_local"))
            pipeline_id = str(payload.get("pipeline_id", "pl_local"))
            principal = str(payload.get("principal_id", "operator"))
            receipt = self._intake.confirm(
                workspace_id=workspace_id,
                project_id=project_id,
                pipeline_id=pipeline_id,
                actor=Actor(
                    principal_id=principal,
                    provider="CLI",
                    provider_actor_id=principal,
                ),
                text=text,
                command_id=command_id,
            )
            if receipt.status == "ACCEPTED":
                self._requirements[pipeline_id] = text
                self._save_requirements()
                self._advance_prd(pipeline_id, workspace_id, project_id)
                self._advance_architecture(pipeline_id, workspace_id, project_id)
            return receipt.model_dump(mode="json")
        if op == "approve":
            return self._approve_baseline(payload)
        if op == "retry":
            return self._retry_verify(payload)
        return self._inner.process(command_id, payload)

    def _load_registry(self) -> ProjectRegistry:
        document = self._parse_json(self._dir / "projects.json")
        if self._corrupt or not document:
            return ProjectRegistry()
        return ProjectRegistry.load(document)

    def _save_registry(self) -> None:
        self._write_json(self._dir / "projects.json", self._registry.dump())

    def _load_bindings(self) -> BindingTable:
        document = self._parse_json(self._dir / "bindings.json")
        if self._corrupt or not document:
            return BindingTable({})
        return BindingTable.load(document)

    def _save_bindings(self) -> None:
        self._write_json(self._dir / "bindings.json", self._bindings.dump())

    def _load_delivery(self) -> FakeDelivery:
        document = self._parse_json(self._dir / "delivery.json")
        if self._corrupt or not document:
            return FakeDelivery()
        return FakeDelivery.load(document)

    def _save_delivery(self) -> None:
        self._write_json(self._dir / "delivery.json", self._delivery.dump())

    def _mirror_github(
        self, record: DeliveryRecord, request: DeliveryRequest
    ) -> DeliveryRecord:
        if not self._github or self._github_transport is None or not self._github_token:
            return record
        remote = GitHubDelivery(
            self._github.get("repo", ""),
            self._github_token,
            self._github_transport,
            self._github.get("base", "main"),
        ).publish(request)
        if not remote.ok:
            return record
        merged = DeliveryRecord(
            ok=True,
            action="RECORDED",
            branch=remote.branch or record.branch,
            pr_number=remote.pr_number or record.pr_number,
            head_sha=record.head_sha,
            check_status=record.check_status,
            review_status=record.review_status,
            queue_status=record.queue_status,
            pr_url=remote.pr_url,
        )
        key = request.pipeline_id or request.name
        self._delivery.remember(key, merged)
        return merged

    def _load_kernel(self) -> ControllerTransactionStore:
        path = self._dir.parent / "controller.sqlite"
        store = SqliteKernelStore(str(path))
        counts = store.counts()
        empty = counts.inbox == 0 and counts.events == 0 and counts.pipelines == 0
        if empty:
            document = self._parse_json(self._dir / "kernel.json")
            if document:
                store.import_dump(document)
        return store

    def _record_station(
        self,
        workspace_id: str,
        project_id: str,
        pipeline_id: str,
        station: str,
        fields: dict[str, str],
    ) -> None:
        command_type = _RECORD_COMMANDS.get(station)
        event_type = _RECORD_EVENTS.get(station)
        if command_type is None or event_type is None or not workspace_id:
            return
        attempt = 1 + sum(
            1
            for event in self._store.list_events(workspace_id, pipeline_id)
            if event.event_type == event_type
        )
        command_id = f"cmd_{pipeline_id}_{station}_{attempt}"
        snapshot = self._store.load_pipeline(workspace_id, pipeline_id)
        if snapshot is None:
            return
        payload = {key: str(value) for key, value in fields.items()}
        command = ControllerCommand(
            schema_id="https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
            schema_version=FixedV1Integer(1),
            command_id=command_id,
            idempotency_key=f"record-{command_id}-key000",
            workspace_id=workspace_id,
            project_id=project_id,
            pipeline_id=pipeline_id,
            expected_revision=snapshot.revision,
            actor=Actor(
                principal_id="runtime",
                provider="SYSTEM",
                provider_actor_id="kernel-bridge",
            ),
            ingress="SYSTEM_RECONCILER",
            command_type=command_type,
            payload=payload,
            correlation_id=f"corr-{command_id}",
            submitted_at=UtcTimestampRef(_RECORDED),
        )
        self._controller.submit(command)

    def _record_verify(
        self, workspace_id: str, project_id: str, pipeline_id: str, sha: str
    ) -> None:
        row = dict(self._verify.get(pipeline_id, {}))
        row["pipeline_id"] = pipeline_id
        row["project_id"] = project_id
        row["candidate_sha"] = sha
        self._record_station(workspace_id, project_id, pipeline_id, "verify", row)
        self._drain_outbox(workspace_id)

    def _drain_outbox(self, workspace_id: str) -> None:
        if not workspace_id:
            return
        for item in self._store.list_pending_outbox(workspace_id):
            if item.effect_type != "PUBLISH_PR":
                self._store.record_outbox_delivery(workspace_id, item.command_id, "{}")
                continue
            try:
                payload = json.loads(item.payload_json)
            except ValueError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            typed = cast(dict[str, Any], payload)
            pipeline_id = str(typed.get("pipeline_id", ""))
            project_id = str(typed.get("project_id", "prj_local"))
            sha = str(typed.get("candidate_sha", ""))
            stored = self._delivery.lookup(pipeline_id) if pipeline_id else None
            if (stored is None or not stored.pr_url) and sha:
                request = DeliveryRequest(
                    name=sha, project_id=project_id, pipeline_id=pipeline_id
                )
                published = self._delivery.publish(request)
                published = self._mirror_github(published, request)
                self._save_delivery()
                stored = published
            receipt = json.dumps(
                {
                    "pr_url": stored.pr_url if stored is not None else "",
                    "pr_number": stored.pr_number if stored is not None else "",
                    "head_sha": stored.head_sha if stored is not None else "",
                },
                sort_keys=True,
            )
            self._store.record_outbox_delivery(workspace_id, item.command_id, receipt)

    def _import_json_stations(self) -> None:
        workspace_id = "ws_local"
        ids = (
            set(self._prd)
            | set(self._arch)
            | set(self._dev)
            | set(self._verify)
            | set(self._approvals)
        )
        for pipeline_id in ids:
            snapshot = self._store.load_pipeline(workspace_id, pipeline_id)
            if snapshot is None or snapshot.status != "OPEN":
                continue
            events = self._store.list_events(workspace_id, pipeline_id)
            if any(event.event_type in _RECORD_EVENTS.values() for event in events):
                continue
            project_id = (
                self._approvals.get(pipeline_id, {}).get("project_id", "prj_local")
                or "prj_local"
            )
            if pipeline_id in self._prd:
                self._record_station(
                    workspace_id, project_id, pipeline_id, "prd", self._prd[pipeline_id]
                )
            if pipeline_id in self._arch:
                self._record_station(
                    workspace_id,
                    project_id,
                    pipeline_id,
                    "architecture",
                    self._arch[pipeline_id],
                )
            if pipeline_id in self._dev:
                self._record_station(
                    workspace_id,
                    project_id,
                    pipeline_id,
                    "development",
                    self._dev[pipeline_id],
                )
            if pipeline_id in self._verify:
                sha = self._dev.get(pipeline_id, {}).get("candidate_sha", "")
                self._record_verify(workspace_id, project_id, pipeline_id, sha)
            if pipeline_id in self._approvals:
                self._record_station(
                    workspace_id,
                    project_id,
                    pipeline_id,
                    "approval",
                    {
                        "approval_status": self._approvals[pipeline_id].get(
                            "approval_status", ""
                        ),
                        "approver_id": self._approvals[pipeline_id].get(
                            "approver_id", ""
                        ),
                    },
                )

    def _load_github(self) -> dict[str, str]:
        document = self._parse_json(self._dir / "github.json")
        if self._corrupt or not document:
            return {}
        repo = str(document.get("repo", ""))
        if repo.count("/") != 1:
            return {}
        return {"repo": repo, "base": str(document.get("base", "main"))}

    def _save_github(self) -> None:
        self._write_json(self._dir / "github.json", self._github)

    def _hydrate_from_events(self, workspace_id: str, pipeline_id: str) -> None:
        folded = fold_stage_projection(
            self._store.list_events(workspace_id, pipeline_id)
        )
        if not folded:
            return
        if folded.get("prd_status") and pipeline_id not in self._prd:
            self._prd[pipeline_id] = {
                "prd_id": folded.get("prd_id", ""),
                "prd_status": folded.get("prd_status", ""),
                "prd_gate": folded.get("prd_gate", ""),
            }
        if folded.get("arch_status") and pipeline_id not in self._arch:
            self._arch[pipeline_id] = {
                "design_id": folded.get("design_id", ""),
                "testplan_id": folded.get("testplan_id", ""),
                "arch_status": folded.get("arch_status", ""),
                "arch_gate": folded.get("arch_gate", ""),
            }
        if folded.get("candidate_gate") == "PASS" and pipeline_id not in self._dev:
            self._dev[pipeline_id] = {
                "impl_id": folded.get("impl_id", ""),
                "candidate_sha": folded.get("candidate_sha", ""),
                "candidate_path": folded.get("candidate_path", ""),
                "dev_status": folded.get("dev_status", ""),
                "candidate_gate": folded.get("candidate_gate", ""),
            }
        if folded.get("verify_status") == "READY" and pipeline_id not in self._verify:
            self._verify[pipeline_id] = {
                "verify_status": folded.get("verify_status", ""),
                "e2e_id": folded.get("e2e_id", ""),
                "acceptance_id": folded.get("acceptance_id", ""),
                "verify_attempts": folded.get("verify_attempts", "0"),
                "infra_attempts": folded.get("infra_attempts", "0"),
            }
        approved = folded.get("approval_status") == "APPROVED"
        if approved and pipeline_id not in self._approvals:
            self._approvals[pipeline_id] = {
                "approval_status": folded.get("approval_status", ""),
                "approver_id": folded.get("approver_id", ""),
                "project_id": "",
            }

    def _advance_prd(
        self, pipeline_id: str, workspace_id: str, project_id: str
    ) -> None:
        self._hydrate_from_events(workspace_id, pipeline_id)
        if pipeline_id in self._prd:
            return
        artifacts = LocalCasArtifacts(self._dir.parent / "cas")
        folder = self._plans_dir(pipeline_id, "prd")
        result = PrdStage(
            self._bindings,
            artifacts,
            planner=self._runtime_broker(str(folder), "planner"),
            folder=folder,
        ).run(
            pipeline_id,
            workspace_id,
            project_id,
            prompt=self._prd_prompt(pipeline_id),
        )
        gate = "FAIL"
        if result.status == "COMPLETED":
            gate = (
                PrdGate(self._controller, artifacts)
                .evaluate(
                    pipeline_id=pipeline_id,
                    workspace_id=workspace_id,
                    artifact_id=result.artifact_id,
                )
                .status
            )
        self._prd[pipeline_id] = {
            "prd_id": result.artifact_id or "",
            "prd_status": result.status,
            "prd_gate": gate,
        }
        self._save_prd()
        self._record_station(
            workspace_id,
            project_id,
            pipeline_id,
            "prd",
            self._prd[pipeline_id],
        )

    def _advance_architecture(
        self, pipeline_id: str, workspace_id: str, project_id: str
    ) -> None:
        self._hydrate_from_events(workspace_id, pipeline_id)
        if pipeline_id in self._arch:
            return
        planning = self._prd.get(pipeline_id)
        if planning is None or planning.get("prd_gate") != "PASS":
            return
        prd_id = planning.get("prd_id", "")
        artifacts = LocalCasArtifacts(self._dir.parent / "cas")
        folder = self._plans_dir(pipeline_id, "architecture")
        result = ArchitectureStage(
            self._bindings,
            artifacts,
            planner=self._runtime_broker(str(folder), "planner"),
            folder=folder,
        ).run(
            prd_artifact_id=prd_id,
            pipeline_id=pipeline_id,
            prompt=self._architecture_prompt(pipeline_id, prd_id),
        )
        gate = (
            ArchitectureGate(self._controller, artifacts)
            .evaluate(
                pipeline_id=pipeline_id,
                workspace_id=workspace_id,
                prd_artifact_id=prd_id,
                result=result,
            )
            .status
        )
        self._arch[pipeline_id] = {
            "design_id": result.design_id or "",
            "testplan_id": result.testplan_id or "",
            "arch_status": result.status,
            "arch_gate": gate,
        }
        self._save_arch()
        self._record_station(
            workspace_id,
            project_id,
            pipeline_id,
            "architecture",
            self._arch[pipeline_id],
        )
        if gate == "PASS" and pipeline_id not in self._approvals:
            self._approvals[pipeline_id] = {
                "approval_status": "PENDING",
                "approver_id": "",
                "project_id": project_id,
            }
            self._save_approvals()

    def _parse_json(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._corrupt = True
            return {}
        if not isinstance(document, dict):
            self._corrupt = True
            return {}
        return cast(dict[str, Any], document)

    def _write_json(self, path: Path, document: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(
            prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        temp = Path(name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                out.write(json.dumps(document, sort_keys=True))
            os.replace(temp, path)
        except OSError:
            with contextlib.suppress(OSError):
                temp.unlink()
            raise

    def _apply_stage_bundle(self) -> None:
        document = self._parse_json(self._dir / "stages.json")
        if self._corrupt or not document:
            return
        approvals = document.get("approvals")
        if isinstance(approvals, dict) and not (self._dir / "approvals.json").is_file():
            self._approvals = self._coerce_approvals(cast(dict[str, Any], approvals))
        developed = document.get("development")
        if (
            isinstance(developed, dict)
            and not (self._dir / "development.json").is_file()
        ):
            self._dev = self._coerce_dev(cast(dict[str, Any], developed))
        verified = document.get("verify")
        if isinstance(verified, dict) and not (self._dir / "verify.json").is_file():
            self._verify = self._coerce_verify(cast(dict[str, Any], verified))

    def _save_stages(self) -> None:
        payload = {
            "approvals": self._approvals,
            "development": self._dev,
            "verify": self._verify,
        }
        self._write_json(self._dir / "stages.json", payload)

    def _load_prd(self) -> dict[str, dict[str, str]]:
        document = self._parse_json(self._dir / "prd.json")
        loaded: dict[str, dict[str, str]] = {}
        typed = document
        for raw_key, item in typed.items():
            if not isinstance(item, dict):
                continue
            row = cast(dict[str, Any], item)
            loaded[str(raw_key)] = {
                "prd_id": str(row.get("prd_id", "")),
                "prd_status": str(row.get("prd_status", "")),
                "prd_gate": str(row.get("prd_gate", "")),
            }
        return loaded

    def _save_prd(self) -> None:
        self._write_json(self._dir / "prd.json", self._prd)

    def _load_arch(self) -> dict[str, dict[str, str]]:
        document = self._parse_json(self._dir / "architecture.json")
        loaded: dict[str, dict[str, str]] = {}
        for raw_key, item in document.items():
            if not isinstance(item, dict):
                continue
            row = cast(dict[str, Any], item)
            loaded[str(raw_key)] = {
                "design_id": str(row.get("design_id", "")),
                "testplan_id": str(row.get("testplan_id", "")),
                "arch_status": str(row.get("arch_status", "")),
                "arch_gate": str(row.get("arch_gate", "")),
            }
        return loaded

    def _save_arch(self) -> None:
        self._write_json(self._dir / "architecture.json", self._arch)

    def _advance_development(
        self,
        pipeline_id: str,
        project_id: str,
        principal_id: str,
        workspace_id: str = "ws_local",
    ) -> None:
        self._hydrate_from_events(workspace_id, pipeline_id)
        if pipeline_id in self._dev:
            return
        planning = self._prd.get(pipeline_id)
        design = self._arch.get(pipeline_id)
        if (
            planning is None
            or design is None
            or planning.get("prd_gate") != "PASS"
            or design.get("arch_gate") != "PASS"
        ):
            return
        prd_id = planning.get("prd_id", "")
        design_id = design.get("design_id", "")
        testplan_id = design.get("testplan_id", "")
        try:
            self._approval.designate(pipeline_id, project_id, principal_id)
            self._approval.approve(
                pipeline_id=pipeline_id,
                project_id=project_id,
                actor_id=principal_id,
                prd_id=prd_id,
                design_id=design_id,
                testplan_id=testplan_id,
            )
        except PermissionError:
            self._dev[pipeline_id] = {
                "impl_id": "",
                "candidate_sha": "",
                "candidate_path": "",
                "dev_status": "DENIED",
                "candidate_gate": "FAIL",
            }
            self._save_dev()
            self._record_station(
                workspace_id,
                project_id,
                pipeline_id,
                "development",
                self._dev[pipeline_id],
            )
            return
        artifacts = LocalCasArtifacts(self._dir.parent / "cas")
        worktree = ManagedWorktree(self._dir.parent / "worktrees" / pipeline_id)
        result = DevelopmentStage(
            self._bindings,
            self._approval,
            artifacts,
            worktree,
            executor=self._executor_broker(worktree),
        ).run(
            pipeline_id=pipeline_id,
            prd_id=prd_id,
            design_id=design_id,
            testplan_id=testplan_id,
            prompt=self._implement_prompt(pipeline_id, prd_id, design_id, testplan_id),
        )
        if result.feedback:
            self._set_feedback(pipeline_id, result.feedback)
        elif result.status == "COMPLETED":
            self._clear_feedback(pipeline_id)
        gate = (
            CandidateGate(self._approval, artifacts)
            .evaluate(
                pipeline_id=pipeline_id,
                prd_id=prd_id,
                design_id=design_id,
                testplan_id=testplan_id,
                result=result,
            )
            .status
        )
        candidate = result.candidate
        self._dev[pipeline_id] = {
            "impl_id": result.artifact_id or "",
            "candidate_sha": candidate.sha if candidate is not None else "",
            "candidate_path": candidate.relative_path if candidate is not None else "",
            "dev_status": result.status,
            "candidate_gate": gate,
        }
        self._save_dev()
        self._record_station(
            workspace_id, project_id, pipeline_id, "development", self._dev[pipeline_id]
        )

    def _plans_dir(self, pipeline_id: str, stage: str) -> Path:
        folder = self._dir.parent / "plans" / pipeline_id / stage
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _executor_broker(self, worktree: ManagedWorktree) -> BoundRuntimeBroker:
        return self._runtime_broker(str(worktree.root), "executor")

    def _e2e_runtime(self, cwd: str) -> RuntimeBrokerPort:
        try:
            binding = self._bindings.resolve("e2e")
        except BindingNotFound:
            return _PassingRuntime()
        if binding.runtime == "fake":
            return _PassingRuntime()
        root = self._dir.parent / "verify-sandbox"
        with contextlib.suppress(BrowserToolsError, OSError):
            materialize_browser_tools(root)
        return ChromeMcpRuntime(
            profile=compile_profile(
                write_roots=[cwd],
                browser="CHROME_DEVTOOLS_MCP",
                stage_type="E2E",
                profile_id="cap_e2e",
            ),
            state_root=root,
        )

    def _role_runtime(self, role: str, cwd: str) -> RuntimeBrokerPort:
        try:
            binding = self._bindings.resolve(cast(StageRole, role))
        except BindingNotFound:
            return _PassingRuntime()
        if binding.runtime == "fake":
            return _PassingRuntime()
        return self._runtime_broker(cwd, role)

    def _profile_for(self, role: str, cwd: str, family: str) -> Any:
        stage = {
            "planner": "PRD",
            "executor": "DEVELOPMENT",
            "e2e": "E2E",
            "reviewer": "ACCEPTANCE",
        }.get(role, "DEVELOPMENT")
        return compile_profile(
            write_roots=[cwd],
            executables=[family],
            stage_type=stage,  # type: ignore[arg-type]
            profile_id=f"cap_{role}",
        )

    def _runtime_broker(self, cwd: str, role: str = "executor") -> BoundRuntimeBroker:
        sandbox = "workspace-write" if role == "executor" else "read-only"
        adapters: dict[RuntimeFamily, RuntimeBrokerPort] = {
            "fake": FakeRuntimeBroker(),
            "opencode": OpenCodeAdapter(
                self._pinned_exe("opencode"),
                cwd=cwd,
                profile=self._profile_for(role, cwd, "opencode"),
            ),
            "codex": CodexAdapter(
                self._pinned_exe("codex"),
                cwd=cwd,
                profile=self._profile_for(role, cwd, "codex"),
                sandbox=sandbox,
            ),
        }
        for family in ("claude", "cursor", "kiro", "grok"):
            adapters[family] = ProcessAdapter(
                self._pinned_exe(family),
                cwd=cwd,
                profile=self._profile_for(role, cwd, "process"),
            )
        return BoundRuntimeBroker(self._bindings, adapters)

    def _prd_prompt(self, pipeline_id: str) -> str:
        return prd_prompt(self._requirements.get(pipeline_id, ""))

    def _architecture_prompt(self, pipeline_id: str, prd_id: str) -> str:
        del pipeline_id
        return architecture_prompt(self._artifact_text(prd_id))

    def _implement_prompt(
        self, pipeline_id: str, prd_id: str, design_id: str, testplan_id: str
    ) -> str:
        return implement_prompt(
            self._artifact_text(prd_id),
            self._artifact_text(design_id),
            self._artifact_text(testplan_id),
            self._feedback.get(pipeline_id, ""),
        )

    def _load_feedback(self) -> dict[str, str]:
        document = self._parse_json(self._dir / "feedback.json")
        loaded: dict[str, str] = {}
        for key, value in document.items():
            if isinstance(value, str) and value.strip():
                loaded[str(key)] = value
        return loaded

    def _save_feedback(self) -> None:
        self._write_json(self._dir / "feedback.json", self._feedback)

    def _set_feedback(self, pipeline_id: str, note: str) -> None:
        text = note.strip()
        if not text:
            return
        self._feedback[pipeline_id] = text
        self._save_feedback()

    def _clear_feedback(self, pipeline_id: str) -> None:
        if pipeline_id not in self._feedback:
            return
        self._feedback.pop(pipeline_id, None)
        self._save_feedback()

    def _artifact_text(self, artifact_id: str) -> str:
        if not artifact_id:
            return ""
        store = LocalCasArtifacts(self._dir.parent / "cas")
        try:
            return store.open(artifact_id).decode("utf-8", errors="replace")
        except (OSError, KeyError, ValueError, ArtifactNotFound):
            return ""

    def _load_requirements(self) -> dict[str, str]:
        document = self._parse_json(self._dir / "requirements.json")
        loaded: dict[str, str] = {}
        for raw_key, item in document.items():
            if isinstance(item, str):
                loaded[str(raw_key)] = item
        return loaded

    def _save_requirements(self) -> None:
        self._write_json(self._dir / "requirements.json", self._requirements)

    def _pinned_exe(self, family: str) -> str | None:
        path = self._runtimes.get(family, "")
        if path and Path(path).is_file():
            return path
        return None

    def _load_runtime_pins(self) -> dict[str, str]:
        document = self._parse_json(self._dir / "runtimes.json")
        loaded: dict[str, str] = {}
        for family in ("opencode", "codex", "claude", "cursor", "kiro", "grok"):
            raw = str(document.get(family, ""))
            if raw and Path(raw).is_file():
                loaded[family] = raw
        return loaded

    def _coerce_dev(self, document: dict[str, Any]) -> dict[str, dict[str, str]]:
        loaded: dict[str, dict[str, str]] = {}
        for raw_key, item in document.items():
            if not isinstance(item, dict):
                continue
            row = cast(dict[str, Any], item)
            loaded[str(raw_key)] = {
                "impl_id": str(row.get("impl_id", "")),
                "candidate_sha": str(row.get("candidate_sha", "")),
                "candidate_path": str(row.get("candidate_path", "")),
                "dev_status": str(row.get("dev_status", "")),
                "candidate_gate": str(row.get("candidate_gate", "")),
                "rework_attempts": str(row.get("rework_attempts", "0")),
            }
        return loaded

    def _load_dev(self) -> dict[str, dict[str, str]]:
        return self._coerce_dev(self._parse_json(self._dir / "development.json"))

    def _save_dev(self) -> None:
        self._write_json(self._dir / "development.json", self._dev)
        self._save_stages()

    def _advance_verify(
        self, pipeline_id: str, project_id: str, workspace_id: str = "ws_local"
    ) -> None:
        self._hydrate_from_events(workspace_id, pipeline_id)
        if pipeline_id in self._verify:
            return
        developed = self._dev.get(pipeline_id)
        if developed is None or developed.get("candidate_gate") != "PASS":
            return
        sha = developed.get("candidate_sha", "")
        artifacts = LocalCasArtifacts(self._dir.parent / "cas")
        sandbox = VerificationSandbox(self._dir.parent / "sandbox" / pipeline_id)
        worktree = self._dir.parent / "worktrees" / pipeline_id
        cwd = str(sandbox.root)
        testplan_id = self._arch.get(pipeline_id, {}).get("testplan_id", "")
        try:
            result = VerifyFlow(
                self._bindings,
                artifacts,
                self._e2e_runtime(cwd),
                self._role_runtime("reviewer", cwd),
                self._delivery,
                sandbox,
                project_id=project_id,
                pipeline_id=pipeline_id,
                candidate_root=worktree if worktree.is_dir() else None,
                testplan_text=self._artifact_text(testplan_id),
                candidate_sha=sha,
            ).run(build_integration_candidate(sha, "0" * 64))
        except Exception:
            prior = self._verify.get(pipeline_id, {})
            self._verify[pipeline_id] = {
                "verify_status": "INFRA",
                "e2e_id": "",
                "acceptance_id": "",
                "verify_attempts": str(prior.get("verify_attempts", "0")),
                "infra_attempts": str(prior.get("infra_attempts", "0")),
            }
            self._save_verify()
            self._record_verify(workspace_id, project_id, pipeline_id, sha="")
            return
        stored = self._delivery.lookup(pipeline_id)
        if stored is not None:
            self._mirror_github(
                stored,
                DeliveryRequest(
                    name=sha, project_id=project_id, pipeline_id=pipeline_id
                ),
            )
        self._save_delivery()
        self._verify[pipeline_id] = {
            "verify_status": result.status,
            "e2e_id": result.e2e_id or "",
            "acceptance_id": result.acceptance_id or "",
            "verify_attempts": str(
                self._verify.get(pipeline_id, {}).get("verify_attempts", "0")
            ),
        }
        if result.status == "REWORK" and result.feedback:
            self._set_feedback(pipeline_id, result.feedback)
        elif result.status == "READY":
            self._clear_feedback(pipeline_id)
        self._save_verify()
        self._record_verify(workspace_id, project_id, pipeline_id, sha)

    def _coerce_verify(self, document: dict[str, Any]) -> dict[str, dict[str, str]]:
        loaded: dict[str, dict[str, str]] = {}
        for raw_key, item in document.items():
            if not isinstance(item, dict):
                continue
            row = cast(dict[str, Any], item)
            loaded[str(raw_key)] = {
                "verify_status": str(row.get("verify_status", "")),
                "e2e_id": str(row.get("e2e_id", "")),
                "acceptance_id": str(row.get("acceptance_id", "")),
                "verify_attempts": str(row.get("verify_attempts", "0")),
                "infra_attempts": str(row.get("infra_attempts", "0")),
            }
        return loaded

    def _load_verify(self) -> dict[str, dict[str, str]]:
        return self._coerce_verify(self._parse_json(self._dir / "verify.json"))

    def _save_verify(self) -> None:
        self._write_json(self._dir / "verify.json", self._verify)
        self._save_stages()

    def _retry_verify(self, payload: dict[str, Any]) -> dict[str, Any]:
        pipeline_id = str(payload.get("pipeline_id", "pl_local"))
        project_id = str(payload.get("project_id", "prj_local"))
        principal = str(payload.get("principal_id", "operator"))
        workspace_id = str(payload.get("workspace_id", "ws_local"))
        self._hydrate_from_events(workspace_id, pipeline_id)
        verified = self._verify.get(pipeline_id, {})
        developed = self._dev.get(pipeline_id, {})
        rework = verified.get("verify_status") == "REWORK"
        infra = verified.get("verify_status") == "INFRA"
        failed_dev = developed.get("candidate_gate") == "FAIL"
        if not rework and not failed_dev and not infra:
            return {"ok": False, "error": "not rework"}
        used = int(
            verified.get("verify_attempts") or developed.get("rework_attempts") or 0
        )
        infra_used = int(verified.get("infra_attempts") or 0)
        if infra:
            if infra_used >= 3:
                return {"ok": False, "error": "retry exhausted"}
        elif used >= 1:
            return {"ok": False, "error": "retry exhausted"}
        if self._registry.role_of(project_id, principal) is None:
            return {"ok": False, "error": "not a project member"}
        if self._spawn_worker:
            now = int(time.time())
            holder = f"worker-{pipeline_id}"
            try:
                lease = self._controller.acquire_lease(
                    workspace_id,
                    pipeline_id,
                    holder,
                    now,
                    1800,
                    replace=False,
                )
            except LeaseError:
                return {"ok": False, "error": "busy"}
            self._dev.pop(pipeline_id, None)
            self._save_dev()
            self._verify.pop(pipeline_id, None)
            self._spawn_stage_worker(
                workspace_id,
                project_id,
                pipeline_id,
                principal,
                holder,
                lease.generation,
            )
            return {"ok": True, "running": True}
        self._dev.pop(pipeline_id, None)
        self._save_dev()
        self._verify.pop(pipeline_id, None)
        self._advance_development(pipeline_id, project_id, principal, workspace_id)
        self._advance_verify(pipeline_id, project_id, workspace_id)
        row = self._verify.get(pipeline_id, {})
        if row:
            if infra:
                if row.get("verify_status") == "INFRA":
                    row["infra_attempts"] = str(infra_used + 1)
                else:
                    row["infra_attempts"] = str(infra_used)
                row["verify_attempts"] = str(used)
            else:
                row["verify_attempts"] = "1"
            self._verify[pipeline_id] = row
            self._save_verify()
        else:
            leftover = self._dev.get(pipeline_id, {})
            leftover["rework_attempts"] = "1"
            self._dev[pipeline_id] = leftover
            self._save_dev()
            row = leftover
        status = row.get("verify_status", "")
        gate = self._dev.get(pipeline_id, {}).get("candidate_gate", "")
        return {
            "ok": status == "READY" and gate != "FAIL",
            "verify_status": status,
            "verify_attempts": row.get("verify_attempts", "1"),
            "candidate_gate": gate,
            "feedback": self._feedback.get(pipeline_id, ""),
        }

    def _approve_baseline(self, payload: dict[str, Any]) -> dict[str, Any]:
        pipeline_id = str(payload.get("pipeline_id", "pl_local"))
        project_id = str(payload.get("project_id", "prj_local"))
        principal = str(payload.get("principal_id", "operator"))
        workspace_id = str(payload.get("workspace_id", "ws_local"))
        now = int(time.time())
        held = self._store.load_lease(workspace_id, pipeline_id)
        if held is not None and now <= held.expires_at:
            return {"ok": False, "error": "busy"}
        self._hydrate_from_events(workspace_id, pipeline_id)
        planning = self._prd.get(pipeline_id)
        design = self._arch.get(pipeline_id)
        if (
            planning is None
            or design is None
            or planning.get("prd_gate") != "PASS"
            or design.get("arch_gate") != "PASS"
        ):
            return {"ok": False, "error": "baseline not ready"}
        if self._registry.role_of(project_id, principal) is None:
            return {"ok": False, "error": "not a project member"}
        holder = f"worker-{pipeline_id}"
        try:
            lease = self._controller.acquire_lease(
                workspace_id, pipeline_id, holder, now, 1800, replace=False
            )
        except LeaseError:
            return {"ok": False, "error": "busy"}
        if self._spawn_worker:
            committed = self._commit_approval(
                pipeline_id, project_id, principal, workspace_id
            )
            if not committed.get("ok"):
                self._controller.cancel(workspace_id, pipeline_id)
                return committed
            self._spawn_stage_worker(
                workspace_id,
                project_id,
                pipeline_id,
                principal,
                holder,
                lease.generation,
            )
            return {
                "ok": True,
                "running": True,
                "approval_status": "APPROVED",
                "approver_id": principal,
            }
        try:
            return self._run_approved(
                payload, pipeline_id, project_id, principal, workspace_id
            )
        finally:
            self._controller.cancel(workspace_id, pipeline_id)

    def _commit_approval(
        self,
        pipeline_id: str,
        project_id: str,
        principal: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        planning = self._prd.get(pipeline_id)
        design = self._arch.get(pipeline_id)
        if planning is None or design is None:
            return {"ok": False, "error": "baseline not ready"}
        try:
            self._approval.designate(pipeline_id, project_id, principal)
            self._approval.approve(
                pipeline_id=pipeline_id,
                project_id=project_id,
                actor_id=principal,
                prd_id=planning.get("prd_id", ""),
                design_id=design.get("design_id", ""),
                testplan_id=design.get("testplan_id", ""),
            )
        except PermissionError:
            return {"ok": False, "error": "approval denied"}
        self._approvals = self._approval.dump()
        row = self._approvals.get(pipeline_id, {})
        row["project_id"] = project_id
        self._approvals[pipeline_id] = row
        self._save_approvals()
        self._record_station(
            workspace_id,
            project_id,
            pipeline_id,
            "approval",
            {
                "approval_status": "APPROVED",
                "approver_id": principal,
            },
        )
        return {"ok": True}

    def _run_approved(
        self,
        payload: dict[str, Any],
        pipeline_id: str,
        project_id: str,
        principal: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        del payload
        committed = self._commit_approval(
            pipeline_id, project_id, principal, workspace_id
        )
        if not committed.get("ok"):
            return committed
        return self.run_leased_stages(
            workspace_id=workspace_id,
            project_id=project_id,
            pipeline_id=pipeline_id,
            principal_id=principal,
            as_receipt=True,
        )

    def run_leased_stages(
        self,
        *,
        workspace_id: str,
        project_id: str,
        pipeline_id: str,
        principal_id: str,
        as_receipt: bool = False,
    ) -> Any:
        self._hydrate_from_events(workspace_id, pipeline_id)
        self._advance_development(pipeline_id, project_id, principal_id, workspace_id)
        self._advance_verify(pipeline_id, project_id, workspace_id)
        verify_status = self._verify.get(pipeline_id, {}).get("verify_status", "")
        gate = self._dev.get(pipeline_id, {}).get("candidate_gate", "")
        if as_receipt:
            return {
                "ok": verify_status not in {"REWORK", "INFRA"} and gate != "FAIL",
                "approval_status": "APPROVED",
                "approver_id": principal_id,
                "verify_status": verify_status,
                "candidate_gate": gate,
                "feedback": self._feedback.get(pipeline_id, ""),
            }
        if verify_status == "READY" and gate != "FAIL":
            return 0
        return 1

    def heartbeat_lease(
        self,
        workspace_id: str,
        pipeline_id: str,
        holder: str,
        generation: int,
        now: int,
    ) -> None:
        self._controller.heartbeat_lease(
            workspace_id, pipeline_id, holder, generation, now, 180
        )

    def release_lease(self, workspace_id: str, pipeline_id: str) -> None:
        self._controller.cancel(workspace_id, pipeline_id)

    def _spawn_stage_worker(
        self,
        workspace_id: str,
        project_id: str,
        pipeline_id: str,
        principal: str,
        holder: str,
        generation: int,
    ) -> None:
        if self._worker_cmd is not None:
            argv = list(self._worker_cmd)
        else:
            argv = [
                sys.executable,
                "-m",
                "hermes_pipeline.transport.stage_worker",
                "--state-root",
                str(self._dir.parent),
                "--workspace-id",
                workspace_id,
                "--project-id",
                project_id,
                "--pipeline-id",
                pipeline_id,
                "--principal-id",
                principal,
                "--holder",
                holder,
                "--generation",
                str(generation),
            ]
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"GITHUB_TOKEN", "GH_TOKEN"}
        }
        kwargs: dict[str, Any] = {
            "cwd": str(self._dir.parent),
            "env": env,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )
        subprocess.Popen(argv, **kwargs)

    def _coerce_approvals(self, document: dict[str, Any]) -> dict[str, dict[str, str]]:
        loaded: dict[str, dict[str, str]] = {}
        for raw_key, item in document.items():
            if not isinstance(item, dict):
                continue
            row = cast(dict[str, Any], item)
            loaded[str(raw_key)] = {
                "approval_status": str(row.get("approval_status", "")),
                "approver_id": str(row.get("approver_id", "")),
                "project_id": str(row.get("project_id", "")),
                "prd_id": str(row.get("prd_id", "")),
                "design_id": str(row.get("design_id", "")),
                "testplan_id": str(row.get("testplan_id", "")),
                "designated_id": str(row.get("designated_id", "")),
            }
        return loaded

    def _load_approvals(self) -> dict[str, dict[str, str]]:
        return self._coerce_approvals(self._parse_json(self._dir / "approvals.json"))

    def _save_approvals(self) -> None:
        self._write_json(self._dir / "approvals.json", self._approvals)
        self._save_stages()


class _PassingRuntime:
    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        return RuntimeHandle(runtime_id=request.runtime_id, status="COMPLETED")

    def signal(self, runtime_id: str) -> RuntimeSignalReceipt:
        del runtime_id
        return RuntimeSignalReceipt(ok=True, code="CANCELLED")

    def inspect(self, runtime_id: str) -> RuntimeSnapshot:
        return RuntimeSnapshot(runtime_id=runtime_id, status="COMPLETED")

    def collect(self, runtime_id: str) -> RuntimeOutcome:
        return RuntimeOutcome(runtime_id=runtime_id, status="COMPLETED")


def _record_view(record: DeliveryRecord) -> dict[str, Any]:
    return {
        "ok": record.ok,
        "action": record.action,
        "branch": record.branch,
        "pr_number": record.pr_number,
        "head_sha": record.head_sha,
        "check_status": record.check_status,
        "review_status": record.review_status,
        "queue_status": record.queue_status,
        "pr_url": record.pr_url,
    }


def prd_prompt(need: str) -> str:
    return f"{PRD_CONTRACT}\n{fence('NEED', need)}"


def architecture_prompt(prd_text: str) -> str:
    return f"{ARCHITECTURE_CONTRACT}\n{fence('PRD', prd_text)}"


def implement_prompt(
    prd_text: str, design_text: str, testplan_text: str, feedback: str = ""
) -> str:
    parts = [
        DEVELOPMENT_CONTRACT,
        fence("PRD", prd_text),
        fence("DESIGN", design_text),
        fence("TESTPLAN", testplan_text),
    ]
    note = feedback.strip()
    if note:
        parts.append("FEEDBACK FROM LAST GATE. Fix these issues, then self-test.")
        parts.append(fence("FEEDBACK", note))
    return "\n".join(parts)


__all__ = ["KernelBridge", "architecture_prompt", "implement_prompt", "prd_prompt"]
