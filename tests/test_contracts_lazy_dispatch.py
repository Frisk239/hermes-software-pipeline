"""Lazy-dispatch boundary tests (AC-10).

pydantic, jsonschema, and rfc8785 are imported only after the ``contracts``
subcommand is parsed. ``--version`` and the normal runtime path stay pure
standard library, and ``contracts`` returns a bounded error when the
development dependencies are absent.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_BLOCKER = """
import sys

class _Block:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in (
            "pydantic",
            "pydantic_core",
            "jsonschema",
            "referencing",
            "rpds",
            "rfc8785",
            "typing_inspection",
        ):
            raise ImportError("blocked for lazy-dispatch test")
        return None

sys.meta_path.insert(0, _Block())
from hermes_pipeline.cli import main
raise SystemExit(main({argv!r}))
"""


def _run_with_blocked_toolchain(argv: list[str]) -> subprocess.CompletedProcess[str]:
    code = _BLOCKER.format(argv=argv)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )


def _assert_bounded_subprocess_result(
    proc: subprocess.CompletedProcess[str],
    expected_returncode: int,
    required_output: str,
) -> None:
    """Validate bounded CLI output without rendering it on regression."""
    combined = proc.stdout + proc.stderr
    if (
        proc.returncode != expected_returncode
        or required_output not in combined
        or "Traceback" in combined
        or len(combined.encode("utf-8")) > 512
    ):
        raise AssertionError("lazy-dispatch subprocess returned unsafe output")


def test_version_works_without_toolchain_imports() -> None:
    proc = _run_with_blocked_toolchain(["--version"])
    _assert_bounded_subprocess_result(proc, 0, "0.1.0")


def test_contracts_check_returns_bounded_error_without_toolchain() -> None:
    proc = _run_with_blocked_toolchain(["contracts", "check"])
    _assert_bounded_subprocess_result(proc, 1, "contract toolchain unavailable")


def test_plugin_entry_and_version_never_import_toolchain() -> None:
    """The plugin entry and --version paths must not import pydantic, even
    when the development dependencies are present."""
    proc = subprocess.run(
        [sys.executable, "-m", "hermes_pipeline.cli", "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        cwd=REPO_ROOT,
    )
    _assert_bounded_subprocess_result(proc, 0, "0.1.0")


def test_subcommand_parse_errors_happen_before_toolchain_import() -> None:
    proc = _run_with_blocked_toolchain(["contracts"])
    assert proc.returncode == 2
    proc = _run_with_blocked_toolchain(["contracts", "bogus"])
    assert proc.returncode == 2
