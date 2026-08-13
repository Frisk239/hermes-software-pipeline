"""Public Repository Interface adopted by Slice 00-07.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RepositoryRequest:
    name: str


@dataclass(frozen=True)
class RepositoryRecord:
    ok: bool
    action: str


@runtime_checkable
class RepositoryPort(Protocol):
    def prepare(self, request: RepositoryRequest) -> RepositoryRecord:
        """Record a prepare call. Never mutates Git."""
        ...

    def create_candidate(self, request: RepositoryRequest) -> RepositoryRecord:
        """Record a create-candidate call. Never mutates Git."""
        ...

    def verify(self, request: RepositoryRequest) -> RepositoryRecord:
        """Record a verify call. Never mutates Git."""
        ...

    def cleanup(self, request: RepositoryRequest) -> RepositoryRecord:
        """Record a cleanup call. Never mutates Git."""
        ...


__all__ = ["RepositoryPort", "RepositoryRecord", "RepositoryRequest"]
