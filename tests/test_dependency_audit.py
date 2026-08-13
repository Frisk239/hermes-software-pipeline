"""Dependency audit rejects a planted root runtime dependency."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from hermes_pipeline.cli._bootstrap import isolated_script_module


@pytest.fixture
def auditor() -> Iterator[Any]:
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_dependency_audit.py"
    with isolated_script_module("check_dependency_audit", path) as module:
        yield cast(Any, module)


def test_audit_accepts_empty_runtime_dependencies(auditor: Any) -> None:
    root = Path(__file__).resolve().parents[1]
    assert auditor.audit_root(root) == []
    assert auditor.main(["--root", str(root)]) == 0


def test_audit_rejects_planted_root_runtime_dependency(
    tmp_path: Path, auditor: Any
) -> None:
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'planted'\nversion = '0.0.0'\ndependencies = ['httpx']\n",
        encoding="utf-8",
    )
    findings = auditor.audit_root(tmp_path)
    assert findings
    assert "httpx" in findings[0]
    assert auditor.main(["--root", str(tmp_path)]) == 1
