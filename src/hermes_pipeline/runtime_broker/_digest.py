"""RFC 8785 and raw-byte digests for 00-06 authorization.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE
"""

from __future__ import annotations

from typing import Any

from hermes_pipeline.contracts.jcs import content_hash, raw_digest


def object_digest(value: dict[str, Any]) -> str:
    """RFC 8785 digest of a flat authorization object."""
    return content_hash(value)


def file_digest(data: bytes) -> str:
    """Raw SHA-256 digest of committed file bytes."""
    return raw_digest(data)


def digest_hex(digest: str) -> str:
    """Strip the sha256: prefix from a digest."""
    prefix = "sha256:"
    if digest.startswith(prefix):
        return digest[len(prefix) :]
    return digest
