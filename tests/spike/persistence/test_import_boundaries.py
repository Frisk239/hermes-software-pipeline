"""Import-boundary regression tests (slice-00-04, AC-01/AC-02/AC-11).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Positive fixtures:

- the Stage Executor boundary and the LangGraph graph spike import only
  domain values and ``ControllerCommandPort``;
- the Controller imports no SQLAlchemy, LangGraph, Alembic, filesystem, or
  concrete Adapter code;
- the domain evaluator imports no framework, I/O, clock, identity,
  randomness, or provider package (also covered by the domain tests).

Negative fixtures: a module importing the private persistence port, a
persistence Adapter, SQLAlchemy, or database files from the Stage Executor
or graph code fails the boundary scan; controller code importing SQLAlchemy
or LangGraph fails.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src" / "hermes_pipeline"

#: Top-level names forbidden in Controller code (architecture rule ARCH-06).
CONTROLLER_FORBIDDEN = {
    "sqlalchemy",
    "langgraph",
    "alembic",
    "os",
    "pathlib",
    "shutil",
    "subprocess",
    "tempfile",
    "sqlite3",
}

#: Private persistence surface forbidden in Stage Executor/graph code.
STAGE_FORBIDDEN_MODULES = (
    "hermes_pipeline.persistence",
    "hermes_pipeline.controller._persistence_port",
)

#: Top-level packages forbidden in Stage Executor/graph code (SQLAlchemy and
#: Alembic; the graph uses the stdlib ``sqlite3`` only for the checkpoint
#: connection type, which the caller owns).
STAGE_FORBIDDEN_TOPS = {"sqlalchemy", "alembic"}


def _assert_runtime_probe_succeeded(proc: subprocess.CompletedProcess[str]) -> None:
    """Assert the probe result without rendering untrusted subprocess output."""
    if proc.returncode != 0:
        raise AssertionError("runtime import-boundary probe failed")
    if proc.stdout.strip() != "[]":
        raise AssertionError("runtime import-boundary probe returned invalid marker")


def _assert_safe_diagnostic(rendered: str, expected: str, canary: str) -> None:
    """Verify diagnostic redaction without echoing the canary on regression."""
    if (
        rendered != expected
        or canary in rendered
        or chr(10) in rendered
        or chr(7) in rendered
    ):
        raise AssertionError("unsafe import-boundary diagnostic")


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            module = (
                node.module if node.level == 0 else f"{'.' * node.level}{node.module}"
            )
            found.append((node.lineno, module))
    return found


def _controller_files() -> list[Path]:
    return sorted((SRC / "controller").rglob("*.py"))


def _stage_files() -> list[Path]:
    return sorted((SRC / "stage_executor").rglob("*.py"))


def test_controller_imports_no_forbidden_dependency() -> None:
    """AC-02 negative: Controller code importing SQLAlchemy, LangGraph,
    filesystem, or a concrete Adapter fails; the real Controller files must
    never contain such imports."""
    violations: list[str] = []
    for path in _controller_files():
        for lineno, module in _imports(path):
            top = module.split(".", 1)[0]
            if top in CONTROLLER_FORBIDDEN:
                violations.append(f"{path.name}:{lineno}: {module}")
            if "adapter" in module.lower():
                violations.append(f"{path.name}:{lineno}: adapter import {module}")
    assert violations == [], f"forbidden controller imports: {violations}"


def test_stage_executor_and_graph_imports_respect_boundary() -> None:
    """AC-11 negative: Stage Executor and LangGraph graph code importing the
    private persistence port, a persistence Adapter, SQLAlchemy, or database
    files fails; the real files must never contain such imports."""
    violations: list[str] = []
    for path in _stage_files():
        for lineno, module in _imports(path):
            if module.startswith(STAGE_FORBIDDEN_MODULES):
                violations.append(f"{path.name}:{lineno}: {module}")
            top = module.split(".", 1)[0]
            if top in STAGE_FORBIDDEN_TOPS:
                violations.append(f"{path.name}:{lineno}: {module}")
    assert violations == [], f"forbidden stage imports: {violations}"


def _negative_fixture_fails_scan(tmp_path: Path, code: str) -> bool:
    """The boundary scanner must flag a module containing a forbidden
    import. This is the negative fixture: forbidden imports fail."""
    path = tmp_path / "_forbidden_fixture.py"
    path.write_text(code, encoding="utf-8")
    found = _imports(path)
    tops = {module.split(".", 1)[0] for _, module in found}
    return (
        bool(tops & CONTROLLER_FORBIDDEN)
        or bool(tops & STAGE_FORBIDDEN_TOPS)
        or any(module.startswith(STAGE_FORBIDDEN_MODULES) for _, module in found)
    )


def test_negative_fixture_controller_imports_sqlalchemy_fails(
    tmp_path: Path,
) -> None:
    assert _negative_fixture_fails_scan(tmp_path, "import sqlalchemy\n")


def test_negative_fixture_controller_imports_langgraph_fails(
    tmp_path: Path,
) -> None:
    assert _negative_fixture_fails_scan(tmp_path, "import langgraph\n")


def test_negative_fixture_stage_imports_private_port_fails(
    tmp_path: Path,
) -> None:
    code = "from hermes_pipeline.controller._persistence_port import X\n"
    assert _negative_fixture_fails_scan(tmp_path, code)


def test_negative_fixture_stage_imports_persistence_adapter_fails(
    tmp_path: Path,
) -> None:
    code = "from hermes_pipeline.persistence.sqlite_spike import Y\n"
    assert _negative_fixture_fails_scan(tmp_path, code)


def test_negative_fixture_stage_imports_database_files_fails(
    tmp_path: Path,
) -> None:
    code = "from hermes_pipeline.persistence import sqlite_spike\n"
    assert _negative_fixture_fails_scan(tmp_path, code)


def test_negative_fixture_stage_imports_sqlalchemy_fails(
    tmp_path: Path,
) -> None:
    assert _negative_fixture_fails_scan(tmp_path, "import sqlalchemy\n")


def test_controller_module_tree_passes_architecture_check() -> None:
    """AC-02 positive: the committed architecture checker reports no
    diagnostics for the spike Controller tree."""
    from hermes_pipeline.cli._architecture_check import check_package_tree

    diagnostics = check_package_tree(SRC)
    violations = [d for d in diagnostics if d.path.startswith("controller/")]
    assert violations == []


def test_domain_module_tree_passes_architecture_check() -> None:
    """AC-01 positive: the committed architecture checker reports no
    diagnostics for the spike domain tree."""
    from hermes_pipeline.cli._architecture_check import check_package_tree

    diagnostics = check_package_tree(SRC)
    violations = [d for d in diagnostics if d.path.startswith("domain/")]
    assert violations == []


def test_stage_executor_module_tree_passes_architecture_check() -> None:
    """AC-11 positive: the committed architecture checker reports no
    diagnostics for the stage executor spike tree."""
    from hermes_pipeline.cli._architecture_check import check_package_tree

    diagnostics = check_package_tree(SRC)
    violations = [d for d in diagnostics if d.path.startswith("stage_executor/")]
    assert violations == []


def test_runtime_path_imports_no_spike_dependency() -> None:
    """AC-13: --version and the normal runtime path never import a spike
    package; verified in a fresh subprocess."""
    probe = (
        "import hermes_pipeline.cli._main, sys\n"
        "loaded = sorted(\n"
        "    n for n in ('sqlalchemy', 'langgraph', 'alembic',\n"
        "                'langgraph.checkpoint.sqlite', 'sqlite_vec')\n"
        "    if n in sys.modules\n"
        ")\n"
        "print(loaded)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    _assert_runtime_probe_succeeded(proc)


def test_runtime_probe_failure_does_not_render_subprocess_output() -> None:
    """AC-13 negative: subprocess output stays out of assertion diagnostics."""
    canary = "canary-boundary-output" + chr(10) + "with-control" + chr(7)
    proc = subprocess.CompletedProcess(
        args=[], returncode=1, stdout=canary, stderr=canary
    )

    try:
        _assert_runtime_probe_succeeded(proc)
    except AssertionError as error:
        rendered = str(error)
    else:
        raise AssertionError("runtime probe failure was unexpectedly accepted")

    _assert_safe_diagnostic(rendered, "runtime import-boundary probe failed", canary)
