"""Public Delivery Interface adopted by Slice 00-07.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class DeliveryRequest:
    name: str
    project_id: str = ""
    pipeline_id: str = ""


@dataclass(frozen=True)
class DeliveryRecord:
    ok: bool
    action: Literal["RECORDED"]
    branch: str = ""
    pr_number: int = 0
    head_sha: str = ""


@runtime_checkable
class DeliveryPort(Protocol):
    def publish(self, request: DeliveryRequest) -> DeliveryRecord:
        """Record a publish intent. No approve or merge."""
        ...

    def reconcile(self, request: DeliveryRequest) -> DeliveryRecord:
        """Record a reconcile intent. No approve or merge."""
        ...


__all__ = ["DeliveryPort", "DeliveryRecord", "DeliveryRequest"]
