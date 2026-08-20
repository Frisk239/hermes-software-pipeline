"""E2E + Acceptance verification flow (slice 04-01).

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from hermes_pipeline.artifacts.ports import ArtifactPutRequest, ArtifactsPort
from hermes_pipeline.delivery.ports import (
    DeliveryPort,
    DeliveryRecord,
    DeliveryRequest,
)
from hermes_pipeline.repository.integration import (
    IntegrationCandidate,
    VerificationSandbox,
)
from hermes_pipeline.runtime_broker.binding import BindingNotFound, BindingTable
from hermes_pipeline.runtime_broker.ports import RuntimeBrokerPort, RuntimeLaunchRequest
from hermes_pipeline.stage_executor.contracts import (
    ACCEPTANCE_CONTRACT,
    E2E_CONTRACT,
    fence,
)
from hermes_pipeline.stage_executor.self_test import run_app, run_pytest

E2E_BYTES = b"hermes-pipeline-e2e-v1\n"
ACCEPT_BYTES = b"hermes-pipeline-acceptance-v1\n"

VerifyStatus = Literal["READY", "REWORK", "DENIED", "DRIFT"]


@dataclass(frozen=True)
class VerifyResult:
    status: VerifyStatus
    e2e_id: str | None = None
    acceptance_id: str | None = None
    delivered: bool = False
    delivery: DeliveryRecord | None = None
    feedback: str = ""


class VerifyFlow:
    def __init__(
        self,
        bindings: BindingTable,
        artifacts: ArtifactsPort,
        e2e_runtime: RuntimeBrokerPort,
        reviewer_runtime: RuntimeBrokerPort,
        delivery: DeliveryPort,
        sandbox: VerificationSandbox,
        project_id: str = "prj_local",
        pipeline_id: str = "pl_local",
        candidate_root: Path | None = None,
        testplan_text: str = "",
        candidate_sha: str = "",
    ) -> None:
        self._bindings = bindings
        self._artifacts = artifacts
        self._e2e = e2e_runtime
        self._reviewer = reviewer_runtime
        self._delivery = delivery
        self._sandbox = sandbox
        self._project_id = project_id
        self._pipeline_id = pipeline_id
        self._candidate_root = candidate_root
        self._testplan_text = testplan_text
        self._candidate_sha = candidate_sha
        self._passed_sha: str | None = None

    def run(self, integration: IntegrationCandidate) -> VerifyResult:
        try:
            self._bindings.resolve("e2e")
            self._bindings.resolve("reviewer")
        except BindingNotFound:
            return VerifyResult(status="DENIED")
        if self._passed_sha is not None and self._passed_sha != integration.sha:
            return VerifyResult(status="DRIFT")
        self._sandbox.create(integration.sha)
        try:
            scripted = self._run_staged_candidate()
            if scripted == "failed":
                return VerifyResult(
                    status="REWORK", feedback=_script_feedback(self._sandbox.root)
                )
            e2e_bind = self._bindings.resolve("e2e")
            real_e2e = e2e_bind.runtime != "fake"
            if real_e2e and scripted in {"timeout", "none", "skip"}:
                return VerifyResult(
                    status="REWORK",
                    feedback=_script_feedback(self._sandbox.root)
                    or "scripted e2e unavailable",
                )
            e2e_id = f"e2e-{integration.sha[:12]}"
            origin, server = self._serve_if_needed(real_e2e)
            try:
                e2e = self._e2e.launch(
                    RuntimeLaunchRequest(
                        runtime_id=e2e_id,
                        role="e2e",
                        prompt=self._e2e_prompt(integration.sha),
                        origin=origin,
                    )
                )
            except (OSError, RuntimeError, ValueError):
                _stop(server)
                return VerifyResult(
                    status="REWORK", feedback="e2e runtime did not complete"
                )
            _stop(server)
            if e2e.status != "COMPLETED" and _verdict(
                self._sandbox.root, "RESULT.md"
            ) not in {"pass", "fail"}:
                return VerifyResult(
                    status="REWORK",
                    feedback=self._e2e_feedback(e2e_id)
                    or "e2e runtime did not complete",
                )
            if real_e2e and e2e.status != "COMPLETED":
                return VerifyResult(
                    status="REWORK",
                    feedback=self._e2e_feedback(e2e_id)
                    or _named_feedback(self._sandbox.root, "RESULT.md")
                    or "e2e RESULT.md is not PASS",
                )
            if real_e2e and _verdict(self._sandbox.root, "RESULT.md") not in {
                "pass",
                "missing",
            }:
                return VerifyResult(
                    status="REWORK",
                    feedback=_named_feedback(self._sandbox.root, "RESULT.md")
                    or "e2e RESULT.md is not PASS",
                )
            e2e_art = self._artifacts.put(
                ArtifactPutRequest(payload=self._e2e_payload(e2e_id, real_e2e))
            )
            review_bind = self._bindings.resolve("reviewer")
            real_reviewer = review_bind.runtime != "fake"
            if scripted == "passed" and not real_reviewer:
                acc_art = self._artifacts.put(ArtifactPutRequest(payload=ACCEPT_BYTES))
            else:
                try:
                    accept = self._reviewer.launch(
                        RuntimeLaunchRequest(
                            runtime_id=f"acc-{integration.sha[:12]}",
                            role="reviewer",
                            prompt=self._review_prompt(integration.sha),
                        )
                    )
                except (OSError, RuntimeError, ValueError):
                    return VerifyResult(
                        status="REWORK",
                        e2e_id=e2e_art.artifact_id,
                        feedback="reviewer runtime did not complete",
                    )
                if accept.status != "COMPLETED" and _verdict(
                    self._sandbox.root, "REVIEW.md"
                ) not in {"pass", "fail"}:
                    return VerifyResult(
                        status="REWORK",
                        e2e_id=e2e_art.artifact_id,
                        feedback="reviewer runtime did not complete",
                    )
                review_bind = self._bindings.resolve("reviewer")
                if (
                    review_bind.runtime != "fake"
                    and _verdict(self._sandbox.root, "REVIEW.md") != "pass"
                ):
                    return VerifyResult(
                        status="REWORK",
                        e2e_id=e2e_art.artifact_id,
                        feedback=_named_feedback(self._sandbox.root, "REVIEW.md")
                        or "REVIEW.md is not PASS",
                    )
                acc_art = self._artifacts.put(ArtifactPutRequest(payload=ACCEPT_BYTES))
            published = self._delivery.publish(
                DeliveryRequest(
                    name=integration.sha,
                    project_id=self._project_id,
                    pipeline_id=self._pipeline_id,
                )
            )
            self._passed_sha = integration.sha
            return VerifyResult(
                status="READY",
                e2e_id=e2e_art.artifact_id,
                acceptance_id=acc_art.artifact_id,
                delivered=published.ok,
                delivery=published,
            )
        finally:
            self._sandbox.cleanup()

    def _run_staged_candidate(self) -> str:
        e2e = self._bindings.resolve("e2e")
        if e2e.runtime == "fake":
            return "skip"
        if self._candidate_root is None:
            return "none"
        self._sandbox.stage_tree(self._candidate_root)
        chunks: list[str] = []
        tested = False
        tests = self._sandbox.root / "tests"
        if tests.is_dir():
            code, text = run_pytest(self._sandbox.root)
            chunks.append(text)
            if code is None or code != 0:
                self._sandbox.write("SCRIPT_OUT", "\n".join(chunks))
                return "failed"
            tested = True
        app = self._sandbox.root / "src" / "app.py"
        if not app.is_file():
            if tested:
                self._sandbox.write("SCRIPT_OUT", "\n".join(chunks))
                return "passed"
            return "none"
        status, text = run_app(app, self._sandbox.root / "src")
        chunks.append(text)
        self._sandbox.write("SCRIPT_OUT", "\n".join(chunks))
        return status

    def _serve_if_needed(
        self, real_e2e: bool
    ) -> tuple[str, subprocess.Popen[bytes] | None]:
        if not real_e2e:
            return "", None
        app = self._sandbox.root / "src" / "app.py"
        if not app.is_file():
            return "http://127.0.0.1/", None
        port = _reserve_port()
        env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "PORT": str(port),
            "HERMES_E2E_PORT": str(port),
        }
        proc = subprocess.Popen(
            [sys.executable, str(app)],
            cwd=str(app.parent),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _wait_loopback(proc, port)
        return f"http://127.0.0.1:{port}/", proc

    def _e2e_payload(self, runtime_id: str, real_e2e: bool) -> bytes:
        if not real_e2e:
            return E2E_BYTES
        text = self._e2e.collect(runtime_id).final_text.strip()
        if text:
            return text.encode("utf-8")
        return E2E_BYTES

    def _e2e_feedback(self, runtime_id: str) -> str:
        return self._e2e.collect(runtime_id).detail.strip()

    def _e2e_prompt(self, sha: str = "") -> str:
        mark = sha or self._candidate_sha
        return (
            f"{E2E_CONTRACT}\n"
            f"Candidate SHA: {mark}\n"
            f"{fence('TESTPLAN', self._testplan_text)}\n"
            "Evaluate this directory only. Run src/app.py if present. "
            "Write RESULT.md: first line PASS or FAIL, then findings."
        )

    def _review_prompt(self, sha: str = "") -> str:
        mark = sha or self._candidate_sha
        return (
            f"{ACCEPTANCE_CONTRACT}\n"
            f"Candidate SHA: {mark}\n"
            f"{fence('TESTPLAN', self._testplan_text)}\n"
            "Evaluate this directory only. "
            "Write REVIEW.md: first line PASS or FAIL, then findings."
        )


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_loopback(proc: subprocess.Popen[bytes], port: int) -> None:
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)


def _stop(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _named_feedback(root: Path, name: str) -> str:
    path = root / name
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _script_feedback(root: Path) -> str:
    return _named_feedback(root, "SCRIPT_OUT").strip() or "scripted verify failed"


def _verdict(folder: Path, name: str) -> str:
    path = folder / name
    if not path.is_file():
        return "missing"
    text = path.read_text(encoding="utf-8", errors="replace").strip().upper()
    if text.startswith("PASS"):
        return "pass"
    if text.startswith("FAIL"):
        return "fail"
    return "missing"


__all__ = [
    "ACCEPT_BYTES",
    "E2E_BYTES",
    "VerifyFlow",
    "VerifyResult",
]
