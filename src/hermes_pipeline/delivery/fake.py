"""Deterministic Delivery Adapter with no approve or merge methods.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from hermes_pipeline.delivery.ports import DeliveryRecord, DeliveryRequest


class FakeDelivery:
    def publish(self, request: DeliveryRequest) -> DeliveryRecord:
        return DeliveryRecord(ok=True, action="RECORDED")

    def reconcile(self, request: DeliveryRequest) -> DeliveryRecord:
        return DeliveryRecord(ok=True, action="RECORDED")


__all__ = ["FakeDelivery"]
