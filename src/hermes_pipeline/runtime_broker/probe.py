"""Resolve agent CLI paths. Env override is a hard miss if the file is gone."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path

Which = Callable[[str], str | None]

_CATALOG: dict[str, tuple[str, tuple[str, ...]]] = {
    "opencode": ("HERMES_OPENCODE_PATH", ("opencode",)),
    "codex": ("HERMES_CODEX_PATH", ("codex",)),
    "claude": ("HERMES_CLAUDE_PATH", ("claude",)),
    "cursor": ("HERMES_CURSOR_PATH", ("cursor-agent", "cursor")),
    "kiro": ("HERMES_KIRO_PATH", ("kiro-cli", "kiro")),
    "grok": ("HERMES_GROK_PATH", ("grok",)),
}


def catalog_families() -> tuple[str, ...]:
    return tuple(_CATALOG)


def resolve_runtime_executable(
    family: str,
    *,
    environ: Mapping[str, str] | None = None,
    which: Which | None = None,
) -> str:
    spec = _CATALOG.get(family)
    if spec is None:
        return ""
    lookup = which or shutil.which
    env = os.environ if environ is None else environ
    key, names = spec
    override = env.get(key, "")
    if override:
        return override if Path(override).is_file() else ""
    for name in names:
        for candidate in (name, f"{name}.exe"):
            found = lookup(candidate)
            if found and Path(found).is_file():
                return _prefer_real_executable(found, family)
    return ""


def _prefer_real_executable(path: str, family: str) -> str:
    current = Path(path)
    if family != "opencode" or current.suffix.lower() not in {".cmd", ".ps1"}:
        return path
    sibling = current.parent / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
    if sibling.is_file():
        return str(sibling)
    return path


def detect_runtime_executables(
    *,
    environ: Mapping[str, str] | None = None,
    which: Which | None = None,
) -> dict[str, str]:
    found: dict[str, str] = {}
    for family in _CATALOG:
        path = resolve_runtime_executable(family, environ=environ, which=which)
        if path:
            found[family] = path
    return found


__all__ = [
    "catalog_families",
    "detect_runtime_executables",
    "resolve_runtime_executable",
]
