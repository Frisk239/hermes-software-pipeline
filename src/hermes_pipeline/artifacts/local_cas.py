from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from hermes_pipeline.artifacts.ports import (
    ArtifactPutRequest,
    ArtifactRecord,
    ArtifactsPort,
    ArtifactVerification,
)
from hermes_pipeline.contracts.definitions import (
    FixedV1Integer,
    Sha256Ref,
    UtcTimestampRef,
)
from hermes_pipeline.contracts.jcs import content_hash
from hermes_pipeline.contracts.runtime import (
    ArtifactManifest,
    ArtifactSourceIdentity,
    Producer,
    Provenance,
)

_ARTIFACT_ID = re.compile(r"^art_[A-Za-z0-9_-]+$")
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SCHEMA_ID = "https://schemas.hermes-pipeline.dev/runtime/artifact-manifest/v1"
_PLACEHOLDER_DIGEST = "sha256:" + "0" * 64
_FIXTURE_PRODUCER = Producer(
    stage_attempt_id="att_fixture",
    execution_run_id="run_fixture",
    lease_generation=1,
)
_FIXTURE_PROVENANCE = Provenance(
    workflow_version="0.1.0",
    runtime_version="0.1.0",
    capability_profile_hash=Sha256Ref("sha256:" + "c" * 64),
)


class ArtifactNotFound(LookupError):
    def __init__(self, artifact_id: str) -> None:
        super().__init__(f"unknown artifact: {artifact_id}")
        self.artifact_id = artifact_id


def assemble_evidence(
    artifacts: ArtifactsPort, artifact_ids: Sequence[str]
) -> ArtifactVerification:
    return ArtifactVerification(
        ok=all(artifacts.verify(artifact_id).ok for artifact_id in artifact_ids)
    )


class LocalCasArtifacts:
    def __init__(self, root: Path, *, created_at: str | None = None) -> None:
        self._root = root
        self._created_at = created_at

    def put(self, request: ArtifactPutRequest) -> ArtifactRecord:
        payload = request.payload
        digest = hashlib.sha256(payload).hexdigest()
        artifact_id = f"art_{digest}"
        blob_path = self._blob_path(digest)
        manifest_path = self._manifest_path(artifact_id)
        if not _blob_matches(blob_path, digest):
            _atomic_write(blob_path, payload)
        if not manifest_path.is_file():
            _atomic_write(
                manifest_path,
                _manifest_bytes(
                    artifact_id=artifact_id,
                    digest=digest,
                    byte_size=len(payload),
                    created_at=self._created_at or _utc_now(),
                ),
            )
        return ArtifactRecord(artifact_id=artifact_id, digest=digest)

    def open(self, artifact_id: str) -> bytes:
        blob_path = self._resolve_blob(artifact_id)
        if blob_path is None or not blob_path.is_file():
            raise ArtifactNotFound(artifact_id)
        return blob_path.read_bytes()

    def verify(self, artifact_id: str) -> ArtifactVerification:
        blob_path = self._resolve_blob(artifact_id)
        if blob_path is None:
            return ArtifactVerification(ok=False)
        digest = blob_path.name
        return ArtifactVerification(ok=_blob_matches(blob_path, digest))

    def _resolve_blob(self, artifact_id: str) -> Path | None:
        if not _ARTIFACT_ID.fullmatch(artifact_id):
            return None
        manifest_path = self._manifest_path(artifact_id)
        if not manifest_path.is_file():
            return None
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        content_digest = document.get("content_digest")
        if not isinstance(content_digest, str) or not content_digest.startswith(
            "sha256:"
        ):
            return None
        hex_digest = content_digest.removeprefix("sha256:")
        if not _HEX_DIGEST.fullmatch(hex_digest):
            return None
        return self._blob_path(hex_digest)

    def _blob_path(self, digest: str) -> Path:
        return self._root / "blobs" / digest

    def _manifest_path(self, artifact_id: str) -> Path:
        return self._root / "manifests" / f"{artifact_id}.json"


def _utc_now() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _blob_matches(path: Path, digest: str) -> bool:
    if not path.is_file():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == digest


def _manifest_bytes(
    *, artifact_id: str, digest: str, byte_size: int, created_at: str
) -> bytes:
    manifest = ArtifactManifest(
        schema_id=_SCHEMA_ID,
        schema_version=FixedV1Integer(1),
        artifact_id=artifact_id,
        logical_role="stage-output",
        media_type="application/octet-stream",
        byte_size=byte_size,
        content_digest=Sha256Ref(f"sha256:{digest}"),
        document_schema_id="",
        document_schema_version=1,
        producer=_FIXTURE_PRODUCER,
        source_identity=ArtifactSourceIdentity(),
        provenance=_FIXTURE_PROVENANCE,
        sensitivity="PROJECT",
        retention_class="PIPELINE",
        created_at=UtcTimestampRef(created_at),
        manifest_digest=Sha256Ref(_PLACEHOLDER_DIGEST),
    )
    document = manifest.model_dump(mode="json", exclude_defaults=True)
    document.pop("manifest_digest", None)
    document["manifest_digest"] = content_hash(document)
    return json.dumps(document, indent=2).encode("utf-8") + b"\n"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


__all__ = [
    "ArtifactNotFound",
    "LocalCasArtifacts",
    "assemble_evidence",
]
