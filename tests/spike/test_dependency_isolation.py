"""Dependency isolation regression (slice-00-04, AC-13).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

SQLAlchemy Core, Alembic, LangGraph, and ``langgraph-checkpoint-sqlite``
with the full locked transitive graph (including ``sqlite-vec``) exist only
in the ``dev`` dependency group; ``[project].dependencies`` stays empty;
the Hermes plugin entry, ``--version``, and the normal runtime path never
import them. ``uv.lock`` is frozen (enforced by the frozen-sync and
offline-sync commands in the canonical set); this file proves the runtime
path and the declared dependency boundary.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "hermes_pipeline"

#: Spike dependency families that must never appear in the runtime path.
SPIKE_PACKAGE_NAMES = {
    "sqlalchemy",
    "alembic",
    "langgraph",
    "langgraph_checkpoint_sqlite",
    "sqlite_vec",
}

#: The normal runtime path files (contract-listed).
RUNTIME_PATH_FILES = (
    SRC / "__init__.py",
    SRC / "cli" / "__init__.py",
    SRC / "cli" / "_main.py",
    SRC / "cli" / "__main__.py",
)


def _assert_version_probe_succeeded(proc: subprocess.CompletedProcess[str]) -> None:
    """Assert the probe result without rendering untrusted subprocess output."""
    if proc.returncode != 0:
        raise AssertionError("runtime dependency isolation probe failed")
    if "LOADED []" not in proc.stdout:
        raise AssertionError(
            "runtime dependency isolation probe returned invalid marker"
        )


def _assert_safe_diagnostic(rendered: str, expected: str, canary: str) -> None:
    """Verify diagnostic redaction without echoing the canary on regression."""
    if (
        rendered != expected
        or canary in rendered
        or chr(10) in rendered
        or chr(7) in rendered
    ):
        raise AssertionError("unsafe dependency-isolation diagnostic")


def _runtime_path_imports() -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for path in RUNTIME_PATH_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.append((path.name, node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.append((path.name, node.lineno, node.module))
    return found


def test_runtime_path_files_never_import_spike_packages() -> None:
    """Negative: importing a spike package from --version or the runtime
    path fails; the committed runtime path files must never contain such
    imports."""
    violations = [
        f"{name}:{lineno}: {module}"
        for name, lineno, module in _runtime_path_imports()
        if module.split(".", 1)[0] in SPIKE_PACKAGE_NAMES
    ]
    assert violations == [], f"runtime path imports spike packages: {violations}"


def test_version_subprocess_loads_no_spike_module() -> None:
    """--version works with no spike import in the interpreter."""
    probe = (
        "from hermes_pipeline.cli._main import main\n"
        "code = main(['--version'])\n"
        "import sys\n"
        "loaded = sorted(n for n in sys.modules if n.split('.')[0] in "
        "{'sqlalchemy', 'alembic', 'langgraph', 'sqlite_vec'})\n"
        "print('LOADED', loaded)\n"
        "raise SystemExit(code)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    _assert_version_probe_succeeded(proc)


def test_version_probe_failure_does_not_render_subprocess_output() -> None:
    """AC-13 negative: subprocess output stays out of assertion diagnostics."""
    canary = "canary-version-output" + chr(10) + "with-control" + chr(7)
    proc = subprocess.CompletedProcess(
        args=[], returncode=1, stdout=canary, stderr=canary
    )

    try:
        _assert_version_probe_succeeded(proc)
    except AssertionError as error:
        rendered = str(error)
    else:
        raise AssertionError("version probe failure was unexpectedly accepted")

    _assert_safe_diagnostic(
        rendered, "runtime dependency isolation probe failed", canary
    )


def test_project_dependencies_stay_empty() -> None:
    """[project].dependencies stays empty: no runtime dependency family was
    introduced by the spike."""
    with open(REPO_ROOT / "pyproject.toml", "rb") as handle:
        project = tomllib.load(handle)
    assert project["project"]["dependencies"] == []


def test_spike_families_are_dev_group_only() -> None:
    """The spike dependency families appear only in the dev dependency
    group of pyproject.toml."""
    with open(REPO_ROOT / "pyproject.toml", "rb") as handle:
        project = tomllib.load(handle)
    dev = project["dependency-groups"]["dev"]
    joined = "\n".join(dev)
    for family in (
        "sqlalchemy",
        "alembic",
        "langgraph",
        "langgraph-checkpoint-sqlite",
    ):
        assert family in joined, f"{family} missing from dev group"
    assert "sqlite-vec" in (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")


def test_compatibility_doc_records_exact_locked_versions() -> None:
    """AC-13 (rework 2, P1-5): docs/development/compatibility-targets.md
    records the exact locked versions of the spike dependency family and
    its key transitive dependencies; every recorded version must match the
    frozen uv.lock (parsed and compared, never duplicated by hand)."""
    with open(REPO_ROOT / "uv.lock", "rb") as handle:
        lock = tomllib.load(handle)
    locked = {pkg["name"]: pkg["version"] for pkg in lock["package"]}

    doc_path = REPO_ROOT / "docs" / "development" / "compatibility-targets.md"
    doc = doc_path.read_text(encoding="utf-8")
    section = doc.split("## Slice-00-04 dev-only spike dependency locks")[1]
    section = section.split("## ")[0]

    for name in (
        "sqlalchemy",
        "alembic",
        "langgraph",
        "langgraph-checkpoint-sqlite",
        "sqlite-vec",
        "langgraph-checkpoint",
        "langgraph-sdk",
        "langchain-core",
        "orjson",
        "greenlet",
        "typing-extensions",
    ):
        assert name in locked, f"{name} missing from uv.lock"
        expected_row = f"| `{name}` | `{locked[name]}` |"
        assert expected_row in section, (
            f"compatibility-targets.md does not record {name} at its exact "
            f"locked version {locked[name]}"
        )
