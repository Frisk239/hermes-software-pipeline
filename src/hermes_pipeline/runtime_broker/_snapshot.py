"""Read-only snapshot tree digest (no Git).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def snapshot_tree_digest(root: Path) -> str:
    """sha256 of sorted relative paths and file bytes. Not a Git tree."""
    hasher = hashlib.sha256()
    if not root.is_dir():
        raise ValueError("snapshot is not a directory")
    files = [path for path in root.rglob("*") if path.is_file()]
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return "sha256:" + hasher.hexdigest()
