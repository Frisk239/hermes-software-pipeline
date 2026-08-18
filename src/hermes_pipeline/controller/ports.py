"""Public Controller Interface adopted by Slice 00-07.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from hermes_pipeline.contracts.runtime import CommandReceipt, ControllerCommand


@dataclass(frozen=True)
class PipelineQuery:
    pipeline_id: str
    workspace_id: str = ""


@dataclass(frozen=True)
class PipelineView:
    pipeline_id: str
    revision: int
    status: Literal["UNCONFIRMED", "OPEN", "REJECTED"]


@runtime_checkable
class ControllerPort(Protocol):
    def submit(self, command: ControllerCommand) -> CommandReceipt:
        """Submit one immutable Controller Command and return its receipt."""
        ...

    def read(self, query: PipelineQuery) -> PipelineView:
        """Return a fixture Pipeline view. No RBAC."""
        ...


__all__ = ["ControllerPort", "PipelineQuery", "PipelineView"]
