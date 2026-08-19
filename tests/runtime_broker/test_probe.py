from __future__ import annotations

from pathlib import Path

from hermes_pipeline.runtime_broker.probe import resolve_runtime_executable


def test_env_override_wins_when_file_exists(tmp_path: Path) -> None:
    exe = tmp_path / "custom-opencode"
    exe.write_text("x", encoding="utf-8")
    path = resolve_runtime_executable(
        "opencode",
        environ={"HERMES_OPENCODE_PATH": str(exe)},
        which=lambda _name: "C:/wrong/opencode",
    )
    assert path == str(exe)


def test_env_override_hard_miss_does_not_fall_back(tmp_path: Path) -> None:
    missing = tmp_path / "gone"
    path = resolve_runtime_executable(
        "opencode",
        environ={"HERMES_OPENCODE_PATH": str(missing)},
        which=lambda _name: str(tmp_path / "on-path"),
    )
    assert path == ""


def test_cursor_uses_cursor_agent_name(tmp_path: Path) -> None:
    exe = tmp_path / "cursor-agent"
    exe.write_text("x", encoding="utf-8")
    path = resolve_runtime_executable(
        "cursor",
        environ={},
        which=lambda name: str(exe) if name == "cursor-agent" else None,
    )
    assert path == str(exe)


def test_npm_cmd_shim_unwraps_to_exe(tmp_path: Path) -> None:
    exe = tmp_path / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("x", encoding="utf-8")
    shim = tmp_path / "opencode.CMD"
    shim.write_text("x", encoding="utf-8")
    path = resolve_runtime_executable(
        "opencode",
        environ={},
        which=lambda name: str(shim) if name == "opencode" else None,
    )
    assert path == str(exe)


def test_which_used_when_no_override(tmp_path: Path) -> None:
    exe = tmp_path / "opencode"
    exe.write_text("x", encoding="utf-8")
    path = resolve_runtime_executable(
        "opencode",
        environ={},
        which=lambda name: str(exe) if name == "opencode" else None,
    )
    assert path == str(exe)
