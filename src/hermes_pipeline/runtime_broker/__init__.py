"""runtime_broker Module — public launch/signal/inspect/collect Interface.

Host runners and vendor probes remain keep-marked evidence and do not
implement this Protocol.
"""

from hermes_pipeline.runtime_broker.fake import FakeRuntimeBroker
from hermes_pipeline.runtime_broker.ports import (
    RuntimeBrokerPort,
    RuntimeHandle,
    RuntimeLaunchRequest,
    RuntimeOutcome,
    RuntimeSignalReceipt,
    RuntimeSnapshot,
)

__all__ = [
    "FakeRuntimeBroker",
    "RuntimeBrokerPort",
    "RuntimeHandle",
    "RuntimeLaunchRequest",
    "RuntimeOutcome",
    "RuntimeSignalReceipt",
    "RuntimeSnapshot",
]
