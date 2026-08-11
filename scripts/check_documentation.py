#!/usr/bin/env python3
"""Dependency-free repository documentation checker (slice-00-01).

Validates governed text files under the repository root using only the
Python standard library:

- strict UTF-8 decoding and absence of U+FFFD replacement characters;
- balanced Markdown code fences;
- resolvable local Markdown links (external schemes and pure anchors are
  skipped);
- terminal ADR status in ``docs/adr/`` (accepted or superseded);
- required root entry point files exist (README, LICENSE, governance,
  contribution, security, support, conduct, context, constitution).

``--check-workflow`` parses ``.github/workflows/documentation-contracts.yml``
with a strict YAML-subset grammar (rejecting invalid syntax, tabs, unknown
keys, and unexpected indentation) and verifies that a job covers both
``windows-latest`` and ``ubuntu-latest`` and runs every required offline
command. This is a deterministic structural check; it does not execute the
workflow.

``--check-workflows`` applies the same syntax, runner, permissions, checkout,
credential, action-version, environment, and exact-command policies to both
the documentation and Python quality workflows.

``--self-test-negative`` executes the checker as a subprocess against the
bootstrap fixtures and asserts that positive fixtures exit 0 and every
deliberately broken fixture exits nonzero, proving the CLI's stable exit
behavior rather than reusing in-process state.

Governed-file discovery honors the checked root's ``.gitignore``: ignored
local content (``reference/`` clones, virtual environments, and standard
tool caches) is never scanned, while governed files that are not ignored
remain scanned, so equivalent unignored invalid content still fails
(AC-07, slice-00-02 correction to slice-00-01).

The checker is read-only, offline, and treats repository text as untrusted
data. It never executes repository content.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

# Keep the worktree free of __pycache__ artifacts: the checker imports a
# local module, and bytecode caching must not leave untracked files behind.
sys.dont_write_bytecode = True

from _check_common import (  # noqa: E402
    Reporter,
    fixture_roots,
    is_path_ignored,
    load_ignore_rules,
    render_bounded_lines,
    repo_root,
)

# Exit codes: 0 = pass, 1 = check failure.
EXIT_OK = 0
EXIT_FAIL = 1

# Governed text files: these suffixes plus the named extensionless files.
GOVERNED_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".txt", ".lock", ".py"}
GOVERNED_NAMES = {".gitattributes", ".gitignore", "LICENSE"}

# Terminal ADR statuses allowed by the repository (see
# docs/development/development-readiness-audit.md). A binding ADR that is
# not accepted blocks dispatch, so any other status is an error. Superseded
# ADRs are recorded as "superseded by ADR-XXXX"; the status word is the
# first token.
ALLOWED_ADR_STATUSES = {"accepted", "superseded"}

# Required root entry points (BOOT-01): product status, trust limits,
# governance, contribution, security, support, conduct, domain language,
# and repository constitution. Deleting any of them must fail the check
# even if every link to it is removed as well.
REQUIRED_ROOT_ENTRY_POINTS = (
    "README.md",
    "LICENSE",
    "GOVERNANCE.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "SUPPORT.md",
    "CODE_OF_CONDUCT.md",
    "CONTEXT.md",
    "AGENTS.md",
)

# The offline commands that CI must run on both operating systems.
REQUIRED_WORKFLOW_COMMANDS = (
    "python scripts/check_documentation.py",
    "python scripts/check_schemas.py",
    "python scripts/check_schemas.py --self-test-negative",
    "python scripts/check_documentation.py --check-workflow",
)

WORKFLOW_PATH = Path(".github/workflows/documentation-contracts.yml")
QUALITY_WORKFLOW_PATH = Path(".github/workflows/python-quality.yml")

# Allowed keys in the strict workflow grammar.
ALLOWED_WORKFLOW_TOP_LEVEL = {"name", "on", "permissions", "jobs"}
REQUIRED_WORKFLOW_ON = {"push", "pull_request"}
ALLOWED_WORKFLOW_JOB = {"strategy", "runs-on", "steps"}
ALLOWED_QUALITY_WORKFLOW_JOB = {"env", "strategy", "runs-on", "steps"}
ALLOWED_WORKFLOW_STRATEGY = {"fail-fast", "matrix"}
ALLOWED_WORKFLOW_STEP = {"uses", "name", "run", "with"}

# Exact runner binding required by the workflow checker.
MATRIX_OS_KEY = "os"
RUNS_ON_MATRIX_EXPRESSION = "${{ matrix.os }}"
REQUIRED_RUNNERS = ("windows-latest", "ubuntu-latest")
CHECKOUT_ACTION = "actions/checkout@v4"
SETUP_PYTHON_ACTION = "actions/setup-python@v5"
# Documentation workflow interpreter (stdlib-only checks; revision 7 keeps it
# at the 3.12 line and never binds it to the source-only 3.12.13 patch).
REQUIRED_PYTHON_VERSION = "3.12"
# Python quality workflow interpreter (revision 7, slice-00-04 CCR): the
# exact uv-managed CPython 3.12.13 Astral build is pinned because it links
# the SQLite library required by the WAL-reset version gate (AC-08); a
# system interpreter of the same version may link a different SQLite.
REQUIRED_QUALITY_PYTHON_VERSION = "3.12.13"
PERSIST_CREDENTIALS_DISABLED = ("false", False)
SETUP_UV_ACTION = "astral-sh/setup-uv@v9.0.0"
REQUIRED_UV_VERSION = "0.12.1"
REQUIRED_QUALITY_ENV = {
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYRIGHT_PYTHON_GLOBAL_NODE": "0",
    "PYRIGHT_PYTHON_NODEJS_WHEEL": "1",
    # Revision 7 (slice-00-04 CCR): uv must use only managed Python
    # installations so a system interpreter with a different bundled SQLite
    # can never satisfy the SQLite WAL-reset version gate.
    "UV_MANAGED_PYTHON": "1",
}
REQUIRED_QUALITY_WORKFLOW_COMMANDS = (
    "uv sync --frozen --all-groups",
    "uv run --offline ruff format --check .",
    "uv run --offline ruff check .",
    "uv run --offline pyright",
    "uv run --offline pytest",
    "uv run --offline python -m hermes_pipeline.cli contracts check",
    "uv run --offline python -m hermes_pipeline.cli contracts drift-check",
    "uv run --offline python -m hermes_pipeline.cli architecture check",
    "uv run --offline python scripts/check_documentation.py",
    "uv run --offline python scripts/check_documentation.py --self-test-negative",
    "uv run --offline python scripts/check_schemas.py --self-test-negative",
    "uv run --offline python scripts/check_documentation.py --check-workflows",
    "uv sync --frozen --all-groups --offline",
    "uv run --offline python -m hermes_pipeline.cli --version",
    "uv run --offline python -m hermes_pipeline.cli contracts check",
    "uv run --offline python -m hermes_pipeline.cli architecture check",
    "uv run --offline python scripts/check_repository_artifacts.py",
)

REQUIRED_DOC_NEGATIVE_FIXTURES = frozenset(
    {
        "broken-link",
        "invalid-utf8-adr",
        "missing-root-entry",
        "oversized-link",
        "path-escape",
        "proposed-adr",
        "replacement-char",
        "unbalanced-fence",
        "unignored-invalid",
    }
)
REQUIRED_WORKFLOW_NEGATIVE_FIXTURES = frozenset(
    {
        "bad-trigger",
        "chained-command",
        "echo-command",
        "extra-permission",
        "invalid-yaml",
        "lookalike-action",
        "missing-checkout",
        "missing-command",
        "missing-permissions",
        "missing-setup-python",
        "name-only-step",
        "persist-credentials",
        "trailing-root",
        "unbound-runs-on",
        "unclosed-quote",
        "wrong-matrix-key",
    }
)

# --------------------------------------------------------------------------
# Hermes integration workflow governance (slice-00-05 fixed technical scope)
# --------------------------------------------------------------------------
# The existing --check-workflows checker covers exactly the two existing
# workflows and does not cover hermes-integration.yml; that coverage gap is
# acknowledged and never papered over. This fixed in-Slice extension adds
# check_hermes_integration_workflow with a strict YAML-subset parse, `on:`
# exactly push/pull_request, read-only permissions, no secrets context,
# matrix coverage of ubuntu-latest and windows-latest, pinned action
# versions, the exact offline probe command inventory, and a network-cutoff
# boundary comment marker, plus positive/negative fixtures under
# scripts/fixtures/workflows/ and the verification commands
# workflow-policy-hermes / workflow-policy-hermes-negative. The two
# existing workflows and their checkers are not modified.

HERMES_WORKFLOW_PATH = Path(".github/workflows/hermes-integration.yml")
ALLOWED_HERMES_WORKFLOW_TOP_LEVEL = {"name", "on", "permissions", "jobs"}
ALLOWED_HERMES_WORKFLOW_JOB = {"strategy", "runs-on", "steps"}
ALLOWED_HERMES_WORKFLOW_STEP = {"uses", "name", "run", "with", "shell"}
HERMES_WORKFLOW_JOB_NAME = "hermes-integration"
HERMES_SHELL = "bash"
# Network-cutoff boundary comment marker (dependency bootstrap above,
# offline probes and second materialization below).
NETWORK_CUTOFF_MARKER = "# NETWORK-CUTOFF"
# The checkout step must pin the event-derived Candidate SHA up front so
# every later assertion (derive, fixture, installed checkout) is bound to
# the exact Candidate.
HERMES_CHECKOUT_REF = "${{ github.event.pull_request.head.sha || github.sha }}"
# The only network-capable actions are the first two bootstrap steps.  Their
# position is security-relevant: an action below NETWORK-CUTOFF would be able
# to fetch code after the workflow claims to be offline.
HERMES_BOOTSTRAP_ACTIONS = (CHECKOUT_ACTION, SETUP_UV_ACTION)
# Fixed bootstrap sequence before the first runtime materialization:
# checkout -> setup-uv -> bootstrap sync -> derive candidate -> provision
# Hermes -> build install fixture -> first materialization. Auxiliary
# shell: bash steps are pinned by name and content patterns; no other bash
# step is allowed anywhere in the job, and none may appear after the
# network cutoff.
HERMES_BASH_STEP_NAMES = (
    "Derive candidate SHA and verify checkout",
    "Provision pinned Hermes release into independent environment",
    "Build candidate-pinned install fixture",
)
HERMES_BOOTSTRAP_COMMAND = "uv sync --frozen --all-groups"
HERMES_FIRST_MATERIALIZATION_COMMAND = (
    "uv run --offline pytest "
    "tests/spike/runtime/test_runtime_provision.py::test_provisions_fresh_state_root"
)
# Exact offline probe command inventory of the hermes-integration job:
# bootstrap, the three runtime provision commands, the three Hermes probe
# suites, and the canonical offline command set.
REQUIRED_HERMES_WORKFLOW_COMMANDS = (
    HERMES_BOOTSTRAP_COMMAND,
    HERMES_FIRST_MATERIALIZATION_COMMAND,
    "uv run --offline pytest "
    "tests/spike/runtime/test_runtime_provision.py::test_reprovisions_fresh_state_root_offline",
    "uv run --offline pytest "
    "tests/spike/runtime/test_runtime_provision.py::test_runs_selfcheck_in_managed_environment",
    "uv run --offline pytest tests/spike/probe/install",
    "uv run --offline pytest tests/spike/probe/pluginmanager",
    "uv run --offline pytest tests/spike/probe/gateway",
    "uv run --offline ruff format --check .",
    "uv run --offline ruff check .",
    "uv run --offline pyright",
    "uv run --offline pytest",
    "uv run --offline python -m hermes_pipeline.cli contracts check",
    "uv run --offline python -m hermes_pipeline.cli contracts drift-check",
    "uv run --offline python -m hermes_pipeline.cli architecture check",
    "uv run --offline python scripts/check_documentation.py",
    "uv run --offline python scripts/check_documentation.py --self-test-negative",
    "uv run --offline python scripts/check_schemas.py --self-test-negative",
    "uv run --offline python scripts/check_documentation.py --check-workflows",
    "uv sync --frozen --all-groups --offline",
    "uv run --offline python -m hermes_pipeline.cli --version",
    "uv run --offline python scripts/check_documentation.py --check-hermes-workflow",
    "uv run --offline python scripts/check_documentation.py "
    "--check-hermes-workflow-negative",
    "uv run --offline python scripts/check_repository_artifacts.py",
)
# Commands allowed only below the cutoff marker (offline surface): the
# full inventory minus the bootstrap sync and the first materialization.
HERMES_OFFLINE_COMMANDS = frozenset(
    command
    for command in REQUIRED_HERMES_WORKFLOW_COMMANDS
    if command not in (HERMES_BOOTSTRAP_COMMAND, HERMES_FIRST_MATERIALIZATION_COMMAND)
)
# Network-implying command surface rejected in auxiliary bash steps and in
# every step below the cutoff: fetch/install tooling and remote git
# operations. ``git clone`` is deliberately excluded: the pinned provision
# step clones the pinned Hermes repository at a fixed commit and the
# fixture step clones the local workspace with ``--no-checkout``; both are
# anchored by their content patterns instead.
NETWORK_COMMAND_RE = re.compile(
    r"\b(curl|wget|pip|npm|yarn|apt|apt-get|yum|docker|podman)\b"
    r"|git (fetch|pull|remote|push)"
    r"|uv (add|remove|lock)(?![\w-]*)"
)
# Exact, reviewed scripts of the pinned auxiliary bash steps: the run body
# must equal the fixed script byte-for-byte (modulo surrounding whitespace)
# so no unauthorized command can be appended to a correctly named step.
HERMES_DERIVE_SCRIPT = (
    "set -euo pipefail\n"
    'if [ "$GITHUB_EVENT_NAME" = "pull_request" ]; then\n'
    '  candidate="${{ github.event.pull_request.head.sha }}"\n'
    "else\n"
    '  candidate="${{ github.sha }}"\n'
    "fi\n"
    'echo "HERMES_PIPELINE_CANDIDATE_SHA=$candidate" >> "$GITHUB_ENV"\n'
    'test "$(git rev-parse HEAD)" = "$candidate"'
)
HERMES_PROVISION_SCRIPT = (
    "set -euo pipefail\n"
    'HERMES_DIR="$RUNNER_TEMP/hermes-agent"\n'
    "git clone --depth 1 --branch v2026.8.3 --single-branch "
    'https://github.com/NousResearch/hermes-agent "$HERMES_DIR"\n'
    'test "$(git -C "$HERMES_DIR" rev-parse HEAD)" = '
    '"3c27eb6234bf91b8ceee9e9071591b31e9b148cb"\n'
    'uv sync --frozen --python 3.11 --project "$HERMES_DIR"\n'
    'if [ -f "$HERMES_DIR/venv/Scripts/python.exe" ]; then\n'
    '  echo "HERMES_PIPELINE_PROBE_HERMES=$HERMES_DIR/venv/Scripts/python.exe" '
    '>> "$GITHUB_ENV"\n'
    'elif [ -f "$HERMES_DIR/.venv/Scripts/python.exe" ]; then\n'
    '  echo "HERMES_PIPELINE_PROBE_HERMES=$HERMES_DIR/.venv/Scripts/python.exe" '
    '>> "$GITHUB_ENV"\n'
    'elif [ -f "$HERMES_DIR/venv/bin/python" ]; then\n'
    '  echo "HERMES_PIPELINE_PROBE_HERMES=$HERMES_DIR/venv/bin/python" '
    '>> "$GITHUB_ENV"\n'
    'elif [ -f "$HERMES_DIR/.venv/bin/python" ]; then\n'
    '  echo "HERMES_PIPELINE_PROBE_HERMES=$HERMES_DIR/.venv/bin/python" '
    '>> "$GITHUB_ENV"\n'
    "else\n"
    '  echo "Hermes interpreter not found" >&2\n'
    "  exit 1\n"
    "fi"
)
HERMES_FIXTURE_SCRIPT = (
    "set -euo pipefail\n"
    'fixture="$RUNNER_TEMP/candidate-fixture"\n'
    'git clone --no-checkout "file://$GITHUB_WORKSPACE" "$fixture"\n'
    'git -C "$fixture" checkout -B main "$HERMES_PIPELINE_CANDIDATE_SHA"\n'
    'test "$(git -C "$fixture" rev-parse HEAD)" = "$HERMES_PIPELINE_CANDIDATE_SHA"\n'
    'test "$(git -C "$fixture" rev-parse HEAD^{tree})" = '
    '"$(git -C "$GITHUB_WORKSPACE" rev-parse HEAD^{tree})"\n'
    'echo "HERMES_PIPELINE_INSTALL_FIXTURE=$fixture" >> "$GITHUB_ENV"'
)
HERMES_BASH_SCRIPTS = {
    "Derive candidate SHA and verify checkout": HERMES_DERIVE_SCRIPT,
    "Provision pinned Hermes release into independent environment": (
        HERMES_PROVISION_SCRIPT
    ),
    "Build candidate-pinned install fixture": HERMES_FIXTURE_SCRIPT,
}
REQUIRED_HERMES_WORKFLOW_NEGATIVE_FIXTURES = frozenset(
    {
        "arbitrary-bootstrap-bash",
        "bad-trigger",
        "bash-extra-clone",
        "bash-extra-curl",
        "bash-extra-env",
        "bash-extra-python-c",
        "command-before-cutoff",
        "derive-before-bootstrap",
        "extra-command",
        "invalid-yaml",
        "missing-checkout-ref",
        "missing-command",
        "missing-marker",
        "missing-permissions",
        "network-after-cutoff",
        "persist-credentials",
        "secrets-context",
        "unpinned-action",
        "wrong-job-name",
        "wrong-matrix",
    }
)

FENCE_RE = re.compile(r"^\s*```")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)")
BACKTICK_SPAN_RE = re.compile(r"`+[^`]*`+")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")
FRONTMATTER_LIMIT = 10
KEY_RE = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s*(.*))?$")
FLOW_SEQ_RE = re.compile(r"^\[(.*)\]$")
# A workflow may use either dot or bracket notation (and may nest the
# reference in a larger expression), so reject any Actions expression that
# names the secrets context rather than matching only ``secrets.NAME``.
SECRETS_CONTEXT_RE = re.compile(r"\$\{\{[^}]*\bsecrets\b[^}]*\}\}", re.IGNORECASE)


class WorkflowSyntaxError(Exception):
    """The workflow file violates the strict YAML-subset grammar."""


def _as_mapping(value: object) -> dict[str, Any] | None:
    """Return a YAML mapping with its untrusted values kept at the boundary."""
    if not isinstance(value, dict):
        return None
    return cast(dict[str, Any], value)


def _as_sequence(value: object) -> list[Any] | None:
    """Return a YAML sequence with its untrusted values kept at the boundary."""
    if not isinstance(value, list):
        return None
    return cast(list[Any], value)


# --------------------------------------------------------------------------
# Governed text checks
# --------------------------------------------------------------------------


def governed_text_files(root: Path, report: Reporter) -> list[Path]:
    """All governed text files under root, excluding .git, the deliberately
    broken self-test fixtures, and paths ignored by the root .gitignore.

    Pruning uses the checked root's own ignore rules, so fixture roots and
    non-Git roots behave exactly like the repository root: ignored local
    content never reaches the scanner, and governed unignored files are
    always scanned (AC-07).
    """
    repo = repo_root()
    fixture_tree = repo / "scripts" / "fixtures"
    rules = load_ignore_rules(root)
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(dirpath)
        if root == repo and current.is_relative_to(fixture_tree):
            dirnames[:] = []
            continue
        if ".git" in dirnames:
            dirnames.remove(".git")
        kept_dirs: list[str] = []
        for name in dirnames:
            rel = current.relative_to(root) / name
            if not is_path_ignored(rel.as_posix(), rules):
                kept_dirs.append(name)
        dirnames[:] = kept_dirs
        for name in filenames:
            path = current / name
            rel = current.relative_to(root) / name
            governed = path.suffix in GOVERNED_SUFFIXES or path.name in GOVERNED_NAMES
            if is_path_ignored(rel.as_posix(), rules):
                continue
            if path.is_symlink():
                if governed:
                    report.issue(f"{path}: governed file must not be a symbolic link")
                continue
            if not governed:
                continue
            if not path.resolve().is_relative_to(root):
                report.issue(f"{path}: governed file resolves outside the checked root")
                continue
            files.append(path)
    return files


def check_utf8(path: Path, report: Reporter) -> str | None:
    """Strict UTF-8 decode; returns decoded text or None on failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        report.issue(f"{path}: not valid UTF-8 ({exc.reason} at byte {exc.start})")
        return None
    if "\ufffd" in text:
        report.issue(f"{path}: contains U+FFFD replacement character(s)")
    return text


def check_markdown(root: Path, path: Path, text: str, report: Reporter) -> None:
    """Balanced fences and resolvable local links in one Markdown file."""
    lines = text.splitlines()
    fence_lines = [i + 1 for i, line in enumerate(lines) if FENCE_RE.match(line)]
    if len(fence_lines) % 2:
        report.issue(
            f"{path}: unbalanced code fence (odd count {len(fence_lines)}; "
            f"fence line(s) {', '.join(str(n) for n in fence_lines)})"
        )

    # Track whether we are inside a fenced block so links inside code
    # examples are not treated as documentation links.
    in_fence = False
    for lineno, line in enumerate(lines, start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # Mask inline code spans so `[x](y)` inside backticks is ignored.
        masked = BACKTICK_SPAN_RE.sub(lambda m: " " * len(m.group(0)), line)
        for target in LINK_RE.findall(masked):
            _check_link(root, path, lineno, target, report)


def _check_link(
    root: Path, path: Path, lineno: int, target: str, report: Reporter
) -> None:
    target = target.strip()
    if not target:
        return
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if not target or target.startswith("#"):
        return  # pure in-page anchor
    if SCHEME_RE.match(target):
        return  # external scheme (http:, https:, mailto:, ...)
    # Split off an optional fragment; only the file path must exist.
    path_part = target.split("#", 1)[0]
    if not path_part:
        return
    # Resolve symlinks and require the final target to remain inside the
    # checked root: a link must never probe the host filesystem (AC-05).
    resolved = (path.parent / path_part).resolve()
    if not resolved.is_relative_to(root):
        report.issue(f"{path}:{lineno}: local link escapes the checked root: {target}")
    elif not resolved.exists():
        report.issue(f"{path}:{lineno}: local link does not resolve: {target}")


def check_adr_status(root: Path, report: Reporter) -> None:
    """Every ADR under docs/adr/ has terminal accepted or superseded status.

    Files that fail strict UTF-8 decoding are skipped here: the decoding
    failure was already reported by check_utf8, and re-reading them would
    only duplicate the bounded output.
    """
    adr_dir = root / "docs" / "adr"
    if adr_dir.is_symlink() or (
        adr_dir.exists() and not adr_dir.resolve().is_relative_to(root)
    ):
        report.issue(f"{adr_dir}: ADR directory escapes the checked root")
        return
    if not adr_dir.is_dir():
        return
    for path in sorted(adr_dir.glob("*.md")):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            continue  # governed_text_files already reports the unsafe file
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        if not lines or lines[0].strip() != "---":
            report.issue(f"{path}: missing YAML frontmatter (must start with '---')")
            continue
        status: str | None = None
        closed = False
        for line in lines[1:FRONTMATTER_LIMIT]:
            stripped = line.strip()
            if stripped == "---":
                closed = True
                break
            if stripped.startswith("status:"):
                status = stripped[len("status:") :].strip().strip("\"'")
        if not closed:
            report.issue(f"{path}: unterminated YAML frontmatter")
            continue
        if status is None:
            report.issue(f"{path}: ADR frontmatter has no status field")
            continue
        # The repository records superseded ADRs as
        # "superseded by ADR-XXXX"; the terminal status is the first token.
        status_word = status.split()[0]
        if status_word not in ALLOWED_ADR_STATUSES:
            report.issue(
                f"{path}: ADR status {status!r} is not terminal "
                f"(allowed: {', '.join(sorted(ALLOWED_ADR_STATUSES))})"
            )


def check_root_entry_points(root: Path, report: Reporter) -> None:
    """Every required root entry point must exist."""
    for name in REQUIRED_ROOT_ENTRY_POINTS:
        entry = root / name
        if entry.is_symlink():
            report.issue(f"{entry}: required root entry point must not be a symlink")
        elif not entry.is_file():
            report.issue(f"{entry.resolve()}: required root entry point missing")
        elif not entry.resolve().is_relative_to(root):
            report.issue(f"{entry}: required root entry point escapes the checked root")


def check_documentation(
    root: Path,
    report: Reporter,
    expect_root_entry_points: bool = False,
) -> None:
    """Run every documentation check against root."""
    for path in governed_text_files(root, report):
        report.scanned += 1
        text = check_utf8(path, report)
        if text is None:
            continue
        if path.suffix == ".md":
            check_markdown(root, path, text, report)
    check_adr_status(root, report)
    if expect_root_entry_points:
        check_root_entry_points(root, report)


# --------------------------------------------------------------------------
# Strict workflow YAML-subset parser
# --------------------------------------------------------------------------


def _indent(raw: str) -> int:
    return len(raw) - len(raw.lstrip(" "))


def _split_key_value(content: str) -> tuple[str, str] | None:
    match = KEY_RE.match(content)
    if not match:
        return None
    return match.group(1), (match.group(2) or "").strip()


def _plain_scalar(value: str, lineno: int) -> str:
    """A plain scalar drops any trailing ' #' comment.

    Values that begin with a quote or a flow-sequence bracket must be
    properly closed; a bare plain scalar may not start with a quote at all.
    """
    if value.startswith(('"', "'")):
        quote = value[0]
        if not value.endswith(quote) or len(value) < 2:
            raise WorkflowSyntaxError(f"line {lineno}: unterminated quoted scalar")
        return value
    if value.startswith("["):
        raise WorkflowSyntaxError(f"line {lineno}: unterminated flow sequence")
    return value.split(" #", 1)[0].strip()


def _parse_mapping(
    cleaned: list[tuple[int, str]], index: int, indent: int
) -> tuple[dict[str, Any], int]:
    """Parse mapping lines at exactly `indent`; stop at shallower lines."""
    mapping: dict[str, object] = {}
    while index < len(cleaned):
        lineno, raw = cleaned[index]
        current_indent = _indent(raw)
        if current_indent < indent:
            break
        if current_indent > indent:
            raise WorkflowSyntaxError(
                f"line {lineno}: unexpected indentation (expected {indent})"
            )
        content = raw.strip()
        if content.startswith("-"):
            break  # a sequence belongs to the parent block
        key_value = _split_key_value(content)
        if key_value is None:
            raise WorkflowSyntaxError(
                f"line {lineno}: expected 'key: value', got {content!r}"
            )
        key, value = key_value
        if key in mapping:
            raise WorkflowSyntaxError(f"line {lineno}: duplicate key {key!r}")
        index += 1
        if not value:
            if index < len(cleaned) and _indent(cleaned[index][1]) > indent:
                child_indent = _indent(cleaned[index][1])
                mapping[key], index = _parse_block(cleaned, index, child_indent)
            else:
                mapping[key] = None
        elif value == "|":
            block_lines: list[str] = []
            if index < len(cleaned) and _indent(cleaned[index][1]) > indent:
                child_indent = _indent(cleaned[index][1])
                while index < len(cleaned):
                    _lineno2, raw2 = cleaned[index]
                    if _indent(raw2) < child_indent:
                        break
                    # Lines may indent deeper than child_indent (their
                    # content); only the block's base indentation is
                    # stripped, matching YAML block-scalar semantics.
                    block_lines.append(raw2[child_indent:])
                    index += 1
            mapping[key] = "\n".join(block_lines)
        elif flow_match := FLOW_SEQ_RE.match(value):
            inner = flow_match.group(1).strip()
            mapping[key] = [item.strip() for item in inner.split(",")] if inner else []
        else:
            mapping[key] = _plain_scalar(value, lineno)
    return mapping, index


def _parse_sequence(
    cleaned: list[tuple[int, str]], index: int, indent: int
) -> tuple[list[Any], int]:
    """Parse sequence items at exactly `indent` (lines starting with '-')."""
    items: list[object] = []
    while index < len(cleaned):
        lineno, raw = cleaned[index]
        current_indent = _indent(raw)
        if current_indent < indent:
            break
        if current_indent > indent:
            raise WorkflowSyntaxError(
                f"line {lineno}: unexpected indentation (expected {indent})"
            )
        content = raw.strip()
        if not content.startswith("- "):
            if content == "-":
                raise WorkflowSyntaxError(f"line {lineno}: empty sequence item")
            break
        rest = content[2:].strip()
        index += 1
        key_value = _split_key_value(rest)
        if key_value is not None:
            item: dict[str, object] = {}
            key, value = key_value
            if (
                not value
                and index < len(cleaned)
                and _indent(cleaned[index][1]) > current_indent
            ):
                child_indent = _indent(cleaned[index][1])
                item[key], index = _parse_block(cleaned, index, child_indent)
            elif value == "|":
                block_lines: list[str] = []
                if index < len(cleaned) and _indent(cleaned[index][1]) > current_indent:
                    child_indent = _indent(cleaned[index][1])
                    while index < len(cleaned):
                        _lineno2, raw2 = cleaned[index]
                        if _indent(raw2) < child_indent:
                            break
                        block_lines.append(raw2[child_indent:])
                        index += 1
                item[key] = "\n".join(block_lines)
            else:
                item[key] = _plain_scalar(value, lineno)
            if index < len(cleaned) and _indent(cleaned[index][1]) > current_indent:
                more_indent = _indent(cleaned[index][1])
                more, index = _parse_mapping(cleaned, index, more_indent)
                overlap = set(item) & set(more)
                if overlap:
                    raise WorkflowSyntaxError(
                        f"line {lineno}: duplicate sequence-item key(s): "
                        f"{', '.join(sorted(overlap))}"
                    )
                item.update(more)
            items.append(item)
        else:
            items.append(_plain_scalar(rest, lineno))
    return items, index


def _parse_block(
    cleaned: list[tuple[int, str]], index: int, indent: int
) -> tuple[dict[str, Any] | list[Any], int]:
    """Dispatch to mapping or sequence parsing based on the next line."""
    _lineno, raw = cleaned[index]
    if raw.strip().startswith("- "):
        return _parse_sequence(cleaned, index, indent)
    return _parse_mapping(cleaned, index, indent)


def parse_workflow(text: str) -> dict[str, Any]:
    """Parse the strict workflow subset into a dict.

    Raises WorkflowSyntaxError on any violation. Supports mappings, plain
    scalars, flow sequences, '|' block scalars, and full-line comments.
    Uncommented prose, tabs, unknown constructs, and inconsistent
    indentation are all rejected.
    """
    cleaned: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw:
            raise WorkflowSyntaxError(f"line {lineno}: tab character not allowed")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned.append((lineno, raw))
    if not cleaned:
        raise WorkflowSyntaxError("document is empty")
    document, index = _parse_block(cleaned, 0, 0)
    if index != len(cleaned):
        leftover = cleaned[index]
        raise WorkflowSyntaxError(
            f"line {leftover[0]}: unexpected content after document "
            f"end ({leftover[1].strip()!r})"
        )
    if not isinstance(document, dict):
        raise WorkflowSyntaxError("document must be a mapping")
    return document


# --------------------------------------------------------------------------
# Workflow configuration check
# --------------------------------------------------------------------------


def check_workflow(root: Path, report: Reporter) -> None:
    """The CI workflow is syntactically valid and covers both required OS.

    This is a deterministic structural check of the committed configuration;
    it does not execute the workflow.
    """
    workflow = root / WORKFLOW_PATH
    if workflow.is_symlink():
        report.issue(f"{workflow}: workflow file must not be a symbolic link")
        return
    if not workflow.is_file():
        report.issue(f"{workflow}: workflow file missing")
        return
    if not workflow.resolve().is_relative_to(root):
        report.issue(f"{workflow}: workflow file resolves outside the checked root")
        return
    try:
        text = workflow.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        report.issue(f"{workflow}: not valid UTF-8 ({exc.reason} at byte {exc.start})")
        return
    try:
        document = parse_workflow(text)
    except WorkflowSyntaxError as exc:
        report.issue(f"{workflow}: invalid workflow YAML ({exc})")
        return

    _check_no_secret_context(workflow, text, report)

    unknown = set(document) - ALLOWED_WORKFLOW_TOP_LEVEL
    for key in sorted(unknown):
        report.issue(f"{workflow}: unknown top-level key {key!r}")

    on_value = _as_mapping(document.get("on"))
    if on_value is None or set(on_value) != REQUIRED_WORKFLOW_ON:
        report.issue(
            f"{workflow}: 'on:' must map exactly the push and pull_request triggers"
        )
    elif any(value is not None for value in on_value.values()):
        report.issue(
            f"{workflow}: push and pull_request triggers must not contain "
            "additional configuration"
        )

    permissions = _as_mapping(document.get("permissions"))
    if permissions is None:
        report.issue(f"{workflow}: missing read-only 'permissions:' block")
    elif permissions != {"contents": "read"}:
        report.issue(
            f"{workflow}: permissions must be exactly {{'contents': 'read'}} "
            f"(got {permissions!r})"
        )

    jobs = _as_mapping(document.get("jobs"))
    if jobs is None or not jobs:
        report.issue(f"{workflow}: no job blocks found under 'jobs:'")
        return

    for job_name, raw_job in jobs.items():
        job = _as_mapping(raw_job)
        if job is None:
            report.issue(f"{workflow}: job {job_name!r} must be a mapping")
            continue
        for key in sorted(set(job) - ALLOWED_WORKFLOW_JOB):
            report.issue(f"{workflow}: job {job_name!r} has unknown key {key!r}")
        _check_job_os_coverage(workflow, job_name, job, report)
        _check_job_commands(workflow, job_name, job, report)
        _check_action_steps(workflow, job_name, job, report)


def check_quality_workflow(root: Path, report: Reporter) -> None:
    """Validate the Python quality workflow against its frozen CI policy."""
    workflow = root / QUALITY_WORKFLOW_PATH
    if workflow.is_symlink():
        report.issue(f"{workflow}: workflow file must not be a symbolic link")
        return
    if not workflow.is_file():
        report.issue(f"{workflow}: workflow file missing")
        return
    if not workflow.resolve().is_relative_to(root):
        report.issue(f"{workflow}: workflow file resolves outside the checked root")
        return
    try:
        text = workflow.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        report.issue(f"{workflow}: not valid UTF-8 ({exc.reason} at byte {exc.start})")
        return
    try:
        document = parse_workflow(text)
    except WorkflowSyntaxError as exc:
        report.issue(f"{workflow}: invalid workflow YAML ({exc})")
        return

    for key in sorted(set(document) - ALLOWED_WORKFLOW_TOP_LEVEL):
        report.issue(f"{workflow}: unknown top-level key {key!r}")
    on_value = _as_mapping(document.get("on"))
    if on_value is None or set(on_value) != REQUIRED_WORKFLOW_ON:
        report.issue(
            f"{workflow}: 'on:' must map exactly the push and pull_request triggers"
        )
    elif any(value is not None for value in on_value.values()):
        report.issue(
            f"{workflow}: push and pull_request triggers must not contain "
            "additional configuration"
        )
    permissions = _as_mapping(document.get("permissions"))
    if permissions != {"contents": "read"}:
        report.issue(f"{workflow}: permissions must be exactly {{'contents': 'read'}}")
    _check_no_secret_context(workflow, text, report)

    jobs = _as_mapping(document.get("jobs"))
    if jobs is None or set(jobs) != {"quality-checks"}:
        report.issue(f"{workflow}: jobs must contain exactly the 'quality-checks' job")
        return
    job = _as_mapping(jobs["quality-checks"])
    if job is None:
        report.issue(f"{workflow}: job 'quality-checks' must be a mapping")
        return
    for key in sorted(set(job) - ALLOWED_QUALITY_WORKFLOW_JOB):
        report.issue(f"{workflow}: job 'quality-checks' has unknown key {key!r}")
    raw_env = _as_mapping(job.get("env"))
    normalized_env = (
        {key: str(value).strip("\"'") for key, value in raw_env.items()}
        if raw_env is not None
        else raw_env
    )
    if normalized_env != REQUIRED_QUALITY_ENV:
        report.issue(
            f"{workflow}: job 'quality-checks' env must be exactly "
            f"{REQUIRED_QUALITY_ENV!r}"
        )
    _check_job_os_coverage(workflow, "quality-checks", job, report)
    _check_quality_job_commands(workflow, job, report)
    _check_quality_action_steps(workflow, job, report)


def check_workflows(root: Path, report: Reporter) -> None:
    """Validate every governed GitHub Actions workflow."""
    check_workflow(root, report)
    check_quality_workflow(root, report)


def check_hermes_integration_workflow(root: Path, report: Reporter) -> None:
    """Validate the slice-00-05 hermes-integration workflow policy.

    Deterministic structural check of the committed configuration (it does
    not execute the workflow): strict YAML-subset parse; ``on:`` exactly
    push/pull_request; ``permissions: {contents: read}``; no secrets
    context; one ``hermes-integration`` job whose matrix covers
    ubuntu-latest and windows-latest with ``runs-on`` bound to the matrix
    axis; pinned checkout/setup-uv action versions; the exact offline
    probe command inventory (auxiliary provisioning steps must declare
    ``shell: bash``); and the network-cutoff boundary comment marker.
    """
    workflow = root / HERMES_WORKFLOW_PATH
    if workflow.is_symlink():
        report.issue(f"{workflow}: workflow file must not be a symbolic link")
        return
    if not workflow.is_file():
        report.issue(f"{workflow}: workflow file missing")
        return
    if not workflow.resolve().is_relative_to(root):
        report.issue(f"{workflow}: workflow file resolves outside the checked root")
        return
    try:
        text = workflow.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        report.issue(f"{workflow}: not valid UTF-8 ({exc.reason} at byte {exc.start})")
        return
    if NETWORK_CUTOFF_MARKER not in text:
        report.issue(
            f"{workflow}: missing network-cutoff boundary marker "
            f"{NETWORK_CUTOFF_MARKER!r}"
        )
    try:
        document = parse_workflow(text)
    except WorkflowSyntaxError as exc:
        report.issue(f"{workflow}: invalid workflow YAML ({exc})")
        return

    _check_no_secret_context(workflow, text, report)

    for key in sorted(set(document) - ALLOWED_HERMES_WORKFLOW_TOP_LEVEL):
        report.issue(f"{workflow}: unknown top-level key {key!r}")
    on_value = _as_mapping(document.get("on"))
    if on_value is None or set(on_value) != REQUIRED_WORKFLOW_ON:
        report.issue(
            f"{workflow}: 'on:' must map exactly the push and pull_request triggers"
        )
    elif any(value is not None for value in on_value.values()):
        report.issue(
            f"{workflow}: push and pull_request triggers must not contain "
            "additional configuration"
        )
    permissions = _as_mapping(document.get("permissions"))
    if permissions != {"contents": "read"}:
        report.issue(
            f"{workflow}: permissions must be exactly {{'contents': 'read'}} "
            f"(got {permissions!r})"
        )
    jobs = _as_mapping(document.get("jobs"))
    if jobs is None or set(jobs) != {HERMES_WORKFLOW_JOB_NAME}:
        report.issue(
            f"{workflow}: jobs must contain exactly the "
            f"{HERMES_WORKFLOW_JOB_NAME!r} job"
        )
        return
    job = _as_mapping(jobs[HERMES_WORKFLOW_JOB_NAME])
    if job is None:
        report.issue(f"{workflow}: job {HERMES_WORKFLOW_JOB_NAME!r} must be a mapping")
        return
    for key in sorted(set(job) - ALLOWED_HERMES_WORKFLOW_JOB):
        report.issue(
            f"{workflow}: job {HERMES_WORKFLOW_JOB_NAME!r} has unknown key {key!r}"
        )
    _check_hermes_job_os_coverage(workflow, job, report)
    _check_hermes_job_commands(workflow, job, report)
    _check_hermes_action_steps(workflow, job, report)
    _check_hermes_cutoff_positions(workflow, text, job, report)


def _check_hermes_cutoff_positions(
    workflow: Path, text: str, job: dict[str, Any], report: Reporter
) -> None:
    """Every offline command must sit below the network-cutoff marker.

    The marker is a comment boundary in the file; its byte position is
    compared against each run command's occurrence so an offline-only
    command placed above the cutoff (or the first materialization placed
    below it) is rejected regardless of the step grammar.
    """
    marker_pos = text.find(NETWORK_CUTOFF_MARKER)
    if marker_pos < 0:
        return  # already reported as missing
    steps = _as_sequence(job.get("steps"))
    if steps is None:
        return
    for raw_step in steps:
        step = _as_mapping(raw_step)
        if step is None or "run" not in step:
            continue
        command = str(step.get("run", "")).strip()
        if not command:
            continue
        # Whole-line match: a bare prefix search would mis-locate shorter
        # commands (e.g. the full-suite ``uv run --offline pytest`` inside
        # the longer first-materialization command).
        line_re = re.compile(rf"(?m)^\s*run:\s*{re.escape(command)}\s*$")
        match = line_re.search(text)
        if match is None:
            continue  # YAML normalization difference; grammar checks cover it
        position = match.start()
        if command in HERMES_OFFLINE_COMMANDS and position < marker_pos:
            report.issue(
                f"{workflow}: offline command {command!r} must run below "
                "the network-cutoff marker"
            )
        if command == HERMES_FIRST_MATERIALIZATION_COMMAND and position > marker_pos:
            report.issue(
                f"{workflow}: first materialization must run above the "
                "network-cutoff marker"
            )


def _check_hermes_job_os_coverage(
    workflow: Path, job: dict[str, Any], report: Reporter
) -> None:
    """The matrix must cover exactly the two required runners."""
    strategy = _as_mapping(job.get("strategy"))
    matrix: dict[str, Any] = {}
    if strategy is not None:
        for key in sorted(set(strategy) - ALLOWED_WORKFLOW_STRATEGY):
            report.issue(f"{workflow}: hermes job has unknown strategy key {key!r}")
        parsed = _as_mapping(strategy.get("matrix"))
        if parsed is not None:
            matrix = parsed
        elif strategy.get("matrix") is not None:
            report.issue(f"{workflow}: hermes job 'matrix' must be a mapping")
    if set(matrix) != {MATRIX_OS_KEY}:
        report.issue(
            f"{workflow}: hermes job matrix must contain only the "
            f"'{MATRIX_OS_KEY}' axis"
        )
    os_values = _as_sequence(matrix.get(MATRIX_OS_KEY))
    if os_values is None:
        report.issue(
            f"{workflow}: hermes job must declare a matrix '{MATRIX_OS_KEY}' axis"
        )
    elif len(os_values) != len(REQUIRED_RUNNERS) or set(os_values) != set(
        REQUIRED_RUNNERS
    ):
        report.issue(
            f"{workflow}: hermes job matrix os must contain exactly "
            f"{', '.join(REQUIRED_RUNNERS)}"
        )
    if job.get("runs-on") != RUNS_ON_MATRIX_EXPRESSION:
        report.issue(
            f"{workflow}: hermes job runs-on must be exactly "
            f"{RUNS_ON_MATRIX_EXPRESSION} (got {job.get('runs-on')!r})"
        )


def _check_hermes_job_commands(
    workflow: Path, job: dict[str, Any], report: Reporter
) -> None:
    """Enforce the fixed bootstrap order, pinned bash steps, and the
    offline-only surface below the network cutoff.

    Step order must be exactly: bootstrap sync, the three pinned bash
    steps (derive candidate, provision Hermes, build install fixture),
    first runtime materialization, then only the frozen offline command
    set below the cutoff. Any other bash step, any network-implying
    command, or any offline command placed above the cutoff is rejected.
    """
    steps = _as_sequence(job.get("steps"))
    if steps is None:
        report.issue(f"{workflow}: hermes job has no steps list")
        return
    expected_bash = list(HERMES_BASH_STEP_NAMES)
    bootstrap_action_index = 0
    bash_index = 0
    bootstrap_done = False
    materialized = False
    seen_offline: list[str] = []
    for step_index, raw_step in enumerate(steps):
        step = _as_mapping(raw_step)
        if step is None:
            report.issue(f"{workflow}: hermes job has a malformed step")
            continue
        for key in sorted(set(step) - ALLOWED_HERMES_WORKFLOW_STEP):
            report.issue(f"{workflow}: hermes job step has unknown key {key!r}")
        has_run = "run" in step
        has_uses = "uses" in step
        if has_run == has_uses:
            report.issue(
                f"{workflow}: hermes job step must contain exactly "
                "one of 'run' or 'uses'"
            )
            continue
        if not has_run:
            uses = step.get("uses")
            if materialized:
                report.issue(
                    f"{workflow}: no action step may run below the network cutoff"
                )
                continue
            if bootstrap_done:
                report.issue(
                    f"{workflow}: action steps must be the first two pinned "
                    "bootstrap steps"
                )
                continue
            expected_action = (
                HERMES_BOOTSTRAP_ACTIONS[bootstrap_action_index]
                if bootstrap_action_index < len(HERMES_BOOTSTRAP_ACTIONS)
                else None
            )
            if step_index >= len(HERMES_BOOTSTRAP_ACTIONS) or uses != expected_action:
                report.issue(
                    f"{workflow}: action steps must be exactly the first "
                    f"{len(HERMES_BOOTSTRAP_ACTIONS)} pinned bootstrap actions"
                )
                continue
            bootstrap_action_index += 1
            continue
        run = step["run"]
        if step.get("with") is not None:
            report.issue(f"{workflow}: hermes job run step cannot contain 'with'")
        if not isinstance(run, str) or not run.strip():
            report.issue(f"{workflow}: hermes job has an empty run step")
            continue
        command = run.strip()
        if not materialized and bootstrap_action_index != len(HERMES_BOOTSTRAP_ACTIONS):
            report.issue(
                f"{workflow}: the first {len(HERMES_BOOTSTRAP_ACTIONS)} steps "
                "must be the pinned bootstrap actions"
            )
            continue
        if step.get("shell") is not None:
            if step.get("shell") != HERMES_SHELL:
                report.issue(
                    f"{workflow}: auxiliary run step must declare "
                    f"shell: {HERMES_SHELL} (got {step.get('shell')!r})"
                )
                continue
            if materialized:
                report.issue(
                    f"{workflow}: no bash step may run below the network cutoff"
                )
                continue
            if not bootstrap_done:
                report.issue(
                    f"{workflow}: pinned bash step must follow the bootstrap sync"
                )
            name = step.get("name")
            if (
                not isinstance(name, str)
                or bash_index >= len(expected_bash)
                or name != expected_bash[bash_index]
            ):
                report.issue(
                    f"{workflow}: bash steps must be exactly the pinned "
                    f"sequence {expected_bash!r} (got {name!r})"
                )
                continue
            _check_hermes_bash_content(workflow, name, command, report)
            bash_index += 1
            continue
        if materialized:
            if command not in HERMES_OFFLINE_COMMANDS:
                report.issue(
                    f"{workflow}: below the network cutoff only the frozen "
                    f"offline command set is allowed (got {command!r})"
                )
            else:
                seen_offline.append(command)
            continue
        if command == HERMES_BOOTSTRAP_COMMAND and not bootstrap_done:
            bootstrap_done = True
        elif (
            command == HERMES_FIRST_MATERIALIZATION_COMMAND
            and bootstrap_done
            and bash_index == len(expected_bash)
        ):
            materialized = True
        elif command == HERMES_BOOTSTRAP_COMMAND:
            report.issue(
                f"{workflow}: bootstrap sync must run exactly once, before "
                "the pinned bash steps"
            )
        elif command == HERMES_FIRST_MATERIALIZATION_COMMAND:
            report.issue(
                f"{workflow}: first materialization must follow the "
                "bootstrap sync and all pinned bash steps"
            )
        else:
            report.issue(
                f"{workflow}: unsupported bootstrap-phase run command {command!r}"
            )
    if not materialized:
        report.issue(
            f"{workflow}: hermes job must complete bootstrap sync, the "
            "pinned bash steps, and the first materialization before the "
            "offline command set"
        )
    if bootstrap_action_index != len(HERMES_BOOTSTRAP_ACTIONS):
        report.issue(
            f"{workflow}: hermes job must begin with the pinned bootstrap "
            "actions before any run step"
        )
    if sorted(seen_offline) != sorted(HERMES_OFFLINE_COMMANDS):
        report.issue(
            f"{workflow}: hermes job offline commands must match the frozen "
            "offline inventory exactly"
        )


def _check_hermes_bash_content(
    workflow: Path, name: str, command: str, report: Reporter
) -> None:
    """Validate one pinned bash step's body against the fixed script.

    The body must equal the reviewed script exactly (whitespace-stripped);
    any appended or altered command — curl, python -c, an extra clone, an
    environment read — changes the bytes and is rejected.
    """
    script = HERMES_BASH_SCRIPTS[name]
    if command.strip() != script.strip():
        report.issue(
            f"{workflow}: bash step {name!r} must match the fixed reviewed "
            "script exactly (no appended or altered commands)"
        )


def _check_hermes_action_steps(
    workflow: Path, job: dict[str, Any], report: Reporter
) -> None:
    """Pin the checkout and setup-uv actions with exact safe settings."""
    steps = _as_sequence(job.get("steps"))
    if steps is None:
        return
    counts = {CHECKOUT_ACTION: 0, SETUP_UV_ACTION: 0}
    for raw_step in steps:
        step = _as_mapping(raw_step)
        if step is None or "uses" not in step:
            continue
        uses = step.get("uses")
        with_block = _as_mapping(step.get("with"))
        if uses == CHECKOUT_ACTION:
            counts[CHECKOUT_ACTION] += 1
            if not (
                with_block is not None
                and set(with_block) == {"persist-credentials", "ref"}
                and with_block.get("persist-credentials")
                in PERSIST_CREDENTIALS_DISABLED
                and str(with_block.get("ref")) == HERMES_CHECKOUT_REF
            ):
                report.issue(
                    f"{workflow}: checkout step must set only "
                    "with.persist-credentials: false and the exact "
                    "event-derived Candidate ref"
                )
        elif uses == SETUP_UV_ACTION:
            counts[SETUP_UV_ACTION] += 1
            if not (
                with_block is not None
                and set(with_block) == {"version", "python-version"}
                and str(with_block.get("version")).strip("\"'") == REQUIRED_UV_VERSION
                and str(with_block.get("python-version")).strip("\"'")
                == REQUIRED_QUALITY_PYTHON_VERSION
            ):
                report.issue(
                    f"{workflow}: setup-uv step must pin uv "
                    f"{REQUIRED_UV_VERSION} and Python "
                    f"{REQUIRED_QUALITY_PYTHON_VERSION}"
                )
        else:
            report.issue(f"{workflow}: unsupported action {uses!r}")
    for action, count in counts.items():
        if count != 1:
            report.issue(f"{workflow}: must use {action} exactly once")


def _check_no_secret_context(workflow: Path, text: str, report: Reporter) -> None:
    """Reject GitHub Actions secret-context interpolation in either workflow."""
    if SECRETS_CONTEXT_RE.search(text):
        report.issue(f"{workflow}: workflow must not consume GitHub secrets")


def _check_quality_job_commands(
    workflow: Path, job: dict[str, Any], report: Reporter
) -> None:
    """Require the exact quality command multiset, including repeated smokes."""
    steps = _as_sequence(job.get("steps"))
    if steps is None:
        report.issue(f"{workflow}: job 'quality-checks' has no steps list")
        return
    commands: list[str] = []
    for raw_step in steps:
        step = _as_mapping(raw_step)
        if step is None:
            report.issue(f"{workflow}: job 'quality-checks' has a malformed step")
            continue
        for key in sorted(set(step) - ALLOWED_WORKFLOW_STEP):
            report.issue(
                f"{workflow}: job 'quality-checks' step has unknown key {key!r}"
            )
        has_run = "run" in step
        has_uses = "uses" in step
        if has_run == has_uses:
            report.issue(
                f"{workflow}: job 'quality-checks' step must contain exactly "
                "one of 'run' or 'uses'"
            )
        if has_run:
            if step.get("with") is not None:
                report.issue(
                    f"{workflow}: job 'quality-checks' run step cannot contain 'with'"
                )
            run = step.get("run")
            if not isinstance(run, str) or not run.strip():
                report.issue(f"{workflow}: job 'quality-checks' has an empty run step")
            else:
                commands.append(run.strip())
    if Counter(commands) != Counter(REQUIRED_QUALITY_WORKFLOW_COMMANDS):
        report.issue(
            f"{workflow}: job 'quality-checks' run commands must match the "
            "frozen quality command inventory exactly"
        )


def _check_quality_action_steps(
    workflow: Path, job: dict[str, Any], report: Reporter
) -> None:
    """Require checkout and setup-uv exactly once with safe frozen settings."""
    steps = _as_sequence(job.get("steps"))
    if steps is None:
        return
    counts = {CHECKOUT_ACTION: 0, SETUP_UV_ACTION: 0}
    for raw_step in steps:
        step = _as_mapping(raw_step)
        if step is None or "uses" not in step:
            continue
        uses = step.get("uses")
        with_block = _as_mapping(step.get("with"))
        if uses == CHECKOUT_ACTION:
            counts[CHECKOUT_ACTION] += 1
            if not (
                with_block is not None
                and set(with_block) == {"persist-credentials"}
                and with_block.get("persist-credentials")
                in PERSIST_CREDENTIALS_DISABLED
            ):
                report.issue(
                    f"{workflow}: checkout step must set only "
                    "with.persist-credentials: false"
                )
        elif uses == SETUP_UV_ACTION:
            counts[SETUP_UV_ACTION] += 1
            if not (
                with_block is not None
                and set(with_block) == {"version", "python-version"}
                and str(with_block.get("version")).strip("\"'") == REQUIRED_UV_VERSION
                and str(with_block.get("python-version")).strip("\"'")
                == REQUIRED_QUALITY_PYTHON_VERSION
            ):
                report.issue(
                    f"{workflow}: setup-uv step must pin uv "
                    f"{REQUIRED_UV_VERSION} and Python "
                    f"{REQUIRED_QUALITY_PYTHON_VERSION}"
                )
        else:
            report.issue(f"{workflow}: unsupported action {uses!r}")
    for action, count in counts.items():
        if count != 1:
            report.issue(f"{workflow}: must use {action} exactly once")


def _check_job_os_coverage(
    workflow: Path, job_name: str, job: dict[str, Any], report: Reporter
) -> None:
    """The matrix must declare an 'os' axis covering both required runners
    and runs-on must bind exactly to that axis expression."""
    strategy = _as_mapping(job.get("strategy"))
    matrix: dict[str, Any] = {}
    if strategy is not None:
        for key in sorted(set(strategy) - ALLOWED_WORKFLOW_STRATEGY):
            report.issue(
                f"{workflow}: job {job_name!r} has unknown strategy key {key!r}"
            )
        candidate = strategy.get("matrix")
        parsed_matrix = _as_mapping(candidate)
        if parsed_matrix is not None:
            matrix = parsed_matrix
        elif candidate is not None:
            report.issue(f"{workflow}: job {job_name!r} 'matrix' must be a mapping")
    if set(matrix) != {MATRIX_OS_KEY}:
        report.issue(
            f"{workflow}: job {job_name!r} matrix must contain only "
            f"the '{MATRIX_OS_KEY}' axis"
        )
    os_values = _as_sequence(matrix.get(MATRIX_OS_KEY))
    if os_values is None:
        report.issue(
            f"{workflow}: job {job_name!r} must declare a matrix "
            f"'{MATRIX_OS_KEY}' list axis"
        )
    else:
        if len(os_values) != len(REQUIRED_RUNNERS) or set(os_values) != set(
            REQUIRED_RUNNERS
        ):
            report.issue(
                f"{workflow}: job {job_name!r} matrix os must contain "
                f"exactly {', '.join(REQUIRED_RUNNERS)}"
            )
    if job.get("runs-on") != RUNS_ON_MATRIX_EXPRESSION:
        report.issue(
            f"{workflow}: job {job_name!r} runs-on must be exactly "
            f"{RUNS_ON_MATRIX_EXPRESSION} (got {job.get('runs-on')!r})"
        )


def _check_job_commands(
    workflow: Path, job_name: str, job: dict[str, Any], report: Reporter
) -> None:
    """Every run step must be exactly one required offline command.

    Substring matching is deliberately avoided: 'echo python ...', chained
    ('&&', ';', '|') and decorated commands are not exact members and are
    rejected.
    """
    steps = _as_sequence(job.get("steps"))
    if steps is None:
        report.issue(f"{workflow}: job {job_name!r} has no steps list")
        return
    run_commands: list[str] = []
    for raw_step in steps:
        step = _as_mapping(raw_step)
        if step is None:
            report.issue(f"{workflow}: job {job_name!r} has a malformed step")
            continue
        for key in sorted(set(step) - ALLOWED_WORKFLOW_STEP):
            report.issue(f"{workflow}: job {job_name!r} step has unknown key {key!r}")
        has_run = "run" in step
        has_uses = "uses" in step
        if has_run == has_uses:
            report.issue(
                f"{workflow}: job {job_name!r} step must contain exactly "
                "one of 'run' or 'uses'"
            )
        if not has_run:
            continue
        run = step["run"]
        if step.get("with") is not None:
            report.issue(f"{workflow}: job {job_name!r} run step cannot contain 'with'")
        if not isinstance(run, str) or not run.strip():
            report.issue(f"{workflow}: job {job_name!r} has an empty run step")
            continue
        command = run.strip()
        if command not in REQUIRED_WORKFLOW_COMMANDS:
            report.issue(
                f"{workflow}: job {job_name!r} has unsupported run command "
                f"{command!r} (only the required offline commands are allowed)"
            )
            continue
        run_commands.append(command)
    if len(run_commands) != len(REQUIRED_WORKFLOW_COMMANDS) or set(run_commands) != set(
        REQUIRED_WORKFLOW_COMMANDS
    ):
        report.issue(
            f"{workflow}: job {job_name!r} must run each required offline "
            "command exactly once"
        )


def _check_action_steps(
    workflow: Path, job_name: str, job: dict[str, Any], report: Reporter
) -> None:
    """Require the two approved action steps with exact safe configuration."""
    steps = _as_sequence(job.get("steps"))
    if steps is None:
        return
    checkout_count = 0
    setup_count = 0
    for raw_step in steps:
        step = _as_mapping(raw_step)
        if step is None:
            continue
        uses = step.get("uses")
        if uses is None:
            continue
        if not isinstance(uses, str):
            report.issue(f"{workflow}: job {job_name!r} has non-string action")
            continue
        with_block = _as_mapping(step.get("with"))
        if uses == CHECKOUT_ACTION:
            checkout_count += 1
            disabled = (
                with_block is not None
                and set(with_block) == {"persist-credentials"}
                and with_block.get("persist-credentials")
                in PERSIST_CREDENTIALS_DISABLED
            )
            if not disabled:
                report.issue(
                    f"{workflow}: job {job_name!r} checkout step must set "
                    "only with.persist-credentials: false"
                )
        elif uses == SETUP_PYTHON_ACTION:
            setup_count += 1
            configured = (
                with_block is not None
                and set(with_block) == {"python-version"}
                and str(with_block.get("python-version")).strip("\"'")
                == REQUIRED_PYTHON_VERSION
            )
            if not configured:
                report.issue(
                    f"{workflow}: job {job_name!r} setup-python step must set "
                    f"only with.python-version: {REQUIRED_PYTHON_VERSION}"
                )
        else:
            report.issue(
                f"{workflow}: job {job_name!r} uses unsupported action {uses!r}"
            )
    if checkout_count != 1:
        report.issue(
            f"{workflow}: job {job_name!r} must use {CHECKOUT_ACTION} exactly once"
        )
    if setup_count != 1:
        report.issue(
            f"{workflow}: job {job_name!r} must use {SETUP_PYTHON_ACTION} exactly once"
        )


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------


def run_self_test_negative(root: Path) -> tuple[list[str], bool]:
    """Execute the checker as a subprocess against the bootstrap fixtures.

    A fixture passes only when the checker command exits 0 for positive
    fixtures and exits nonzero for negative fixtures, proving the stable
    CLI exit behavior. Returns (rendered lines, all_ok).
    """
    script = Path(__file__).resolve()
    lines: list[str] = []
    all_ok = True

    def run_case(name: str, argv: list[str], should_pass: bool) -> None:
        nonlocal all_ok
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            ok = False
            proc = None
        else:
            expected_code = EXIT_OK if should_pass else EXIT_FAIL
            ok = proc.returncode == expected_code
        all_ok = all_ok and ok
        actual = "timeout" if proc is None else f"exit {proc.returncode}"
        lines.append(
            f"fixture {name}: expected exit "
            f"{EXIT_OK if should_pass else EXIT_FAIL}, got {actual} -> "
            f"{'PASS' if ok else 'FAIL'}"
        )
        if proc is None:
            lines.append("  (subprocess timed out)")
            return
        detail = (proc.stdout + proc.stderr).strip().splitlines()
        for line in detail[:8]:
            lines.append(f"  {line}")
        if len(detail) > 8:
            lines.append("  ... (output truncated)")

    try:
        doc_fixtures = fixture_roots(
            root,
            "positive",
            "negative/docs",
            REQUIRED_DOC_NEGATIVE_FIXTURES,
        )
        workflow_fixtures = fixture_roots(
            root,
            "positive/workflow",
            "negative/workflow",
            REQUIRED_WORKFLOW_NEGATIVE_FIXTURES,
        )
    except ValueError as exc:
        return [f"fixture inventory: FAIL ({exc})"], False

    ignored_fixture = root / "scripts" / "fixtures" / "ignored-paths"
    if not ignored_fixture.is_dir():
        return [
            "fixture inventory: FAIL (missing scripts/fixtures/ignored-paths)"
        ], False
    doc_fixtures.append(("ignored-paths", ignored_fixture, True))

    for name, path, should_pass in doc_fixtures:
        extra = (
            ["--check-root-entry-points"]
            if name in ("positive", "missing-root-entry")
            else []
        )
        run_case(
            f"docs/{name}",
            [sys.executable, str(script), "--root", str(path), *extra],
            should_pass,
        )
    for name, path, should_pass in workflow_fixtures:
        run_case(
            f"workflow/{name}",
            [sys.executable, str(script), "--check-workflow", "--root", str(path)],
            should_pass,
        )
    return lines, all_ok


def run_hermes_workflow_self_test(root: Path) -> tuple[list[str], bool]:
    """Execute the checker against the hermes-integration workflow fixtures.

    The positive fixture passes and every negative fixture exits nonzero,
    proving the stable CLI exit behavior of the fixed workflow-governance
    extension.
    """
    script = Path(__file__).resolve()
    lines: list[str] = []
    all_ok = True

    def run_case(name: str, argv: list[str], should_pass: bool) -> None:
        nonlocal all_ok
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            ok = False
            proc = None
        else:
            expected_code = EXIT_OK if should_pass else EXIT_FAIL
            ok = proc.returncode == expected_code
        all_ok = all_ok and ok
        actual = "timeout" if proc is None else f"exit {proc.returncode}"
        lines.append(
            f"hermes-workflow fixture {name}: expected exit "
            f"{EXIT_OK if should_pass else EXIT_FAIL}, got {actual} -> "
            f"{'PASS' if ok else 'FAIL'}"
        )

    try:
        fixtures = fixture_roots(
            root,
            "workflows/positive",
            "workflows/negative",
            REQUIRED_HERMES_WORKFLOW_NEGATIVE_FIXTURES,
        )
    except ValueError as exc:
        return [f"hermes-workflow fixture inventory: FAIL ({exc})"], False
    for name, path, should_pass in fixtures:
        run_case(
            name,
            [
                sys.executable,
                str(script),
                "--check-hermes-workflow",
                "--root",
                str(path),
            ],
            should_pass,
        )
    return lines, all_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dependency-free repository documentation checker."
    )
    parser.add_argument(
        "--root",
        default=None,
        help="repository/docs root to check (default: repository root)",
    )
    parser.add_argument(
        "--check-root-entry-points",
        action="store_true",
        help="validate required root entry point files",
    )
    parser.add_argument(
        "--self-test-negative",
        action="store_true",
        help="execute the checker against broken fixtures and assert nonzero exits",
    )
    parser.add_argument(
        "--check-workflow",
        action="store_true",
        help="validate the documentation CI workflow (backward-compatible)",
    )
    parser.add_argument(
        "--check-workflows",
        action="store_true",
        help="validate all governed CI workflows and exact command mappings",
    )
    parser.add_argument(
        "--check-hermes-workflow",
        action="store_true",
        help="validate the hermes-integration CI workflow policy (slice-00-05)",
    )
    parser.add_argument(
        "--check-hermes-workflow-negative",
        action="store_true",
        help="execute the hermes-integration workflow fixtures and "
        "assert nonzero exits",
    )
    args = parser.parse_args(argv)
    if args.check_workflow and args.check_workflows:
        parser.error("--check-workflow and --check-workflows are mutually exclusive")

    repository = repo_root()
    root = Path(args.root).resolve() if args.root else repository
    report = Reporter()
    if not root.is_relative_to(repository):
        report.issue(f"{root}: checked root must remain inside the repository")
    if args.check_workflow:
        if not report.has_issues:
            check_workflow(root, report)
    elif args.check_workflows:
        if not report.has_issues:
            check_workflows(root, report)
    elif args.check_hermes_workflow:
        if not report.has_issues:
            check_hermes_integration_workflow(root, report)
    else:
        if not report.has_issues:
            check_documentation(
                root,
                report,
                expect_root_entry_points=args.check_root_entry_points
                or root == repository,
            )

    self_test_lines: list[str] = []
    self_test_ok = True
    if args.self_test_negative:
        self_test_lines, self_test_ok = run_self_test_negative(root)
    elif args.check_hermes_workflow_negative:
        self_test_lines, self_test_ok = run_hermes_workflow_self_test(root)

    if report.has_issues:
        print("check_documentation: FAIL")
        print(report.render())
        return EXIT_FAIL
    if not self_test_ok:
        print("check_documentation: FAIL (self-test-negative)")
        print(render_bounded_lines(self_test_lines))
        return EXIT_FAIL
    if args.self_test_negative or args.check_hermes_workflow_negative:
        print(render_bounded_lines(self_test_lines))
    if args.check_workflow or args.check_workflows:
        print("check_documentation: workflow configuration OK")
    elif args.check_hermes_workflow:
        print("check_documentation: hermes-integration workflow configuration OK")
    else:
        print(
            f"check_documentation: OK ({report.scanned} governed text file(s) checked)"
        )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
