"""Write an honest attempt-3 Execution Report from live command runs.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from hermes_pipeline.contracts.jcs import content_hash, raw_digest

REPO = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent / "evidence"
BOOT = "src/hermes_pipeline/runtime_broker/tools_bootstrap.py"
E2E = "src/hermes_pipeline/runtime_broker/controlled_e2e.py"
CLI = "hermes_pipeline.cli"


def _uv(*args: str) -> list[str]:
    return ["uv", "run", "--offline", *args]


COMMANDS: list[tuple[str, list[str]]] = [
    ("frozen-sync", ["uv", "sync", "--frozen", "--all-groups", "--offline"]),
    ("unit-check", ["uv", "run", "pytest", "-m", "fake_only", "-q"]),
    ("tools-bootstrap", _uv("python", BOOT)),
    ("tools-cutoff-verify", _uv("python", BOOT, "verify")),
    ("tools-selfcheck", _uv("python", BOOT, "selfcheck")),
    (
        "probe-codex",
        _uv(
            "pytest",
            "tests/spike/security/test_codex_adapter_probe.py",
            "-m",
            "fake_only",
            "-q",
        ),
    ),
    (
        "probe-opencode",
        _uv(
            "pytest",
            "tests/spike/security/test_opencode_adapter_probe.py",
            "-m",
            "fake_only",
            "-q",
        ),
    ),
    ("probe-codex-real", _uv("python", BOOT, "probe-codex")),
    ("probe-opencode-real", _uv("python", BOOT, "probe-opencode")),
    ("spike-security", _uv("pytest", "tests/spike/security", "-m", "fake_only", "-q")),
    (
        "spike-capability",
        _uv("pytest", "tests/spike/capability", "-m", "fake_only", "-q"),
    ),
    ("spike-e2e", _uv("pytest", "tests/spike/e2e", "-m", "fake_only", "-q")),
    (
        "spike-adversarial-security",
        _uv("pytest", "tests/spike/adversarial-security", "-m", "fake_only", "-q"),
    ),
    ("controlled-e2e", _uv("python", E2E)),
    ("docs-check", ["uv", "run", "python", "scripts/check_documentation.py"]),
    ("offline-version", _uv("python", "-m", CLI, "--version")),
    ("offline-contracts-check", _uv("python", "-m", CLI, "contracts", "check")),
    ("offline-contracts-drift", _uv("python", "-m", CLI, "contracts", "drift-check")),
    ("offline-architecture", _uv("python", "-m", CLI, "architecture", "check")),
    ("offline-format", _uv("ruff", "format", "--check", ".")),
    ("offline-lint", _uv("ruff", "check", ".")),
    ("offline-type", _uv("pyright")),
    ("offline-pytest", _uv("pytest", "-q")),
    ("offline-docs-check", _uv("python", "scripts/check_documentation.py")),
    (
        "offline-docs-negative",
        _uv("python", "scripts/check_documentation.py", "--self-test-negative"),
    ),
    (
        "offline-schema-negative",
        _uv("python", "scripts/check_schemas.py", "--self-test-negative"),
    ),
    (
        "offline-workflow-policy",
        _uv("python", "scripts/check_documentation.py", "--check-workflows"),
    ),
    ("offline-artifact", _uv("python", "scripts/check_repository_artifacts.py")),
    ("diff-check", ["git", "diff", "--check"]),
    ("changed-paths", ["git", "status", "--short"]),
    (
        "fake-only-gate",
        _uv(
            "pytest",
            "tests/spike/security/test_fake_only_gate.py",
            "-m",
            "fake_only",
            "-q",
        ),
    ),
]


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    artifacts: list[dict[str, str]] = []
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for command_id, argv in COMMANDS:
        started = datetime.now(tz=UTC)
        t0 = time.perf_counter()
        completed = subprocess.run(
            argv, cwd=REPO, capture_output=True, check=False, env=env
        )
        duration_ms = int((time.perf_counter() - t0) * 1000)
        blob = completed.stdout + b"\n--- stderr ---\n" + completed.stderr
        digest = raw_digest(blob)
        out_path = EVIDENCE / f"{command_id}.out"
        out_path.write_bytes(blob[:65536])
        art = {
            "artifact_id": f"art_00-06_{command_id.replace('-', '_')}",
            "manifest_digest": digest,
            "role": f"stdout-{command_id}",
        }
        artifacts.append(art)
        results.append(
            {
                "command_id": command_id,
                "exit_code": int(completed.returncode),
                "started_at": started.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "duration_ms": duration_ms,
                "output_artifact": art,
            }
        )
        print(f"{command_id} exit={completed.returncode} ms={duration_ms}", flush=True)
    changed = subprocess.check_output(
        ["git", "diff", "--name-only"], cwd=REPO, text=True
    ).splitlines()
    changed += subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=REPO, text=True
    ).splitlines()
    expanded: list[str] = []
    for item in changed:
        path = REPO / item
        if path.is_dir():
            expanded.extend(
                child.relative_to(REPO).as_posix()
                for child in path.rglob("*")
                if child.is_file()
            )
        else:
            expanded.append(item.replace("\\", "/"))
    report_rel = "tests/spike/security/execution-report.json"
    if report_rel not in expanded:
        expanded.append(report_rel)
    report = {
        "schema_id": "https://schemas.hermes-pipeline.dev/engineering/execution-report/v1",
        "schema_version": 1,
        "report_id": "exec_slice-00-06_attempt3",
        "slice_id": "slice-00-06",
        "contract_revision": 14,
        "attempt": 3,
        "base_sha": "9cf24b876cc7422386ed54c277900ff1e3c2c2bf",
        "candidate_sha": "41f0169023063d6c6996e82daaeeab3a504dfa58",
        "context_manifest_hash": (
            "sha256:fd654c649066755a6907a606139e9808263bd9fa59b913b8eefc3a324d7e5d2f"
        ),
        "changed_paths": sorted(set(expanded)),
        "command_results": results,
        "artifact_refs": artifacts,
        "self_assessment": "READY_FOR_REVIEW",
        "submitted_at": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "risks": [
            "UNCOMMITTED: candidate_sha is worktree HEAD 41f0169 only. "
            "It does not contain this implementation. No implementation "
            "Candidate exists until Git Custodian commits.",
            "Authorized Host success commands were invoked without "
            "Custodian snapshot/record/binding/gate and without a "
            "demonstrated isolation proof. Their exit_code is 1 "
            "(DEPENDENCY_UNAVAILABLE). They are not reported as success.",
            "Windows sealed Codex, Chrome for Testing, and hard network "
            "deny remain UNSUPPORTED_RUNTIME.",
        ],
    }
    report["content_hash"] = content_hash(report)
    Path(REPO / report_rel).write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(report["content_hash"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
