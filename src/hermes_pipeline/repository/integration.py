"""Integration Candidate identity and verification sandbox."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IntegrationCandidate:
    candidate_sha: str
    integration_base_sha: str
    sha: str


def build_integration_candidate(
    candidate_sha: str, integration_base_sha: str
) -> IntegrationCandidate:
    digest = hashlib.sha256(
        f"{candidate_sha}:{integration_base_sha}".encode()
    ).hexdigest()
    return IntegrationCandidate(
        candidate_sha=candidate_sha,
        integration_base_sha=integration_base_sha,
        sha=digest,
    )


class VerificationSandbox:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    @property
    def root(self) -> Path:
        return self._root

    def create(self, integration_sha: str) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / "INTEGRATION_SHA").write_text(integration_sha, encoding="utf-8")
        return self._root

    def stage_tree(self, source: Path) -> None:
        for name in ("src", "tests"):
            src = source / name
            if src.is_dir():
                shutil.copytree(src, self._root / name, dirs_exist_ok=True)

    def cleanup(self) -> None:
        if self._root.exists():
            shutil.rmtree(self._root, ignore_errors=True)

    def write(self, relative: str, text: str) -> None:
        target = (self._root / relative).resolve()
        try:
            target.relative_to(self._root.resolve())
        except ValueError:
            raise ValueError("path escape") from None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def exists(self) -> bool:
        return self._root.exists()


__all__ = [
    "IntegrationCandidate",
    "VerificationSandbox",
    "build_integration_candidate",
]
