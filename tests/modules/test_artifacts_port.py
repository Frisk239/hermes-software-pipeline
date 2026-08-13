"""Shared contract tests for the Artifacts Interface fake."""

from __future__ import annotations

import hashlib

from hermes_pipeline.artifacts import (
    ArtifactPutRequest,
    ArtifactsPort,
    FakeArtifacts,
)


def test_fake_is_an_artifacts_port() -> None:
    assert isinstance(FakeArtifacts(), ArtifactsPort)


def test_put_open_verify_round_trip_keys_by_sha256() -> None:
    fake = FakeArtifacts()
    payload = b"slice-00-07-artifact"
    digest = hashlib.sha256(payload).hexdigest()
    record = fake.put(ArtifactPutRequest(payload=payload))
    assert record.digest == digest
    assert record.artifact_id == digest
    assert fake.open(record.artifact_id) == payload
    assert fake.verify(record.artifact_id).ok is True
    assert fake.verify("missing").ok is False
