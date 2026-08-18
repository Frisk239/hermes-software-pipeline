"""Host runtime probe (slice 05-17).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

from pathlib import Path

from hermes_shim._runtimes import resolve_runtime_executable, write_runtime_pins


def test_write_runtime_pins(tmp_path: Path) -> None:
    write_runtime_pins(tmp_path, {"opencode": "C:/tools/opencode"})
    text = (tmp_path / "descriptor" / "runtimes.json").read_text(encoding="utf-8")
    assert "opencode" in text


def test_override_hard_miss(tmp_path: Path) -> None:
    path = resolve_runtime_executable(
        "codex",
        environ={"HERMES_CODEX_PATH": str(tmp_path / "missing")},
        which=lambda _name: "C:/other/codex",
    )
    assert path == ""
