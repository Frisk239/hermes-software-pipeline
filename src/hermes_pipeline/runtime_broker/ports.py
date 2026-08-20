"""Public Runtime Broker Interface adopted by Slice 00-07.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

RuntimeStatus = Literal["FAKE", "UNSUPPORTED", "COMPLETED", "CANCELLED", "FAILED"]


@dataclass(frozen=True)
class RuntimeLaunchRequest:
    runtime_id: str
    role: str = ""
    model: str = ""
    prompt: str = ""
    origin: str = ""


@dataclass(frozen=True)
class RuntimeHandle:
    runtime_id: str
    status: RuntimeStatus = "FAKE"


@dataclass(frozen=True)
class RuntimeSignalReceipt:
    ok: bool = False
    code: Literal["UNSUPPORTED", "CANCELLED"] = "UNSUPPORTED"


@dataclass(frozen=True)
class RuntimeSnapshot:
    runtime_id: str
    status: RuntimeStatus = "FAKE"


@dataclass(frozen=True)
class RuntimeOutcome:
    runtime_id: str
    status: RuntimeStatus = "FAKE"
    detail: str = ""
    final_text: str = ""


@runtime_checkable
class RuntimeBrokerPort(Protocol):
    def launch(self, request: RuntimeLaunchRequest) -> RuntimeHandle:
        """Launch or refuse a runtime. Fake never starts a vendor CLI."""
        ...

    def signal(self, runtime_id: str) -> RuntimeSignalReceipt:
        """Signal a runtime (cancel) or refuse the signal."""
        ...

    def inspect(self, runtime_id: str) -> RuntimeSnapshot:
        """Return the current runtime snapshot."""
        ...

    def collect(self, runtime_id: str) -> RuntimeOutcome:
        """Return the collected runtime outcome."""
        ...


__all__ = [
    "RuntimeBrokerPort",
    "RuntimeHandle",
    "RuntimeLaunchRequest",
    "RuntimeOutcome",
    "RuntimeSignalReceipt",
    "RuntimeSnapshot",
    "RuntimeStatus",
]
