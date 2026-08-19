"""Named artifact harvest for bound planner and executor stages.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from pathlib import Path

from hermes_pipeline.repository.worktree import SECRET_CANARY

PRD_NAMES = ("PRD.md", "prd.md")
DESIGN_NAMES = ("ARCHITECTURE.md", "architecture.md", "design.md")
TESTPLAN_NAMES = ("TESTPLAN.md", "testplan.md")
_PLANNING = frozenset(
    name.lower() for name in (*PRD_NAMES, *DESIGN_NAMES, *TESTPLAN_NAMES)
)


def named_file_bytes(folder: Path | None, names: tuple[str, ...]) -> bytes | None:
    if folder is None or not folder.is_dir():
        return None
    wanted = {name.lower() for name in names}
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.name.lower() in wanted:
            body = path.read_bytes()
            if SECRET_CANARY.encode("utf-8") in body:
                return None
            return body
    return None


def pick_implementation(files: list[Path], root: Path) -> Path | None:
    src: list[Path] = []
    for path in files:
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if path.name.lower() in _PLANNING:
            continue
        if rel == "src/app.py":
            return path
        if rel.startswith("src/"):
            src.append(path)
    if src:
        return sorted(src)[0]
    return None


__all__ = [
    "DESIGN_NAMES",
    "PRD_NAMES",
    "TESTPLAN_NAMES",
    "named_file_bytes",
    "pick_implementation",
]
