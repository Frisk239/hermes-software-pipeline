"""Hostile-input rejection used by 00-06 adapters.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE
"""

from __future__ import annotations

import os
from pathlib import Path

DOS_DEVICES = frozenset({"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"})


class PolicyError(ValueError):
    """A hostile path, Git, or config input was rejected."""


def assert_path_inside(root: Path, candidate: str) -> Path:
    """Reject absolute, dot-dot, symlink/junction, and 8.3 escapes."""
    if not candidate or candidate in DOS_DEVICES:
        raise PolicyError("forbidden path")
    if candidate.startswith(("/", "\\")):
        raise PolicyError("absolute path rejected")
    if len(candidate) >= 2 and candidate[1] == ":":
        raise PolicyError("absolute path rejected")
    raw = Path(candidate)
    if raw.is_absolute() or raw.drive:
        raise PolicyError("absolute path rejected")
    if any(part == ".." for part in raw.parts):
        raise PolicyError("dot-dot rejected")
    if "~" in raw.name:
        raise PolicyError("8.3 short name rejected")
    target = root / raw
    if target.exists() and (target.is_symlink() or _is_junction(target)):
        raise PolicyError("symlink or junction rejected")
    resolved = target.resolve()
    root_resolved = root.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PolicyError("path escapes root") from exc
    return resolved


def _is_junction(path: Path) -> bool:
    if os.name != "nt":
        return False
    try:
        stat_result = path.lstat()
    except OSError:
        return False
    return bool(getattr(stat_result, "st_file_attributes", 0) & 0x400)


def assert_no_git_metadata(snapshot: Path) -> None:
    """A .git file or directory is never isolation evidence."""
    if (snapshot / ".git").exists():
        raise PolicyError("snapshot contains .git")


def assert_digest_unchanged(path: Path, expected: str) -> None:
    """Require a file's raw sha256 to remain the recorded digest."""
    from hermes_pipeline.runtime_broker._digest import file_digest

    if not path.exists():
        raise PolicyError("candidate gitdir missing")
    if file_digest(path.read_bytes()) != expected:
        raise PolicyError("candidate gitdir digest changed")


def assert_codex_config_not_trusted(config_text: str) -> None:
    """Reject a .codex/config.toml that disables the trust gate."""
    lowered = config_text.lower()
    if "trusted = true" in lowered or 'approval_policy = "never"' in lowered:
        raise PolicyError("codex trust gate disabled")


def git_child_environment(state_root: Path) -> dict[str, str]:
    """Force child Git config under state-root; no hooksPath/LFS smudge."""
    empty = state_root / "child-home" / "gitconfig"
    empty.parent.mkdir(parents=True, exist_ok=True)
    empty.write_text("[user]\n\tname = hermes\n", encoding="utf-8")
    return {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(empty),
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_LFS_SKIP_SMUDGE": "1",
    }
