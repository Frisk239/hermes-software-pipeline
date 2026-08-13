"""Deterministic Repository Adapter that never calls Git.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from hermes_pipeline.repository.ports import RepositoryRecord, RepositoryRequest


class FakeRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def prepare(self, request: RepositoryRequest) -> RepositoryRecord:
        self.calls.append(("prepare", request.name))
        return RepositoryRecord(ok=True, action="prepare")

    def create_candidate(self, request: RepositoryRequest) -> RepositoryRecord:
        self.calls.append(("create_candidate", request.name))
        return RepositoryRecord(ok=True, action="create_candidate")

    def verify(self, request: RepositoryRequest) -> RepositoryRecord:
        self.calls.append(("verify", request.name))
        return RepositoryRecord(ok=True, action="verify")

    def cleanup(self, request: RepositoryRequest) -> RepositoryRecord:
        self.calls.append(("cleanup", request.name))
        return RepositoryRecord(ok=True, action="cleanup")


__all__ = ["FakeRepository"]
