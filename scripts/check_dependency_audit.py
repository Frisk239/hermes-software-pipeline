#!/usr/bin/env python3
"""Fail when the root project declares a runtime dependency."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

sys.dont_write_bytecode = True

EXIT_OK = 0
EXIT_FAIL = 1
MAX_LINES = 20


def audit_root(root: Path) -> list[str]:
    findings: list[str] = []
    pyproject = root / "pyproject.toml"
    lock_path = root / "uv.lock"
    if not pyproject.is_file():
        findings.append("missing pyproject.toml")
        return findings
    if not lock_path.is_file():
        findings.append("missing uv.lock")
    with pyproject.open("rb") as handle:
        document = tomllib.load(handle)
    project = document.get("project")
    dependencies = []
    if isinstance(project, dict):
        raw = project.get("dependencies", [])
        if isinstance(raw, list):
            dependencies = [item for item in raw if isinstance(item, str)]
        else:
            findings.append("project.dependencies is not a list")
    else:
        findings.append("missing [project] table")
    if dependencies:
        findings.append(
            "runtime dependency present: " + ", ".join(dependencies[:MAX_LINES])
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)
    root = (args.root or Path(__file__).resolve().parent.parent).resolve()
    findings = audit_root(root)
    if not findings:
        print("check_dependency_audit: OK")
        return EXIT_OK
    print("check_dependency_audit: FAIL")
    for line in findings[:MAX_LINES]:
        print(line)
    return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
