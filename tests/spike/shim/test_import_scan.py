"""Shim import-boundary scan (slice-00-05, AC-02).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

The root ``__init__.py`` imports only ``hermes_shim``; ``hermes_shim/``
imports only the standard library and Hermes-guaranteed modules. No
Controller, Agent, Git, database, or runtime-dependency import; no import
of ``src/hermes_pipeline`` from the root entry or the shim.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SHIM_ROOT = REPO_ROOT / "hermes_shim"
ROOT_INIT = REPO_ROOT / "__init__.py"

# Modules the shim may import: stdlib + its own package (relative or via
# the hermes_shim prefix). Everything else is a boundary violation.
ALLOWED_TOP_LEVEL = frozenset(sys.stdlib_module_names) | {"hermes_shim"}


def _collect_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    edges: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                edges.append((node.lineno, node.module))
            elif node.level == 1:
                # Same-package relative import: allowed (hermes_shim internals).
                edges.append((node.lineno, f".{node.module or ''}"))
            else:
                edges.append((node.lineno, f"LEVEL{node.level}:{node.module or ''}"))
    return edges


def _violations(path: Path) -> list[str]:
    problems: list[str] = []
    for lineno, module in _collect_imports(path):
        if module.startswith(".") or module.startswith("hermes_shim"):
            continue
        top = module.split(".", 1)[0]
        if top not in ALLOWED_TOP_LEVEL:
            problems.append(f"{path.name}:{lineno}: import {module!r} is not stdlib")
    return problems


@pytest.mark.parametrize(
    "path",
    [
        ROOT_INIT,
        *sorted(SHIM_ROOT.glob("*.py")),
    ],
)
def test_shim_imports_are_stdlib_only(path: Path) -> None:
    assert path.is_file(), f"missing expected shim module {path}"
    assert _violations(path) == []


def test_root_init_imports_only_hermes_shim() -> None:
    text = ROOT_INIT.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            imported.append(node.module or "")
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    assert imported, "root entry must import hermes_shim"
    assert all(name == "hermes_shim" for name in imported), (
        f"root entry must import only hermes_shim: {imported}"
    )


def test_root_init_never_imports_src_package() -> None:
    text = ROOT_INIT.read_text(encoding="utf-8")
    # Only import statements matter; the docstring may mention the package.
    assert "import hermes_pipeline" not in text
    assert "from hermes_pipeline" not in text
    assert "from .hermes_pipeline" not in text


def test_shim_never_imports_src_package() -> None:
    for path in SHIM_ROOT.glob("*.py"):
        assert "src.hermes_pipeline" not in path.read_text(encoding="utf-8")
        assert "import hermes_pipeline" not in path.read_text(encoding="utf-8")


def test_negative_fixture_importing_src_package_fails() -> None:
    """A shim-like module importing src/hermes_pipeline must fail the scan."""
    fake = REPO_ROOT / "hermes_shim" / "_fake_negative.py"
    fake.write_text(
        "import hermes_pipeline\n",
        encoding="utf-8",
    )
    try:
        violations = _violations(fake)
        assert violations, "negative fixture must violate the import scan"
        assert "hermes_pipeline" in violations[0]
    finally:
        fake.unlink()


def test_negative_fixture_importing_third_party_fails() -> None:
    fake = REPO_ROOT / "hermes_shim" / "_fake_negative.py"
    fake.write_text(
        "import fastapi\n",
        encoding="utf-8",
    )
    try:
        violations = _violations(fake)
        assert violations, "negative fixture must violate the import scan"
        assert "fastapi" in violations[0]
    finally:
        fake.unlink()
