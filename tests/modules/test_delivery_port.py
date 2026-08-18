"""Shared contract tests for the Delivery Interface fake."""

from __future__ import annotations

import ast
from pathlib import Path

from hermes_pipeline.delivery import DeliveryPort, DeliveryRequest, FakeDelivery

FAKE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "hermes_pipeline"
    / "delivery"
    / "fake.py"
)
FORBIDDEN = frozenset({"git", "subprocess", "os", "github"})


def test_fake_is_a_delivery_port() -> None:
    assert isinstance(FakeDelivery(), DeliveryPort)


def test_publish_and_reconcile_are_recorded() -> None:
    fake = FakeDelivery()
    request = DeliveryRequest(name="c" * 64, project_id="prj_a", pipeline_id="pl_a")
    published = fake.publish(request)
    reconciled = fake.reconcile(request)
    assert published == reconciled
    assert published.ok is True
    assert published.action == "RECORDED"
    assert published.branch == "hermes/prj_a/pl_a"
    assert published.pr_number == 1
    assert published.head_sha == "c" * 64


def test_same_sha_is_idempotent_and_new_sha_updates_same_pr() -> None:
    fake = FakeDelivery()
    first = fake.publish(
        DeliveryRequest(name="a" * 64, project_id="prj_a", pipeline_id="pl_a")
    )
    again = fake.publish(
        DeliveryRequest(name="a" * 64, project_id="prj_a", pipeline_id="pl_a")
    )
    updated = fake.publish(
        DeliveryRequest(name="b" * 64, project_id="prj_a", pipeline_id="pl_a")
    )
    other = fake.publish(
        DeliveryRequest(name="a" * 64, project_id="prj_a", pipeline_id="pl_b")
    )
    assert again == first
    assert updated.pr_number == first.pr_number
    assert updated.head_sha == "b" * 64
    assert other.pr_number != first.pr_number


def test_observe_is_deduped_and_new_sha_resets_checks() -> None:
    fake = FakeDelivery()
    request = DeliveryRequest(name="a" * 64, project_id="prj_a", pipeline_id="pl_a")
    fake.publish(request)
    first = fake.reconcile(
        DeliveryRequest(
            name="a" * 64,
            project_id="prj_a",
            pipeline_id="pl_a",
            event_id="evt_check_1",
            check_status="success",
            review_status="approved",
            queue_status="queued",
        )
    )
    dup = fake.reconcile(
        DeliveryRequest(
            name="a" * 64,
            project_id="prj_a",
            pipeline_id="pl_a",
            event_id="evt_check_1",
            check_status="failure",
            review_status="changes_requested",
            queue_status="blocked",
        )
    )
    assert first.check_status == "success"
    assert first.review_status == "approved"
    assert first.queue_status == "queued"
    assert dup == first
    reset = fake.publish(
        DeliveryRequest(name="b" * 64, project_id="prj_a", pipeline_id="pl_a")
    )
    assert reset.check_status == ""
    assert reset.review_status == ""
    assert reset.queue_status == ""


def test_observe_without_pr_is_not_ok() -> None:
    fake = FakeDelivery()
    missed = fake.reconcile(
        DeliveryRequest(
            name="",
            pipeline_id="pl_missing",
            event_id="evt_1",
            check_status="success",
        )
    )
    assert missed.ok is False


def test_fake_never_calls_git_or_github() -> None:
    tree = ast.parse(FAKE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint(FORBIDDEN)


def test_fake_cannot_approve_or_merge() -> None:
    fake = FakeDelivery()
    assert not hasattr(fake, "approve")
    assert not hasattr(fake, "merge")
    assert not hasattr(FakeDelivery, "approve")
    assert not hasattr(FakeDelivery, "merge")
