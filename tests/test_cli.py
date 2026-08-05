"""CLI success, usage-error, and unknown-command exits (slice-00-02).

Exit codes are stable: 0 success, 1 check failure, 2 usage error. Unknown
commands and malformed arguments must fail without touching any state.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from hermes_pipeline.cli._bootstrap import find_repository_root
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


def test_contracts_check_requires_a_source_checkout(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hermes_pipeline.cli._contracts.repo_root", lambda: None)
    assert main(["contracts", "check"]) == 1
    assert "requires a Hermes Pipeline source checkout" in capsys.readouterr().err


def test_contracts_check_restores_script_import_state(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_path = list(sys.path)
    schemas_before = ModuleType("check_schemas_before")
    common_before = ModuleType("_check_common_before")
    monkeypatch.setitem(sys.modules, "check_schemas", schemas_before)
    monkeypatch.setitem(sys.modules, "_check_common", common_before)

    assert main(["contracts", "check"]) == 0
    assert "check_schemas: OK" in capsys.readouterr().out
    assert sys.path == original_path
    assert sys.modules["check_schemas"] is schemas_before
    assert sys.modules["_check_common"] is common_before


def test_architecture_check_accepts_current_skeleton(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["architecture", "check"]) == 0
    assert "architecture check: OK" in capsys.readouterr().out


def test_architecture_check_requires_a_source_checkout_without_root(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hermes_pipeline.cli._main.repo_root", lambda: None)
    assert main(["architecture", "check"]) == 1
    assert "requires a Hermes Pipeline source checkout" in capsys.readouterr().err


def test_architecture_check_with_explicit_root_is_checkout_independent(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "legalpkg"
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setattr("hermes_pipeline.cli._main.repo_root", lambda: None)

    assert main(["architecture", "check", "--root", str(root)]) == 0
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


def test_repository_root_discovery_requires_the_checkout_shape(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    bootstrap = checkout / "src" / "hermes_pipeline" / "cli" / "_bootstrap.py"
    bootstrap.parent.mkdir(parents=True)
    bootstrap.write_text("", encoding="utf-8")
    schema_checker = checkout / "scripts" / "check_schemas.py"
    schema_checker.parent.mkdir()
    schema_checker.write_text("", encoding="utf-8")
    assert find_repository_root(bootstrap) == checkout

    standalone = (
        tmp_path / "site-packages" / "hermes_pipeline" / "cli" / "_bootstrap.py"
    )
    standalone.parent.mkdir(parents=True)
    standalone.write_text("", encoding="utf-8")
    assert find_repository_root(standalone) is None
