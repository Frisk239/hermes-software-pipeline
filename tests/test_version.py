"""Installed metadata and CLI version consistency (AC-04).

The package metadata in ``pyproject.toml`` is the sole version source;
``--version``, ``hermes_pipeline.__version__``, and installed distribution
metadata must all report ``0.1.0``.
"""

from __future__ import annotations

import subprocess
import sys
from importlib.metadata import version

import pytest

import hermes_pipeline
from hermes_pipeline.cli._main import main


def test_installed_distribution_version_is_010() -> None:
    assert version("hermes-pipeline") == "0.1.0"


def test_package_version_reads_installed_metadata() -> None:
    assert hermes_pipeline.__version__ == "0.1.0"


def test_cli_version_matches_installed_metadata(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["--version"])
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "0.1.0"


def test_module_entry_version_matches_installed_metadata() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "hermes_pipeline.cli", "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "0.1.0"
