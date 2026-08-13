"""Event hash-chain computation for the Controller Event Log (slice-00-04).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE

The authoritative Event Log is an append-only chain: every Event row stores
``previous_event_hash`` (the hash of the immediately preceding Event, or
``None`` for the first Event) and its own ``event_hash``. The chain is
verified when a projection is rebuilt (AC-06): any tampered row breaks the
chain and the rebuild fails instead of producing a projection.

The chain algorithm lives here, and only here, so the SQLite spike Adapter
and the projection rebuild path share one implementation. The Controller
never computes event hashes.
"""

from __future__ import annotations

import hashlib

from hermes_pipeline.contracts.jcs import canonical_json

#: Canonical separator between chain fields; fixed and documented.
_CHAIN_SEPARATOR = "|"


def chain_hash(
    previous_event_hash: str | None, sequence: int, payload_json: str
) -> str:
    """Compute the deterministic event hash for one Event row.

    The hash covers the previous link, the strict 1-based sequence (which
    equals the pipeline revision), and the canonical payload JSON, so any
    reordering, payload tampering, or link rewriting changes the hash.
    """
    prev = previous_event_hash if previous_event_hash is not None else ""
    material = _CHAIN_SEPARATOR.join((prev, str(sequence), payload_json))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def verify_chain(events: list[tuple[int, str | None, str, str]]) -> None:
    """Verify a complete Event Log chain.

    ``events`` is a list of ``(sequence, previous_event_hash, event_hash,
    payload_json)`` rows ordered by sequence. Raises ``ValueError`` with a
    bounded message when the first previous link is not ``None``, a link
    mismatches its predecessor, or a row's stored hash does not match the
    recomputed hash.
    """
    expected_previous: str | None = None
    for index, (sequence, previous, stored_hash, payload) in enumerate(events):
        expected_sequence = index + 1
        if sequence != expected_sequence:
            raise ValueError(
                f"event chain sequence gap at {sequence} (expected {expected_sequence})"
            )
        if previous != expected_previous:
            raise ValueError(f"event chain link mismatch at sequence {sequence}")
        recomputed = chain_hash(previous, sequence, payload)
        if stored_hash != recomputed:
            raise ValueError(f"event chain hash mismatch at sequence {sequence}")
        expected_previous = stored_hash


def canonical_event_payload(value: int, revision: int) -> str:
    """Canonical JSON payload of a CounterIncremented event (value, revision)."""
    return canonical_json({"value": value, "revision": revision})


__all__ = ["canonical_event_payload", "chain_hash", "verify_chain"]
