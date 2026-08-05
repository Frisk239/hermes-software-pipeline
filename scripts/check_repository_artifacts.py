#!/usr/bin/env python3
"""Fail when verification leaves cache or bytecode artifacts in the source tree."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
PRUNED_ROOTS = frozenset({".git", ".venv", "reference"})
FORBIDDEN_DIRECTORIES = frozenset(
    {"__pycache__", ".pytest_cache", ".ruff_cache", ".hypothesis", ".mypy_cache"}
)
FORBIDDEN_SUFFIXES = frozenset({".pyc", ".pyo"})
MAX_LINES = 100


def find_artifacts(root: Path = REPOSITORY_ROOT) -> list[str]:
    """Return stable root-relative paths for forbidden generated artifacts."""
    findings: list[str] = []
    fixture_root = root / "scripts" / "fixtures"
    for dirpath, dirnames, filenames in os.walk(
        root, topdown=True, followlinks=False
    ):
        current = Path(dirpath)
        if current == fixture_root or current.is_relative_to(fixture_root):
            dirnames[:] = []
            continue
        kept: list[str] = []
        for name in sorted(dirnames):
            path = current / name
            if name in PRUNED_ROOTS:
                continue
            if name in FORBIDDEN_DIRECTORIES:
                findings.append(path.relative_to(root).as_posix() + "/")
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            path = current / name
            if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                findings.append(path.relative_to(root).as_posix())
    return sorted(set(findings))


def main() -> int:
    findings = find_artifacts()
    if not findings:
        print("check_repository_artifacts: OK")
        return 0
    print("check_repository_artifacts: FAIL")
    for path in findings[:MAX_LINES]:
        print(path)
    if len(findings) > MAX_LINES:
        print(f"... {len(findings) - MAX_LINES} further artifact(s) omitted")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
