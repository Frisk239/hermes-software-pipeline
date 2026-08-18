"""delivery Module — public publish/reconcile Interface.

Remote delivery of verified Candidates to a protected target
repository. The Module boundary is fixed by
``docs/architecture/system-and-module-design.md``. The fake has no
approve or merge methods.
"""

from hermes_pipeline.delivery.fake import FakeDelivery
from hermes_pipeline.delivery.github import GitHubDelivery
from hermes_pipeline.delivery.ports import DeliveryPort, DeliveryRecord, DeliveryRequest

__all__ = [
    "DeliveryPort",
    "DeliveryRecord",
    "DeliveryRequest",
    "FakeDelivery",
    "GitHubDelivery",
]
