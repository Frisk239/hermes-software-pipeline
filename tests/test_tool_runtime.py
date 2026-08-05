"""The frozen Pyright toolchain must use its bundled Node runtime."""

from __future__ import annotations

import os
import subprocess
import sys


def test_pyright_resolves_bundled_node() -> None:
    """Pyright must run with its lockfile-provided Node, never global Node."""
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYRIGHT_PYTHON_DEBUG": "1",
        "PYRIGHT_PYTHON_GLOBAL_NODE": "0",
        "PYRIGHT_PYTHON_NODEJS_WHEEL": "1",
    }
    result = subprocess.run(
        [sys.executable, "-m", "pyright", "--version"],
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    assert "Using nodejs_wheel package" in result.stderr
