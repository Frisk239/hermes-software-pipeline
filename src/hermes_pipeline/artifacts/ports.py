"""Public Artifacts Interface adopted by Slice 00-07.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ArtifactPutRequest:
    payload: bytes


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    digest: str


@dataclass(frozen=True)
class ArtifactVerification:
    ok: bool


@runtime_checkable
class ArtifactsPort(Protocol):
    def put(self, request: ArtifactPutRequest) -> ArtifactRecord:
        """Store one payload and return its content address."""
        ...

    def open(self, artifact_id: str) -> bytes:
        """Return the stored payload."""
        ...

    def verify(self, artifact_id: str) -> ArtifactVerification:
        """Verify a stored artifact exists at its digest."""
        ...


__all__ = [
    "ArtifactPutRequest",
    "ArtifactRecord",
    "ArtifactVerification",
    "ArtifactsPort",
]
