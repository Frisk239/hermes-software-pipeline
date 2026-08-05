"""Repository artifact audit behavior."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from hermes_pipeline.cli._bootstrap import isolated_script_module


@pytest.fixture
def checker() -> Iterator[Any]:
    """Load the audit script without leaking import state between tests."""
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "check_repository_artifacts.py"
    )
    with isolated_script_module("check_repository_artifacts", path) as module:
        yield cast(Any, module)


def test_artifact_checker_rejects_cache_and_bytecode(
    tmp_path: Path, checker: Any
) -> None:
    (tmp_path / "src" / "__pycache__").mkdir(parents=True)
    (tmp_path / "src" / "module.pyc").write_bytes(b"x")
    assert checker.find_artifacts(tmp_path) == [
        "src/__pycache__/",
        "src/module.pyc",
    ]


def test_artifact_checker_ignores_managed_and_fixture_roots(
    tmp_path: Path, checker: Any
) -> None:
    (tmp_path / ".venv" / "__pycache__").mkdir(parents=True)
    fixture = tmp_path / "scripts" / "fixtures" / "sample" / "__pycache__"
    fixture.mkdir(parents=True)
    assert checker.find_artifacts(tmp_path) == []
