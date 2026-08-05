"""Structural policy tests for the Python quality workflow."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from hermes_pipeline.cli._bootstrap import isolated_script_module


@pytest.fixture
def checker() -> Iterator[Any]:
    """Load the dependency-free checker without leaking import state."""
    root = Path(__file__).resolve().parents[1]
    with isolated_script_module(
        "check_documentation", root / "scripts" / "check_documentation.py"
    ) as module:
        yield cast(Any, module)


def _copy_workflow(tmp_path: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    destination = tmp_path / ".github" / "workflows" / "python-quality.yml"
    destination.parent.mkdir(parents=True)
    shutil.copyfile(root / ".github" / "workflows" / "python-quality.yml", destination)
    return destination


def _copy_workflows(tmp_path: Path) -> tuple[Path, Path]:
    root = Path(__file__).resolve().parents[1]
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    documentation = workflows / "documentation-contracts.yml"
    quality = workflows / "python-quality.yml"
    shutil.copyfile(root / ".github" / "workflows" / documentation.name, documentation)
    shutil.copyfile(root / ".github" / "workflows" / quality.name, quality)
    return documentation, quality


def test_quality_workflow_matches_frozen_policy(checker: Any) -> None:
    report = checker.Reporter()
    checker.check_quality_workflow(Path(__file__).resolve().parents[1], report)
    assert not report.has_issues, report.render()


def test_quality_workflow_rejects_missing_command(tmp_path: Path, checker: Any) -> None:
    workflow = _copy_workflow(tmp_path)
    text = workflow.read_text(encoding="utf-8")
    workflow.write_text(
        text.replace(
            "      - name: Unit tests\n        run: uv run --offline pytest\n",
            "",
        ),
        encoding="utf-8",
    )
    report = checker.Reporter()
    checker.check_quality_workflow(tmp_path, report)
    assert report.has_issues
    assert "frozen quality command inventory" in report.render()


def test_quality_workflow_rejects_ambient_node(tmp_path: Path, checker: Any) -> None:
    workflow = _copy_workflow(tmp_path)
    text = workflow.read_text(encoding="utf-8")
    workflow.write_text(
        text.replace('      PYRIGHT_PYTHON_GLOBAL_NODE: "0"\n', ""),
        encoding="utf-8",
    )
    report = checker.Reporter()
    checker.check_quality_workflow(tmp_path, report)
    assert report.has_issues
    assert "env must be exactly" in report.render()


def test_quality_workflow_rejects_compact_secret_context(
    tmp_path: Path, checker: Any
) -> None:
    workflow = _copy_workflow(tmp_path)
    text = workflow.read_text(encoding="utf-8")
    workflow.write_text(
        text.replace("name: python-quality\n", "name: ${{secrets.TOKEN}}\n", 1),
        encoding="utf-8",
    )
    report = checker.Reporter()
    checker.check_quality_workflow(tmp_path, report)
    assert report.has_issues
    assert "must not consume GitHub secrets" in report.render()


def test_all_workflows_reject_secret_in_documentation_workflow(
    tmp_path: Path,
    checker: Any,
) -> None:
    documentation, _ = _copy_workflows(tmp_path)
    text = documentation.read_text(encoding="utf-8")
    documentation.write_text(
        text.replace(
            "name: documentation-contracts\n",
            "name: ${{ secrets['TOKEN'] }}\n",
            1,
        ),
        encoding="utf-8",
    )
    report = checker.Reporter()
    checker.check_workflows(tmp_path, report)
    assert report.has_issues
    assert "must not consume GitHub secrets" in report.render()
