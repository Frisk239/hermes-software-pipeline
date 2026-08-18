"""Bridge loopback commands onto KernelController + intake."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from hermes_pipeline.artifacts.local_cas import LocalCasArtifacts
from hermes_pipeline.contracts.runtime import Actor
from hermes_pipeline.controller import KernelController
from hermes_pipeline.delivery.fake import FakeDelivery
from hermes_pipeline.delivery.github import GitHubDelivery, GitHubTransport
from hermes_pipeline.delivery.ports import DeliveryRecord, DeliveryRequest
from hermes_pipeline.operations.baseline import SolutionApproval
from hermes_pipeline.operations.projects import ProjectRegistry, RequirementIntake
from hermes_pipeline.persistence.kernel_memory import MemoryKernelStore
from hermes_pipeline.repository.integration import (
    VerificationSandbox,
    build_integration_candidate,
)
from hermes_pipeline.repository.worktree import ManagedWorktree
from hermes_pipeline.runtime_broker.binding import (
    RUNTIME_FAMILIES,
    AgentBinding,
    BindingTable,
    BoundRuntimeBroker,
    RuntimeFamily,
)
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
from hermes_pipeline.stage_executor.development import (
    CandidateGate,
    DevelopmentStage,
)
from hermes_pipeline.stage_executor.prd import PrdGate, PrdStage
from hermes_pipeline.stage_executor.verify import VerifyFlow

_RECORDED = "2026-01-01T00:00:00Z"
_ROLES = {"ADMIN", "CONTRIBUTOR", "VIEWER"}
_STAGE_ROLES = {"planner", "executor", "reviewer", "e2e"}
_RUNTIMES = RUNTIME_FAMILIES


class KernelBridge:
    def __init__(self, state_root: Path, inner: Any) -> None:
        self._inner = inner
        self._dir = state_root / "descriptor"
        self._dir.mkdir(parents=True, exist_ok=True)
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
        self._github = self._load_github()
        self._runtimes = self._load_runtime_pins()
        self._requirements = self._load_requirements()
        self._github_transport: GitHubTransport | None = None
        self._github_token = ""

    def enable_github(self, token: str, transport: GitHubTransport) -> None:
        self._github_token = token
        self._github_transport = transport

    def process(self, command_id: str, payload: dict[str, Any]) -> dict[str, Any]:
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
            decision = self._approvals.get(pipeline_id)
            if decision is not None:
                result["approval_status"] = decision.get("approval_status", "")
                result["approver_id"] = decision.get("approver_id", "")
            if self._github:
                result["github_repo"] = self._github.get("repo", "")
            need = self._requirements.get(pipeline_id)
            if need:
                result["requirement_text"] = need
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
            self._save_kernel()
            return receipt.model_dump(mode="json")
        if op == "approve":
            return self._approve_baseline(payload)
        return self._inner.process(command_id, payload)

    def _load_registry(self) -> ProjectRegistry:
        path = self._dir / "projects.json"
        if not path.is_file():
            return ProjectRegistry()
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ProjectRegistry()
        if isinstance(document, dict):
            return ProjectRegistry.load(cast(dict[str, Any], document))
        return ProjectRegistry()

    def _save_registry(self) -> None:
        (self._dir / "projects.json").write_text(
            json.dumps(self._registry.dump(), sort_keys=True),
            encoding="utf-8",
        )

    def _load_bindings(self) -> BindingTable:
        path = self._dir / "bindings.json"
        if not path.is_file():
            return BindingTable({})
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return BindingTable({})
        if isinstance(document, dict):
            return BindingTable.load(cast(dict[str, Any], document))
        return BindingTable({})

    def _save_bindings(self) -> None:
        (self._dir / "bindings.json").write_text(
            json.dumps(self._bindings.dump(), sort_keys=True),
            encoding="utf-8",
        )

    def _load_delivery(self) -> FakeDelivery:
        path = self._dir / "delivery.json"
        if not path.is_file():
            return FakeDelivery()
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return FakeDelivery()
        if isinstance(document, dict):
            return FakeDelivery.load(cast(dict[str, Any], document))
        return FakeDelivery()

    def _save_delivery(self) -> None:
        (self._dir / "delivery.json").write_text(
            json.dumps(self._delivery.dump(), sort_keys=True),
            encoding="utf-8",
        )

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

    def _load_kernel(self) -> MemoryKernelStore:
        path = self._dir / "kernel.json"
        if not path.is_file():
            return MemoryKernelStore()
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return MemoryKernelStore()
        if isinstance(document, dict):
            return MemoryKernelStore.load(cast(dict[str, Any], document))
        return MemoryKernelStore()

    def _save_kernel(self) -> None:
        (self._dir / "kernel.json").write_text(
            json.dumps(self._store.dump(), sort_keys=True),
            encoding="utf-8",
        )

    def _load_github(self) -> dict[str, str]:
        path = self._dir / "github.json"
        if not path.is_file():
            return {}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(document, dict):
            return {}
        row = cast(dict[str, Any], document)
        repo = str(row.get("repo", ""))
        if repo.count("/") != 1:
            return {}
        return {"repo": repo, "base": str(row.get("base", "main"))}

    def _save_github(self) -> None:
        (self._dir / "github.json").write_text(
            json.dumps(self._github, sort_keys=True),
            encoding="utf-8",
        )

    def _advance_prd(
        self, pipeline_id: str, workspace_id: str, project_id: str
    ) -> None:
        if pipeline_id in self._prd:
            return
        artifacts = LocalCasArtifacts(self._dir.parent / "cas")
        result = PrdStage(
            self._bindings,
            artifacts,
            planner=self._planner_broker(pipeline_id),
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

    def _advance_architecture(
        self, pipeline_id: str, workspace_id: str, project_id: str
    ) -> None:
        if pipeline_id in self._arch:
            return
        planning = self._prd.get(pipeline_id)
        if planning is None or planning.get("prd_gate") != "PASS":
            return
        prd_id = planning.get("prd_id", "")
        artifacts = LocalCasArtifacts(self._dir.parent / "cas")
        result = ArchitectureStage(
            self._bindings,
            artifacts,
            planner=self._planner_broker(pipeline_id),
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
        if gate == "PASS" and pipeline_id not in self._approvals:
            self._approvals[pipeline_id] = {
                "approval_status": "PENDING",
                "approver_id": "",
                "project_id": project_id,
            }
            self._save_approvals()

    def _load_prd(self) -> dict[str, dict[str, str]]:
        path = self._dir / "prd.json"
        if not path.is_file():
            return {}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(document, dict):
            return {}
        loaded: dict[str, dict[str, str]] = {}
        typed = cast(dict[str, Any], document)
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
        (self._dir / "prd.json").write_text(
            json.dumps(self._prd, sort_keys=True),
            encoding="utf-8",
        )

    def _load_arch(self) -> dict[str, dict[str, str]]:
        path = self._dir / "architecture.json"
        if not path.is_file():
            return {}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(document, dict):
            return {}
        loaded: dict[str, dict[str, str]] = {}
        typed = cast(dict[str, Any], document)
        for raw_key, item in typed.items():
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
        (self._dir / "architecture.json").write_text(
            json.dumps(self._arch, sort_keys=True),
            encoding="utf-8",
        )

    def _advance_development(
        self, pipeline_id: str, project_id: str, principal_id: str
    ) -> None:
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

    def _planner_broker(self, pipeline_id: str) -> BoundRuntimeBroker:
        folder = self._dir.parent / "plans" / pipeline_id
        folder.mkdir(parents=True, exist_ok=True)
        return self._runtime_broker(str(folder))

    def _executor_broker(self, worktree: ManagedWorktree) -> BoundRuntimeBroker:
        return self._runtime_broker(str(worktree.root))

    def _runtime_broker(self, cwd: str) -> BoundRuntimeBroker:
        adapters: dict[RuntimeFamily, RuntimeBrokerPort] = {
            "fake": FakeRuntimeBroker(),
            "opencode": OpenCodeAdapter(self._pinned_exe("opencode"), cwd=cwd),
            "codex": CodexAdapter(self._pinned_exe("codex"), cwd=cwd),
        }
        for family in ("claude", "cursor", "kiro", "grok"):
            adapters[family] = ProcessAdapter(self._pinned_exe(family), cwd=cwd)
        return BoundRuntimeBroker(self._bindings, adapters)

    def _prd_prompt(self, pipeline_id: str) -> str:
        need = self._requirements.get(pipeline_id, "").strip()
        if need:
            return f"Write a PRD for this requirement:\n{need}"
        return "Write a PRD for the submitted requirement."

    def _architecture_prompt(self, pipeline_id: str, prd_id: str) -> str:
        need = self._requirements.get(pipeline_id, "").strip()
        return f"Write architecture and a test plan for prd={prd_id}\n{need}".strip()

    def _implement_prompt(
        self, pipeline_id: str, prd_id: str, design_id: str, testplan_id: str
    ) -> str:
        need = self._requirements.get(pipeline_id, "").strip()
        if need:
            return (
                f"Implement this requirement in this directory:\n{need}\n"
                f"prd={prd_id} design={design_id} testplan={testplan_id}"
            )
        return (
            f"Implement the approved solution in this directory. "
            f"prd={prd_id} design={design_id} testplan={testplan_id}"
        )

    def _load_requirements(self) -> dict[str, str]:
        path = self._dir / "requirements.json"
        if not path.is_file():
            return {}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(document, dict):
            return {}
        loaded: dict[str, str] = {}
        typed = cast(dict[str, Any], document)
        for raw_key, item in typed.items():
            if isinstance(item, str):
                loaded[str(raw_key)] = item
        return loaded

    def _save_requirements(self) -> None:
        (self._dir / "requirements.json").write_text(
            json.dumps(self._requirements, sort_keys=True),
            encoding="utf-8",
        )

    def _pinned_exe(self, family: str) -> str | None:
        path = self._runtimes.get(family, "")
        if path and Path(path).is_file():
            return path
        return None

    def _load_runtime_pins(self) -> dict[str, str]:
        path = self._dir / "runtimes.json"
        if not path.is_file():
            return {}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(document, dict):
            return {}
        loaded: dict[str, str] = {}
        typed = cast(dict[str, Any], document)
        for family in ("opencode", "codex", "claude", "cursor", "kiro", "grok"):
            raw = str(typed.get(family, ""))
            if raw and Path(raw).is_file():
                loaded[family] = raw
        return loaded

    def _load_dev(self) -> dict[str, dict[str, str]]:
        path = self._dir / "development.json"
        if not path.is_file():
            return {}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(document, dict):
            return {}
        loaded: dict[str, dict[str, str]] = {}
        typed = cast(dict[str, Any], document)
        for raw_key, item in typed.items():
            if not isinstance(item, dict):
                continue
            row = cast(dict[str, Any], item)
            loaded[str(raw_key)] = {
                "impl_id": str(row.get("impl_id", "")),
                "candidate_sha": str(row.get("candidate_sha", "")),
                "candidate_path": str(row.get("candidate_path", "")),
                "dev_status": str(row.get("dev_status", "")),
                "candidate_gate": str(row.get("candidate_gate", "")),
            }
        return loaded

    def _save_dev(self) -> None:
        (self._dir / "development.json").write_text(
            json.dumps(self._dev, sort_keys=True),
            encoding="utf-8",
        )

    def _advance_verify(self, pipeline_id: str, project_id: str) -> None:
        if pipeline_id in self._verify:
            return
        developed = self._dev.get(pipeline_id)
        if developed is None or developed.get("candidate_gate") != "PASS":
            return
        sha = developed.get("candidate_sha", "")
        artifacts = LocalCasArtifacts(self._dir.parent / "cas")
        sandbox = VerificationSandbox(self._dir.parent / "sandbox" / pipeline_id)
        passing = _PassingRuntime()
        result = VerifyFlow(
            self._bindings,
            artifacts,
            passing,
            passing,
            self._delivery,
            sandbox,
            project_id=project_id,
            pipeline_id=pipeline_id,
        ).run(build_integration_candidate(sha, "0" * 64))
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
        }
        self._save_verify()

    def _load_verify(self) -> dict[str, dict[str, str]]:
        path = self._dir / "verify.json"
        if not path.is_file():
            return {}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(document, dict):
            return {}
        loaded: dict[str, dict[str, str]] = {}
        typed = cast(dict[str, Any], document)
        for raw_key, item in typed.items():
            if not isinstance(item, dict):
                continue
            row = cast(dict[str, Any], item)
            loaded[str(raw_key)] = {
                "verify_status": str(row.get("verify_status", "")),
                "e2e_id": str(row.get("e2e_id", "")),
                "acceptance_id": str(row.get("acceptance_id", "")),
            }
        return loaded

    def _save_verify(self) -> None:
        (self._dir / "verify.json").write_text(
            json.dumps(self._verify, sort_keys=True),
            encoding="utf-8",
        )

    def _approve_baseline(self, payload: dict[str, Any]) -> dict[str, Any]:
        pipeline_id = str(payload.get("pipeline_id", "pl_local"))
        project_id = str(payload.get("project_id", "prj_local"))
        principal = str(payload.get("principal_id", "operator"))
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
        self._approvals[pipeline_id] = {
            "approval_status": "APPROVED",
            "approver_id": principal,
            "project_id": project_id,
        }
        self._save_approvals()
        self._advance_development(pipeline_id, project_id, principal)
        self._advance_verify(pipeline_id, project_id)
        return {
            "ok": True,
            "approval_status": "APPROVED",
            "approver_id": principal,
        }

    def _load_approvals(self) -> dict[str, dict[str, str]]:
        path = self._dir / "approvals.json"
        if not path.is_file():
            return {}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(document, dict):
            return {}
        loaded: dict[str, dict[str, str]] = {}
        typed = cast(dict[str, Any], document)
        for raw_key, item in typed.items():
            if not isinstance(item, dict):
                continue
            row = cast(dict[str, Any], item)
            loaded[str(raw_key)] = {
                "approval_status": str(row.get("approval_status", "")),
                "approver_id": str(row.get("approver_id", "")),
                "project_id": str(row.get("project_id", "")),
            }
        return loaded

    def _save_approvals(self) -> None:
        (self._dir / "approvals.json").write_text(
            json.dumps(self._approvals, sort_keys=True),
            encoding="utf-8",
        )


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


__all__ = ["KernelBridge"]
