"""Public Runtime Broker Interface adopted by Slice 00-07.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class RuntimeLaunchRequest:
    runtime_id: str


@dataclass(frozen=True)
class RuntimeHandle:
    runtime_id: str
    status: Literal["FAKE"] = "FAKE"


@dataclass(frozen=True)
class RuntimeSignalReceipt:
    ok: bool = False
    code: Literal["UNSUPPORTED"] = "UNSUPPORTED"


@dataclass(frozen=True)
class RuntimeSnapshot:
    runtime_id: str
    status: Literal["FAKE"] = "FAKE"


@dataclass(frozen=True)
class RuntimeOutcome:
    runtime_id: str
    status: Literal["FAKE"] = "FAKE"


@runtime_checkable
class RuntimeBrokerPort(Protocol):
    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        """Record a fake runtime launch. Never starts a vendor CLI."""
        ...

    def signal(self, runtime_id: str) -> RuntimeSignalReceipt:
        """Refuse vendor signals."""
        ...

    def inspect(self, runtime_id: str) -> RuntimeSnapshot:
        """Return a fake snapshot."""
        ...

    def collect(self, runtime_id: str) -> RuntimeOutcome:
        """Return a fake outcome."""
        ...


__all__ = [
    "RuntimeBrokerPort",
    "RuntimeHandle",
    "RuntimeLaunchRequest",
    "RuntimeOutcome",
    "RuntimeSignalReceipt",
    "RuntimeSnapshot",
]
