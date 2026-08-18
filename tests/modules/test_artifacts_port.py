"""Shared contract tests for Fake and LocalCas Artifacts adapters."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hermes_pipeline.artifacts import (
    ArtifactPutRequest,
    ArtifactsPort,
    FakeArtifacts,
    LocalCasArtifacts,
)


@pytest.fixture(params=["fake", "local_cas"])
def artifacts_port(request: pytest.FixtureRequest, tmp_path: Path) -> ArtifactsPort:
    if request.param == "fake":
        return FakeArtifacts()
    return LocalCasArtifacts(tmp_path)


def test_adapter_is_an_artifacts_port(artifacts_port: ArtifactsPort) -> None:
    assert isinstance(artifacts_port, ArtifactsPort)


def test_fake_is_an_artifacts_port() -> None:
    assert isinstance(FakeArtifacts(), ArtifactsPort)


def test_put_open_verify_round_trip_keys_by_sha256(
    artifacts_port: ArtifactsPort,
) -> None:
    payload = b"slice-00-07-artifact"
    digest = hashlib.sha256(payload).hexdigest()
    record = artifacts_port.put(ArtifactPutRequest(payload=payload))
    assert record.digest == digest
    assert artifacts_port.open(record.artifact_id) == payload
    assert artifacts_port.verify(record.artifact_id).ok is True
    assert artifacts_port.verify("missing").ok is False


def test_fake_keys_artifact_id_by_hex_digest() -> None:
    fake = FakeArtifacts()
    payload = b"slice-00-07-artifact"
    digest = hashlib.sha256(payload).hexdigest()
    record = fake.put(ArtifactPutRequest(payload=payload))
    assert record.artifact_id == digest
