"""Public Interaction Interface adopted by Slice 00-07.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from hermes_pipeline.contracts.runtime import ControllerCommand


@dataclass(frozen=True)
class InteractionReceipt:
    ok: bool


class ApprovalRejected(ValueError):
    """Raised when an ingested event attempts to accept an approval."""


@runtime_checkable
class InteractionPort(Protocol):
    def deliver(self, text: str) -> InteractionReceipt:
        """Record an outbound interaction."""
        ...

    def ingest(self, event: str) -> ControllerCommand:
        """Ingest one event as the committed fixture command."""
        ...


__all__ = ["ApprovalRejected", "InteractionPort", "InteractionReceipt"]
