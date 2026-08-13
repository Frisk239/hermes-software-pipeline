"""Sealed browser-runtime materialization and npm argv execution.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from hermes_pipeline.runtime_broker._identity import (
    load_tool_lock,
    npm_argv,
    verify_browser_inputs,
)
from hermes_pipeline.runtime_broker._process import run_fenced


def materialize_browser_project(
    lock: dict[str, Any], repo_root: Path, state_root: Path
) -> Path:
    """Byte-copy committed package files into a fresh state-root project."""
    verify_browser_inputs(lock, repo_root)
    inputs = lock["browser_runtime_inputs"]
    project = state_root / "tools" / "browser-runtime" / "project"
    project.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(repo_root / inputs["package_manifest"], project / "package.json")
    shutil.copyfile(repo_root / inputs["lockfile"], project / "package-lock.json")
    npmrc = state_root / "tools" / "browser-runtime" / "npmrc"
    npmrc.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(repo_root / inputs["npmrc"], npmrc)
    empty = state_root / "tools" / "browser-runtime" / "empty-global-npmrc"
    empty.write_text("", encoding="utf-8")
    return project


def run_npm(lock: dict[str, Any], state_root: Path, *, offline: bool) -> None:
    """Run the locked npm argv. Missing locked npm fails closed."""
    argv = npm_argv(lock, state_root, offline=offline)
    executable = Path(argv[0])
    if not executable.is_file():
        raise FileNotFoundError(argv[0])
    result = run_fenced(argv, cwd=str(state_root), timeout_s=120.0)
    if result.returncode != 0:
        raise RuntimeError("locked npm failed")


def load_and_materialize(
    tool_lock: Path, repo_root: Path, state_root: Path
) -> dict[str, Any]:
    """Load the tool lock and materialize the browser project."""
    lock = load_tool_lock(tool_lock)
    materialize_browser_project(lock, repo_root, state_root)
    return lock
