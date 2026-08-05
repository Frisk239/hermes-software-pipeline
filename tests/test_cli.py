"""CLI success, usage-error, and unknown-command exits (slice-00-02).

Exit codes are stable: 0 success, 1 check failure, 2 usage error. Unknown
commands and malformed arguments must fail without touching any state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_pipeline.cli._main import main


def test_missing_command_is_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 2
    assert "usage:" in capsys.readouterr().err


def test_unknown_command_is_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["frobnicate"]) == 2
    assert "unknown command" in capsys.readouterr().err


def test_version_rejects_extra_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--version", "extra"]) == 2


def test_contracts_requires_check_subcommand(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["contracts"]) == 2
    assert main(["contracts", "wat"]) == 2


def test_architecture_requires_check_subcommand(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["architecture"]) == 2


def test_architecture_check_rejects_unknown_flags(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["architecture", "check", "--bogus"]) == 2
    assert main(["architecture", "check", "--root"]) == 2
    assert main(["architecture", "check", "--root", "a", "b"]) == 2


def test_contracts_check_delegates_to_bootstrap_checker(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["contracts", "check"]) == 0
    assert "check_schemas: OK" in capsys.readouterr().out


def test_architecture_check_accepts_current_skeleton(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["architecture", "check"]) == 0
    assert "architecture check: OK" in capsys.readouterr().out


def test_architecture_check_rejects_violating_tree(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    root = tmp_path / "badpkg"
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    (root / "controller").mkdir()
    (root / "controller" / "__init__.py").write_text(
        "import subprocess\n", encoding="utf-8"
    )
    assert main(["architecture", "check", "--root", str(root)]) == 1
    assert "ARCH-06" in capsys.readouterr().out
