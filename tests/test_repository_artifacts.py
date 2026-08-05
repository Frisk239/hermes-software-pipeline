"""Repository artifact audit behavior."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_checker() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "check_repository_artifacts.py"
    )
    spec = importlib.util.spec_from_file_location("check_repository_artifacts", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_artifact_checker_rejects_cache_and_bytecode(tmp_path: Path) -> None:
    checker = _load_checker()
    (tmp_path / "src" / "__pycache__").mkdir(parents=True)
    (tmp_path / "src" / "module.pyc").write_bytes(b"x")
    assert checker.find_artifacts(tmp_path) == [
        "src/__pycache__/",
        "src/module.pyc",
    ]


def test_artifact_checker_ignores_managed_and_fixture_roots(tmp_path: Path) -> None:
    checker = _load_checker()
    (tmp_path / ".venv" / "__pycache__").mkdir(parents=True)
    fixture = tmp_path / "scripts" / "fixtures" / "sample" / "__pycache__"
    fixture.mkdir(parents=True)
    assert checker.find_artifacts(tmp_path) == []
