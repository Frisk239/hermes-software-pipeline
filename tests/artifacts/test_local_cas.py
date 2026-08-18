from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

from hermes_pipeline.artifacts import (
    ArtifactNotFound,
    ArtifactPutRequest,
    LocalCasArtifacts,
    assemble_evidence,
)
from hermes_pipeline.contracts.jcs import content_hash
from hermes_pipeline.contracts.runtime import ArtifactManifest

_ARTIFACT_ID = re.compile(r"^art_[A-Za-z0-9_-]+$")
_CONTROLLER = (
    Path(__file__).resolve().parents[2] / "src" / "hermes_pipeline" / "controller"
)


def test_put_open_verify_round_trip(tmp_path: Path) -> None:
    cas = LocalCasArtifacts(tmp_path)
    payload = b"hello"
    digest = hashlib.sha256(payload).hexdigest()
    record = cas.put(ArtifactPutRequest(payload=payload))
    assert record.digest == digest
    assert _ARTIFACT_ID.fullmatch(record.artifact_id)
    assert cas.open(record.artifact_id) == payload
    assert cas.verify(record.artifact_id).ok is True


def test_open_unknown_id_raises(tmp_path: Path) -> None:
    cas = LocalCasArtifacts(tmp_path)
    with pytest.raises(ArtifactNotFound):
        cas.open("art_missing")


def test_survives_new_instance_on_same_root(tmp_path: Path) -> None:
    first = LocalCasArtifacts(tmp_path)
    record = first.put(ArtifactPutRequest(payload=b"hello"))
    del first
    second = LocalCasArtifacts(tmp_path)
    assert second.open(record.artifact_id) == b"hello"
    assert second.verify(record.artifact_id).ok is True


def test_same_content_reuses_digest_without_tmp_files(tmp_path: Path) -> None:
    cas = LocalCasArtifacts(tmp_path)
    first = cas.put(ArtifactPutRequest(payload=b"hello"))
    second = cas.put(ArtifactPutRequest(payload=b"hello"))
    assert first.digest == second.digest
    assert first.artifact_id == second.artifact_id
    blobs = list((tmp_path / "blobs").iterdir())
    assert len(blobs) == 1
    assert not any(path.name.endswith(".tmp") for path in tmp_path.rglob("*"))


def test_put_writes_sidecar_manifest(tmp_path: Path) -> None:
    cas = LocalCasArtifacts(tmp_path, created_at="2026-08-06T00:00:00.000Z")
    record = cas.put(ArtifactPutRequest(payload=b"hello"))
    path = tmp_path / "manifests" / f"{record.artifact_id}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    manifest = ArtifactManifest.model_validate(document)
    assert manifest.artifact_id == record.artifact_id
    assert manifest.content_digest == f"sha256:{record.digest}"
    assert manifest.logical_role == "stage-output"
    assert manifest.media_type == "application/octet-stream"
    assert manifest.sensitivity == "PROJECT"
    assert manifest.retention_class == "PIPELINE"
    body = {key: value for key, value in document.items() if key != "manifest_digest"}
    assert document["manifest_digest"] == content_hash(body)


def test_verify_rejects_tampered_blob(tmp_path: Path) -> None:
    cas = LocalCasArtifacts(tmp_path)
    record = cas.put(ArtifactPutRequest(payload=b"hello"))
    blob = tmp_path / "blobs" / record.digest
    blob.write_bytes(b"tampered")
    assert cas.verify(record.artifact_id).ok is False


def test_assemble_evidence_requires_every_id(tmp_path: Path) -> None:
    cas = LocalCasArtifacts(tmp_path)
    kept = cas.put(ArtifactPutRequest(payload=b"hello"))
    extra = cas.put(ArtifactPutRequest(payload=b"world"))
    assert assemble_evidence(cas, [kept.artifact_id, extra.artifact_id]).ok is True
    assert assemble_evidence(cas, [kept.artifact_id, "art_missing"]).ok is False


def test_controller_does_not_import_local_cas() -> None:
    for path in _CONTROLLER.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            assert all("local_cas" not in name for name in names)
