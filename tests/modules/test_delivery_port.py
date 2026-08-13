"""Shared contract tests for the Delivery Interface fake."""

from __future__ import annotations

from hermes_pipeline.delivery import DeliveryPort, DeliveryRequest, FakeDelivery


def test_fake_is_a_delivery_port() -> None:
    assert isinstance(FakeDelivery(), DeliveryPort)


def test_publish_and_reconcile_are_recorded() -> None:
    fake = FakeDelivery()
    published = fake.publish(DeliveryRequest(name="candidate"))
    reconciled = fake.reconcile(DeliveryRequest(name="candidate"))
    assert published == reconciled
    assert published.ok is True
    assert published.action == "RECORDED"


def test_fake_cannot_approve_or_merge() -> None:
    fake = FakeDelivery()
    assert not hasattr(fake, "approve")
    assert not hasattr(fake, "merge")
    assert not hasattr(FakeDelivery, "approve")
    assert not hasattr(FakeDelivery, "merge")
