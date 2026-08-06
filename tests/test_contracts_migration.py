"""Pure compatibility migration Interface tests (AC-08).

The registry maps each of the 14 $ids to a finite supported version range;
migration is a pure function with no storage or business state. A v1-to-v1
migration is the identity and records the original identity plus digests;
out-of-range requests error without any state change.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_pipeline.contracts.generate import generate_compatibility_registry
from hermes_pipeline.contracts.migration import migrate

REPO_ROOT = Path(__file__).resolve().parents[1]

DOCUMENT = {
    "schema_id": "https://schemas.hermes-pipeline.dev/engineering/closeout/v1",
    "schema_version": 1,
    "closeout_id": "close_slice_00_02",
    "scope_kind": "SLICE",
    "scope_id": "slice-00-02",
    "base_sha": "a" * 40,
    "accepted_sha": "a" * 40,
    "delivered": ["x"],
    "evidence": [
        {
            "artifact_id": "art_evidence_001",
            "manifest_digest": "sha256:" + "c" * 64,
            "role": "r",
        }
    ],
    "residual_debt": [],
    "next_prerequisites": [],
    "closed_at": "2026-08-06T00:00:00.000Z",
    "content_hash": "sha256:" + "c" * 64,
}


def test_registry_generation_is_committed_and_valid() -> None:
    committed = json.loads(
        (REPO_ROOT / "contracts" / "compatibility-registry.json").read_text(
            encoding="utf-8"
        )
    )
    assert committed == generate_compatibility_registry()


def test_v1_to_v1_identity_migration_records_identity_and_digests() -> None:
    registry = generate_compatibility_registry()
    entry = migrate(
        registry,
        "https://schemas.hermes-pipeline.dev/engineering/closeout/v1",
        1,
        DOCUMENT,
    )
    assert entry.schema_id == DOCUMENT["schema_id"]
    assert entry.from_version == 1
    assert entry.to_version == 1
    assert entry.source_digest == entry.migrated_digest
    assert entry.source_digest.startswith("sha256:")
    assert len(entry.source_digest) == len("sha256:") + 64


def test_out_of_range_migration_errors_without_state_change() -> None:
    registry = generate_compatibility_registry()
    with pytest.raises(ValueError):
        migrate(
            registry,
            "https://schemas.hermes-pipeline.dev/engineering/closeout/v1",
            2,
            DOCUMENT,
        )
    with pytest.raises(ValueError):
        migrate(
            registry,
            "https://schemas.hermes-pipeline.dev/engineering/closeout/v1",
            0,
            DOCUMENT,
        )
    with pytest.raises(ValueError):
        migrate(
            registry,
            "https://schemas.hermes-pipeline.dev/engineering/nonexistent/v1",
            1,
            DOCUMENT,
        )
    # no state changed: the registry is a pure mapping
    assert registry == generate_compatibility_registry()


def test_mismatched_document_identity_is_rejected() -> None:
    """A document whose schema_id differs from the requested registry
    identity must be rejected (revision 6)."""
    registry = generate_compatibility_registry()
    mismatched = dict(DOCUMENT)
    mismatched["schema_id"] = (
        "https://schemas.hermes-pipeline.dev/engineering/execution-report/v1"
    )
    with pytest.raises(ValueError, match="does not match the requested identity"):
        migrate(
            registry,
            "https://schemas.hermes-pipeline.dev/engineering/closeout/v1",
            1,
            mismatched,
        )


def test_unsupported_source_version_is_rejected() -> None:
    """A document whose source schema_version is outside the supported range
    must be rejected, even when the requested target is supported."""
    registry = generate_compatibility_registry()
    unsupported = dict(DOCUMENT)
    unsupported["schema_version"] = 2
    with pytest.raises(ValueError, match="source version 2 is outside"):
        migrate(
            registry,
            "https://schemas.hermes-pipeline.dev/engineering/closeout/v1",
            1,
            unsupported,
        )


def test_non_integer_schema_version_is_rejected() -> None:
    registry = generate_compatibility_registry()
    for bad in ("1", True, 1.5):
        document: dict[str, object] = dict(DOCUMENT)
        document["schema_version"] = bad
        with pytest.raises(ValueError, match="no integer schema_version"):
            migrate(
                registry,
                "https://schemas.hermes-pipeline.dev/engineering/closeout/v1",
                1,
                document,
            )


def test_integral_float_source_schema_version_is_accepted() -> None:
    """Serialized Schema documents use Draft integer semantics: ``1.0`` is v1."""
    registry = generate_compatibility_registry()
    document: dict[str, object] = dict(DOCUMENT)
    document["schema_version"] = 1.0
    entry = migrate(
        registry,
        "https://schemas.hermes-pipeline.dev/engineering/closeout/v1",
        1,
        document,
    )
    assert entry.from_version == 1
    assert entry.to_version == 1


def test_non_integer_target_version_is_rejected() -> None:
    registry = generate_compatibility_registry()
    for bad in ("1", True, 1.0):
        with pytest.raises(ValueError, match="target version must be an integer"):
            migrate(
                registry,
                "https://schemas.hermes-pipeline.dev/engineering/closeout/v1",
                bad,
                DOCUMENT,
            )


def test_recorded_identity_is_the_verified_document_identity() -> None:
    """The recorded identity is the verified identity from the document
    (revision 6), and the source version must be within the supported range."""
    registry = generate_compatibility_registry()
    entry = migrate(
        registry,
        "https://schemas.hermes-pipeline.dev/engineering/closeout/v1",
        1,
        DOCUMENT,
    )
    assert entry.schema_id == DOCUMENT["schema_id"]


def test_every_registry_entry_migrates_identity() -> None:
    registry = generate_compatibility_registry()
    for schema_id, entry in registry.items():
        current = entry["current_version"]
        assert current in entry["supported_versions"]
        document = {"schema_id": schema_id, "schema_version": current}
        migrated = migrate(registry, schema_id, current, document)
        assert migrated.to_version == current
        assert migrated.source_digest == migrated.migrated_digest
