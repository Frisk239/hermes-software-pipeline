"""RFC 8785 canonical JSON and content hashing.

``rfc8785`` is the single JCS implementation (ADR-0026, human planning
decision 2026-08-06); no sorted-key approximation exists anywhere in this
package (enforced by a regression test). ``content_hash`` values are
computed with the ``content_hash`` field absent, as UTF-8 SHA-256 prefixed
with ``sha256:`` (the ``common/definitions`` ``sha256`` shape).
"""

from __future__ import annotations

import hashlib
from typing import Any

import rfc8785


def canonical_json(value: Any) -> str:
    """RFC 8785 canonical JSON text for a Python value.

    Raises ``ValueError`` for NaN, Infinity, and lone surrogates, which the
    canonical form cannot represent.
    """
    return rfc8785.dumps(value).decode("utf-8")


def content_hash(document: dict[str, Any]) -> str:
    """``sha256:<hex>`` of the RFC 8785 canonical document.

    The ``content_hash`` field itself is excluded from the canonicalization,
    matching the committed contract documents.
    """
    digest = hashlib.sha256(
        canonical_json(
            {k: v for k, v in document.items() if k != "content_hash"}
        ).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def raw_digest(data: bytes) -> str:
    """``sha256:<hex>`` of raw bytes (fixture snapshots and artifacts)."""
    return f"sha256:{hashlib.sha256(data).hexdigest()}"
