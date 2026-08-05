"""Deterministic test facilities (slice-00-02, AC-06).

These values are pure and injectable: a frozen UTC clock, a deterministic
identity sequence, and a temporary root with automatic cleanup. Tests never
depend on wall time, network, credentials, or user directories.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FrozenUtcClock:
    """A deterministic clock frozen at one fixed UTC instant.

    ``now()`` always returns the same value and never reads the wall clock,
    so tests depending on it are reproducible.
    """

    _now: datetime

    def now(self) -> datetime:
        return self._now


class DeterministicIdentitySequence:
    """A deterministic identity sequence with a fixed prefix and counter.

    Two sequences built with the same prefix and start produce identical
    values in the same order; ``next_id`` never touches randomness or
    identity providers.
    """

    def __init__(self, prefix: str = "id-", start: int = 0) -> None:
        self._prefix = prefix
        self._counter = start

    def next_id(self) -> str:
        value = self._counter
        self._counter += 1
        return f"{self._prefix}{value}"
