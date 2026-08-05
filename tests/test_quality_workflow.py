"""Structural policy tests for the Python quality workflow."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType


def _load_checker() -> ModuleType:
    root = Path(__file__).resolve().parents[1]
    scripts = root / "scripts"
    sys.path.insert(0, str(scripts))
    path = scripts / "check_documentation.py"
    spec = importlib.util.spec_from_file_location("check_documentation", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _copy_workflow(tmp_path: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    destination = tmp_path / ".github" / "workflows" / "python-quality.yml"
    destination.parent.mkdir(parents=True)
    shutil.copyfile(root / ".github" / "workflows" / "python-quality.yml", destination)
    return destination


def test_quality_workflow_matches_frozen_policy() -> None:
    checker = _load_checker()
    report = checker.Reporter()
    checker.check_quality_workflow(Path(__file__).resolve().parents[1], report)
    assert not report.has_issues, report.render()


def test_quality_workflow_rejects_missing_command(tmp_path: Path) -> None:
    checker = _load_checker()
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


def test_quality_workflow_rejects_ambient_node(tmp_path: Path) -> None:
    checker = _load_checker()
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


def test_quality_workflow_rejects_compact_secret_context(tmp_path: Path) -> None:
    checker = _load_checker()
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
