"""Pure compatibility migration Interface (AC-08).

The registry records finite supported version ranges per schema identity.
Migration is a pure function of the registry and the document bytes: it
verifies the document's own ``schema_id`` against the requested registry
identity and the source/target versions against the supported range, records
the verified original schema identity and the migrated digest, and performs
no storage, business state, or real transformation. A v1-to-v1 migration is
the identity: the document passes through unchanged and the source and
migrated digests are equal. Out-of-range requests raise ``ValueError``
without any state change.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from .jcs import content_hash


@dataclass(frozen=True)
class MigrationEntry:
    """One migration record: identity, version range, and digests."""

    schema_id: str
    from_version: int
    to_version: int
    source_digest: str
    migrated_digest: str


def _supported_versions(entry: Mapping[str, Any]) -> list[int]:
    """The strictly increasing supported range of one registry entry."""
    supported = entry.get("supported_versions")
    if not isinstance(supported, list) or not supported:
        raise ValueError(f"registry entry {entry!r} is malformed")
    supported = cast(list[Any], supported)
    if not all(
        isinstance(item, int) and not isinstance(item, bool) for item in supported
    ):
        raise ValueError(f"registry entry {entry!r} is malformed")
    supported = cast(list[int], supported)
    if any(supported[i] >= supported[i + 1] for i in range(len(supported) - 1)):
        raise ValueError(f"registry entry {entry!r} is malformed")
    return supported


def _source_version(value: object) -> int:
    """Normalize one JSON-document schema version without widening it.

    JSON Schema's ``integer`` and ``const: 1`` semantics accept a finite
    integral JSON number such as ``1.0`` but reject booleans, strings, and
    non-integral numbers. Migration consumes serialized document data, so
    its source boundary must match the root-contract models and Schemas.
    The target is an API argument and deliberately remains an exact Python
    ``int`` below.
    """
    if isinstance(value, bool):
        raise ValueError("document has no integer schema_version")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise ValueError("document has no integer schema_version")


def migrate(
    registry: Mapping[str, Mapping[str, Any]],
    schema_id: str,
    to_version: object,
    document: Mapping[str, Any],
) -> MigrationEntry:
    """Migrate one document to a supported version (pure, no side effects).

    ``registry`` maps each schema ``$id`` to ``{"current_version": int,
    "supported_versions": [int, ...]}``. The requested identity must match
    the document's own ``schema_id``, and both the document's source version
    and the requested target must be members of ``supported_versions``; the
    recorded identity is the verified identity from the document.
    """
    entry = registry.get(schema_id)
    if entry is None:
        raise ValueError(f"schema {schema_id!r} is not registered")
    supported = _supported_versions(entry)

    source_identity = document.get("schema_id")
    if not isinstance(source_identity, str):
        raise ValueError("document has no string schema_id")
    if source_identity != schema_id:
        raise ValueError(
            f"document schema_id {source_identity!r} does not match the "
            f"requested identity {schema_id!r}"
        )

    source_version = _source_version(document.get("schema_version"))
    if source_version not in supported:
        raise ValueError(
            f"source version {source_version} is outside the supported range "
            f"for {schema_id!r} ({supported})"
        )
    if not isinstance(to_version, int) or isinstance(to_version, bool):
        raise ValueError("target version must be an integer")
    target_version = to_version
    if target_version not in supported:
        raise ValueError(
            f"version {target_version} is outside the supported range for "
            f"{schema_id!r} ({supported})"
        )
    if source_version != target_version:
        raise ValueError(
            "migration from version "
            f"{source_version} to {target_version} is "
            "not implemented; only identity migrations are supported"
        )

    migrated = dict(document)
    source_digest = content_hash(dict(document))
    migrated_digest = content_hash(migrated)
    return MigrationEntry(
        schema_id=source_identity,
        from_version=source_version,
        to_version=target_version,
        source_digest=source_digest,
        migrated_digest=migrated_digest,
    )
