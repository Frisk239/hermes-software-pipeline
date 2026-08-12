"""Portable process-boundary checks for the Slice 00-05 Hermes probes.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tests.spike.probe import _hermes


def test_probe_runners_force_utf8_decoding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Probe output must not depend on the Windows console code page."""
    python = tmp_path / "venv" / "Scripts" / "python.exe"
    executable = python.parent / ("hermes.exe" if os.name == "nt" else "hermes")
    executable.parent.mkdir(parents=True)
    python.write_bytes(b"")
    executable.write_bytes(b"")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    observed: list[dict[str, Any]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed.append(kwargs)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(_hermes.subprocess, "run", fake_run)
    _hermes.run_hermes_cli(python, checkout, home, ["plugins", "list"])
    _hermes.run_probe_script(python, checkout, home, "print('probe')")

    assert len(observed) == 2
    for kwargs in observed:
        assert kwargs["text"] is True
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
