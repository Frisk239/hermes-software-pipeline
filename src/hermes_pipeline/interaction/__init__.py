"""interaction Module — public deliver/ingest Interface.

Delivery and ingestion of operator-facing interaction events. The
Module boundary is fixed by ``docs/architecture/system-and-module-design.md``.
The fake cannot accept an approval.
"""

from hermes_pipeline.interaction.fake import FakeInteraction
from hermes_pipeline.interaction.ports import (
    ApprovalRejected,
    InteractionPort,
    InteractionReceipt,
)

__all__ = [
    "ApprovalRejected",
    "FakeInteraction",
    "InteractionPort",
    "InteractionReceipt",
]
