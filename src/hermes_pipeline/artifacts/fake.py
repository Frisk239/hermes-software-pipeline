"""In-memory artifact Adapter keyed by SHA-256 hex.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

import hashlib

from hermes_pipeline.artifacts.ports import (
    ArtifactPutRequest,
    ArtifactRecord,
    ArtifactVerification,
)


class FakeArtifacts:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def put(self, request: ArtifactPutRequest) -> ArtifactRecord:
        digest = hashlib.sha256(request.payload).hexdigest()
        self._store[digest] = request.payload
        return ArtifactRecord(artifact_id=digest, digest=digest)

    def open(self, artifact_id: str) -> bytes:
        return self._store[artifact_id]

    def verify(self, artifact_id: str) -> ArtifactVerification:
        return ArtifactVerification(ok=artifact_id in self._store)


__all__ = ["FakeArtifacts"]
