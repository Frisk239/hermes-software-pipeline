"""Workflow-governance extension tests (slice-00-05, AC-11/AC-12).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

The fixed workflow-governance extension (scripts/check_documentation.py
``check_hermes_integration_workflow`` plus scripts/fixtures/workflows/)
validates the committed hermes-integration.yml and its positive/negative
fixtures; the two existing workflows and their checkers remain unchanged.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "check_documentation.py"
FIXTURES = REPO_ROOT / "scripts" / "fixtures" / "workflows"

REQUIRED_NEGATIVE_FIXTURES = {
    "arbitrary-bootstrap-bash",
    "bad-trigger",
    "bash-after-cutoff",
    "bash-extra-clone",
    "bash-extra-curl",
    "bash-extra-env",
    "bash-extra-python-c",
    "command-before-cutoff",
    "derive-before-bootstrap",
    "extra-command",
    "extra-env",
    "invalid-yaml",
    "missing-checkout-ref",
    "missing-command",
    "missing-env",
    "missing-marker",
    "missing-permissions",
    "network-after-cutoff",
    "persist-credentials",
    "quote-wrapped-env",
    "secrets-context",
    "unpinned-action",
    "wrong-env-value",
    "wrong-job-name",
    "wrong-matrix",
}


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_committed_workflow_passes_policy() -> None:
    proc = _run(["--check-hermes-workflow", "--root", str(REPO_ROOT)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "hermes-integration workflow configuration OK" in proc.stdout


def test_positive_fixture_passes() -> None:
    proc = _run(["--check-hermes-workflow", "--root", str(FIXTURES / "positive")])
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize(
    ("uses", "with_block"),
    [
        (
            "actions/checkout@v4",
            "        with:\n"
            "          persist-credentials: false\n"
            "          ref: ${{ github.event.pull_request.head.sha || github.sha }}\n",
        ),
        (
            "astral-sh/setup-uv@v9.0.0",
            "        with:\n"
            '          version: "0.12.1"\n'
            '          python-version: "3.12.13"\n',
        ),
    ],
)
def test_action_after_network_cutoff_is_rejected(uses: str, with_block: str) -> None:
    """Network-capable actions are permitted only before the cutoff.

    These are intentionally generated from the passing fixture so the only
    violation is a correctly configured extra action below the cutoff.  The
    policy must reject that placement, not merely an invalid action shape.
    """
    source = (
        FIXTURES / "positive" / ".github" / "workflows" / "hermes-integration.yml"
    ).read_text(encoding="utf-8")
    injected = (
        f"      - uses: {uses}\n"
        f"{with_block}"
        "      - name: Offline runtime re-materialization\n"
    )
    mutated = source.replace(
        "      - name: Offline runtime re-materialization\n", injected, 1
    )
    # The bootstrap CLI intentionally restricts --root to this repository;
    # use an auto-cleaned directory beneath it so the subprocess exercises
    # the public checker rather than an internal helper.
    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
        root = Path(temporary)
        workflow = root / ".github" / "workflows" / "hermes-integration.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text(mutated, encoding="utf-8")
        proc = _run(["--check-hermes-workflow", "--root", str(root)])
        assert proc.returncode == 1
        assert "no action step may run below the network cutoff" in proc.stdout


def test_fixture_inventory_complete() -> None:
    present = {p.name for p in (FIXTURES / "negative").glob("*") if p.is_dir()}
    assert present == REQUIRED_NEGATIVE_FIXTURES


@pytest.mark.parametrize("name", sorted(REQUIRED_NEGATIVE_FIXTURES))
def test_negative_fixture_fails(name: str) -> None:
    proc = _run(
        ["--check-hermes-workflow", "--root", str(FIXTURES / "negative" / name)]
    )
    assert proc.returncode == 1, f"negative fixture {name} must fail"


def test_existing_workflow_policy_unchanged() -> None:
    """The two existing workflows and their checker still pass."""
    proc = _run(["--check-workflows", "--root", str(REPO_ROOT)])
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_committed_workflow_matches_positive_fixture() -> None:
    """Actual workflow and positive fixture must be byte-identical."""
    committed = (
        REPO_ROOT / ".github" / "workflows" / "hermes-integration.yml"
    ).read_bytes()
    fixture = (
        FIXTURES / "positive" / ".github" / "workflows" / "hermes-integration.yml"
    ).read_bytes()
    assert committed == fixture, "committed workflow diverged from positive fixture"
