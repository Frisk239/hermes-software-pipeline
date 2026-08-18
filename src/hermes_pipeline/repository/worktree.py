"""Managed worktree and Candidate SHA without mutating user Git."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

SECRET_CANARY = "SECRET_CANARY"


@dataclass(frozen=True)
class CandidateRecord:
    sha: str
    relative_path: str


class ManagedWorktree:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def write(self, relative_path: str, payload: bytes) -> Path:
        if SECRET_CANARY.encode("utf-8") in payload:
            raise ValueError("secret canary")
        target = (self._root / relative_path).resolve()
        if not str(target).startswith(str(self._root)):
            raise ValueError("path escape")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return target

    def candidate_sha(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(self._root.rglob("*")):
            if path.is_file():
                rel = path.relative_to(self._root).as_posix()
                digest.update(rel.encode("utf-8"))
                digest.update(path.read_bytes())
        return digest.hexdigest()


__all__ = ["SECRET_CANARY", "CandidateRecord", "ManagedWorktree"]
