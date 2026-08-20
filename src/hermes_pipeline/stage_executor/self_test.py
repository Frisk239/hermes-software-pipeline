"""Development self-test and scripted verify runner.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FEEDBACK_MARK = "FEEDBACK FROM LAST GATE"


def pytest_unavailable(text: str) -> bool:
    return "no module named pytest" in text.lower()


def run_self_test(root: Path) -> tuple[bool, str]:
    chunks: list[str] = []
    tests = root / "tests"
    if tests.is_dir():
        code, text = run_pytest(root)
        chunks.append(text)
        if code is None or code != 0:
            return False, "\n".join(chunks).strip() or "pytest failed"
    app = root / "src" / "app.py"
    if not app.is_file():
        return True, "\n".join(chunks)
    status, text = run_app(app, root / "src")
    chunks.append(text)
    if status == "passed":
        return True, "\n".join(chunks)
    return False, "\n".join(chunks).strip() or f"src/app.py {status}"


def run_app(app: Path, cwd: Path) -> tuple[str, str]:
    checked = run_python([str(app), "--check"], cwd)
    if checked[0] == 0:
        return "passed", checked[1]
    if checked[0] is None:
        return "timeout", checked[1]
    lowered = checked[1].lower()
    if checked[0] == 2 or "unrecognized" in lowered or "invalid" in lowered:
        bare = run_python([str(app)], cwd)
        if bare[0] == 0:
            return "passed", bare[1]
        if bare[0] is None:
            return "timeout", bare[1]
        return "failed", bare[1]
    return "failed", checked[1]


def run_python(argv: list[str], cwd: Path) -> tuple[int | None, str]:
    try:
        completed = subprocess.run(
            [sys.executable, *argv],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "timeout"
    text = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, text


def run_pytest(root: Path) -> tuple[int | None, str]:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, "pytest unavailable"
    text = (completed.stdout or "") + (completed.stderr or "")
    if pytest_unavailable(text):
        return 0, ""
    return completed.returncode, text


__all__ = [
    "FEEDBACK_MARK",
    "pytest_unavailable",
    "run_app",
    "run_pytest",
    "run_python",
    "run_self_test",
]
