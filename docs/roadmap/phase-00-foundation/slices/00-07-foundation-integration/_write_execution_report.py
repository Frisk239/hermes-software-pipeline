"""Run Slice 00-07 verification commands and write the Execution Report."""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from hermes_pipeline.contracts.jcs import content_hash, raw_digest

REPO = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent / "evidence"

COMMANDS: list[tuple[str, list[str]]] = [
    ("frozen-sync", ["uv", "sync", "--frozen", "--all-groups", "--offline"]),
    ("offline-format", ["uv", "run", "--offline", "ruff", "format", "--check", "."]),
    ("offline-lint", ["uv", "run", "--offline", "ruff", "check", "."]),
    ("offline-type", ["uv", "run", "--offline", "pyright"]),
    ("offline-pytest", ["uv", "run", "--offline", "pytest"]),
    (
        "offline-contracts-check",
        [
            "uv",
            "run",
            "--offline",
            "python",
            "-m",
            "hermes_pipeline.cli",
            "contracts",
            "check",
        ],
    ),
    (
        "offline-contracts-drift",
        [
            "uv",
            "run",
            "--offline",
            "python",
            "-m",
            "hermes_pipeline.cli",
            "contracts",
            "drift-check",
        ],
    ),
    (
        "architecture-check",
        [
            "uv",
            "run",
            "--offline",
            "python",
            "-m",
            "hermes_pipeline.cli",
            "architecture",
            "check",
        ],
    ),
    (
        "docs-check",
        ["uv", "run", "--offline", "python", "scripts/check_documentation.py"],
    ),
    (
        "workflow-check",
        [
            "uv",
            "run",
            "--offline",
            "python",
            "scripts/check_documentation.py",
            "--check-workflows",
        ],
    ),
    ("sbom-preview", ["uv", "run", "--offline", "python", "scripts/sbom_preview.py"]),
    (
        "dependency-audit",
        ["uv", "run", "--offline", "python", "scripts/check_dependency_audit.py"],
    ),
    (
        "hermes-integration",
        [
            "uv",
            "run",
            "--offline",
            "pytest",
            "tests/spike/lifecycle",
            "tests/spike/shim",
            "-q",
        ],
    ),
    ("changed-paths", ["git", "status", "--short"]),
]


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    artifacts: list[dict[str, str]] = []
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    failed = False
    for command_id, argv in COMMANDS:
        started = datetime.now(tz=UTC)
        t0 = time.perf_counter()
        completed = subprocess.run(
            argv, cwd=REPO, capture_output=True, check=False, env=env
        )
        duration_ms = int((time.perf_counter() - t0) * 1000)
        blob = completed.stdout + b"\n--- stderr ---\n" + completed.stderr
        digest = raw_digest(blob)
        (EVIDENCE / f"{command_id}.out").write_bytes(blob[:65536])
        art = {
            "artifact_id": f"art_00-07_{command_id.replace('-', '_')}",
            "manifest_digest": digest,
            "role": f"stdout-{command_id}",
        }
        artifacts.append(art)
        results.append(
            {
                "command_id": command_id,
                "exit_code": int(completed.returncode),
                "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "duration_ms": duration_ms,
                "output_artifact": art,
            }
        )
        print(f"{command_id} exit={completed.returncode} ms={duration_ms}", flush=True)
        if completed.returncode != 0:
            failed = True
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
    report_rel = (
        "docs/roadmap/phase-00-foundation/slices/"
        "00-07-foundation-integration/execution-report.json"
    )
    if report_rel not in expanded:
        expanded.append(report_rel)
    report = {
        "schema_id": "https://schemas.hermes-pipeline.dev/engineering/execution-report/v1",
        "schema_version": 1,
        "report_id": "exec_slice-00-07_attempt1",
        "slice_id": "slice-00-07",
        "contract_revision": 2,
        "attempt": 1,
        "base_sha": "078411b20283288ab2ec85f081d3ed463fba96e4",
        "candidate_sha": "d5672acd53df8630b2ac3be8d50c723ee60f9cc2",
        "context_manifest_hash": (
            "sha256:f2de1f88dc6b4e7089ec209953b5742a7637bc1355319ba5dbce4edbec8cbe40"
        ),
        "changed_paths": sorted(set(expanded)),
        "command_results": results,
        "artifact_refs": artifacts,
        "self_assessment": "BLOCKED" if failed else "READY_FOR_REVIEW",
        "submitted_at": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "risks": [
            "UNCOMMITTED: candidate_sha is worktree HEAD d5672ac. "
            "No implementation Candidate exists until Git Custodian commits.",
            "Windows and Linux CI on the Candidate are required after publication.",
            "Isolation, Chrome for Testing, and Windows sealed Codex remain "
            "UNSUPPORTED or experimental.",
        ],
    }
    report["content_hash"] = content_hash(report)
    Path(REPO / report_rel).write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(report["self_assessment"], report["content_hash"])
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
