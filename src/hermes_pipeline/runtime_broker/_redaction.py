"""Hermes-side bounded redaction (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE
"""

from __future__ import annotations

from collections.abc import Iterable

MAX_BOUNDED_BYTES = 4096
REDACTED = "[REDACTED]"


def bound_text(text: str, limit: int = MAX_BOUNDED_BYTES) -> str:
    """Cap captured text by UTF-8 byte length."""
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", errors="ignore")


def redact(text: str, canaries: Iterable[str]) -> str:
    """Replace every canary with a marker. Vendor sanitizers are unused."""
    redacted = text
    for canary in canaries:
        if canary:
            redacted = redacted.replace(canary, REDACTED)
    return bound_text(redacted)


def child_environment(
    base: dict[str, str],
    *,
    allow: Iterable[str],
    canaries: Iterable[str],
) -> dict[str, str]:
    """Build a child env that never inherits secret canaries."""
    allowed = set(allow)
    forbidden = set(canaries)
    cleaned: dict[str, str] = {}
    for key, value in base.items():
        if key in forbidden or value in forbidden:
            continue
        if allowed and key not in allowed:
            continue
        cleaned[key] = value
    return cleaned
