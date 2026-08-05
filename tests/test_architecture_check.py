"""Standard-library AST architecture checker tests (AC-05).

The checker must accept the legal package skeleton and deterministically
reject forbidden absolute, relative, dynamic, adapter-to-core, domain
escape, controller-boundary, adapter-in-core, and Shim imports with stable
file/line/rule diagnostics.
"""

from __future__ import annotations

from pathlib import Path

from hermes_pipeline.cli._architecture_check import (
    Diagnostic,
    check_package_tree,
    render_diagnostics,
)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _package(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    _write(root, "__init__.py", "")
    return root


def _rules(root: Path) -> set[str]:
    return {diagnostic.rule for diagnostic in check_package_tree(root)}


def test_legal_package_tree_has_no_diagnostics(tmp_path: Path) -> None:
    root = _package(tmp_path, "legalpkg")
    _write(root, "domain/__init__.py", "")
    _write(root, "domain/value.py", "import datetime\n")
    _write(root, "contracts/__init__.py", "")
    _write(root, "controller/__init__.py", f"from {root.name}.domain.value import V\n")
    assert check_package_tree(root) == []


def test_forbidden_absolute_import(tmp_path: Path) -> None:
    root = _package(tmp_path, "abspkg")
    _write(root, "domain/__init__.py", "")
    _write(root, "mod.py", "import domain\n")
    assert "ARCH-01" in _rules(root)


def test_forbidden_relative_import(tmp_path: Path) -> None:
    root = _package(tmp_path, "relpkg")
    _write(root, "domain/__init__.py", "")
    _write(root, "sub/__init__.py", "")
    _write(root, "sub/mod.py", "from ..domain import value\n")
    assert "ARCH-02" in _rules(root)


def test_forbidden_dynamic_import_direct(tmp_path: Path) -> None:
    root = _package(tmp_path, "dynpkg")
    _write(root, "mod.py", "import importlib\nimportlib.import_module('x')\n")
    assert "ARCH-03" in _rules(root)


def test_forbidden_dynamic_import_alias(tmp_path: Path) -> None:
    root = _package(tmp_path, "dynpkg2")
    _write(root, "mod.py", "import importlib as il\nil.import_module('x')\n")
    assert "ARCH-03" in _rules(root)


def test_forbidden_dynamic_import_from(tmp_path: Path) -> None:
    root = _package(tmp_path, "dynpkg3")
    _write(root, "mod.py", "from importlib import import_module\nimport_module('x')\n")
    assert "ARCH-03" in _rules(root)


def test_forbidden_dynamic_import_builtin(tmp_path: Path) -> None:
    root = _package(tmp_path, "dynpkg4")
    _write(root, "mod.py", "__import__('x')\n")
    assert "ARCH-03" in _rules(root)


def test_adapter_may_import_inward_facing_interface(tmp_path: Path) -> None:
    root = _package(tmp_path, "adapterpkg")
    _write(root, "adapters/__init__.py", "")
    _write(root, "contracts/__init__.py", "")
    _write(root, "adapters/store.py", f"from {root.name}.contracts import Record\n")
    assert check_package_tree(root) == []


def test_core_must_not_import_adapter(tmp_path: Path) -> None:
    root = _package(tmp_path, "corepkg")
    _write(root, "contracts/__init__.py", "")
    _write(root, "adapters/__init__.py", "")
    _write(root, "contracts/model.py", f"from {root.name}.adapters import A\n")
    assert "ARCH-04" in _rules(root)


def test_domain_external_dependency_rejected(tmp_path: Path) -> None:
    root = _package(tmp_path, "domainpkg")
    _write(root, "domain/__init__.py", "")
    _write(root, "domain/rule.py", "import requests\n")
    assert "ARCH-05" in _rules(root)


def test_domain_stdlib_and_contracts_allowed(tmp_path: Path) -> None:
    root = _package(tmp_path, "domainok")
    _write(root, "domain/__init__.py", "")
    _write(root, "contracts/__init__.py", "")
    _write(
        root,
        "domain/rule.py",
        f"import datetime\nfrom {root.name}.contracts import T\n",
    )
    assert check_package_tree(root) == []


def test_controller_forbidden_subprocess(tmp_path: Path) -> None:
    root = _package(tmp_path, "ctrlpkg")
    _write(root, "controller/__init__.py", "")
    _write(root, "controller/app.py", "import subprocess\n")
    assert "ARCH-06" in _rules(root)


def test_controller_forbidden_framework(tmp_path: Path) -> None:
    root = _package(tmp_path, "ctrlpkg2")
    _write(root, "controller/__init__.py", "")
    _write(root, "controller/app.py", "import fastapi\n")
    assert "ARCH-06" in _rules(root)


def test_controller_forbidden_provider_sdk(tmp_path: Path) -> None:
    root = _package(tmp_path, "ctrlprovider")
    _write(root, "controller/__init__.py", "")
    _write(root, "controller/app.py", "import github\n")
    assert "ARCH-06" in _rules(root)


def test_controller_forbidden_concrete_filesystem(tmp_path: Path) -> None:
    root = _package(tmp_path, "ctrlfilesystem")
    _write(root, "controller/__init__.py", "")
    _write(root, "controller/app.py", "from pathlib import Path\n")
    assert "ARCH-06" in _rules(root)


def test_controller_forbidden_filesystem_adapter(tmp_path: Path) -> None:
    root = _package(tmp_path, "ctrlpkg3")
    _write(root, "controller/__init__.py", "")
    _write(root, "adapters/__init__.py", "")
    _write(root, "controller/app.py", f"from {root.name}.adapters.fs import read\n")
    assert "ARCH-06" in _rules(root)


def test_hermes_shim_import_forbidden(tmp_path: Path) -> None:
    root = _package(tmp_path, "shimpkg")
    _write(root, "mod.py", "import hermes_shim\n")
    assert "ARCH-08" in _rules(root)


def test_syntax_error_reported(tmp_path: Path) -> None:
    root = _package(tmp_path, "badpkg")
    _write(root, "mod.py", "def broken(:\n")
    assert "ARCH-99" in _rules(root)


def test_missing_package_root_reported(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    diagnostics = check_package_tree(missing)
    assert len(diagnostics) == 1
    assert diagnostics[0].rule == "ARCH-99"


def test_render_is_sorted_and_identifies_rule(tmp_path: Path) -> None:
    diagnostics = [
        Diagnostic("b.py", 1, "ARCH-02", "msg"),
        Diagnostic("a.py", 2, "ARCH-01", "msg"),
        Diagnostic("a.py", 1, "ARCH-01", "msg"),
    ]
    lines = render_diagnostics(diagnostics).splitlines()
    assert lines[0].startswith("a.py:1: ARCH-01")
    assert lines[1].startswith("a.py:2: ARCH-01")
    assert lines[2].startswith("b.py:1: ARCH-02")


def test_render_sanitizes_control_characters() -> None:
    diagnostics = [Diagnostic("a.py", 1, "ARCH-01", "bad\x00newline\ninjection")]
    text = render_diagnostics(diagnostics)
    assert "\x00" not in text
    assert "\\u0000" in text
    assert "\\u000a" in text


def test_output_is_bounded(tmp_path: Path) -> None:
    root = _package(tmp_path, "noisypkg")
    _write(root, "domain/__init__.py", "")
    for index in range(150):
        _write(root, f"mod{index}.py", "import domain\n")
    text = render_diagnostics(check_package_tree(root))
    assert len(text.encode("utf-8")) <= 8192
    assert "further diagnostic(s) omitted" in text or "output truncated" in text
