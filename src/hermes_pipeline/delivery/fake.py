"""Deterministic Delivery Adapter with no approve or merge methods.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from typing import Any, cast

from hermes_pipeline.delivery.ports import DeliveryRecord, DeliveryRequest

_CHECKS = frozenset({"pending", "success", "failure"})
_REVIEWS = frozenset({"pending", "approved", "changes_requested"})
_QUEUES = frozenset({"idle", "queued", "blocked"})


class FakeDelivery:
    def __init__(self) -> None:
        self._records: dict[str, DeliveryRecord] = {}
        self._events: set[str] = set()
        self._next_pr = 1

    def publish(self, request: DeliveryRequest) -> DeliveryRecord:
        key = _pipeline_key(request)
        existing = self._records.get(key)
        if existing is not None:
            if existing.head_sha == request.name:
                return existing
            self._forget_events(key)
            updated = DeliveryRecord(
                ok=True,
                action="RECORDED",
                branch=existing.branch,
                pr_number=existing.pr_number,
                head_sha=request.name,
                pr_url=existing.pr_url,
            )
            self._records[key] = updated
            return updated
        record = DeliveryRecord(
            ok=True,
            action="RECORDED",
            branch=_branch_name(request),
            pr_number=self._next_pr,
            head_sha=request.name,
        )
        self._next_pr += 1
        self._records[key] = record
        return record

    def reconcile(self, request: DeliveryRequest) -> DeliveryRecord:
        key = _pipeline_key(request)
        stored = self._records.get(key)
        if stored is None:
            if request.name:
                stored = self.publish(request)
            else:
                return DeliveryRecord(ok=False, action="RECORDED")
        if not request.event_id:
            return stored
        token = f"{key}:{request.event_id}"
        if token in self._events:
            return stored
        self._events.add(token)
        updated = DeliveryRecord(
            ok=True,
            action="RECORDED",
            branch=stored.branch,
            pr_number=stored.pr_number,
            head_sha=stored.head_sha,
            check_status=_pick(request.check_status, _CHECKS, stored.check_status),
            review_status=_pick(request.review_status, _REVIEWS, stored.review_status),
            queue_status=_pick(request.queue_status, _QUEUES, stored.queue_status),
            pr_url=stored.pr_url,
        )
        self._records[key] = updated
        return updated

    def lookup(self, pipeline_id: str) -> DeliveryRecord | None:
        return self._records.get(pipeline_id)

    def remember(self, pipeline_id: str, record: DeliveryRecord) -> None:
        self._records[pipeline_id] = record

    def dump(self) -> dict[str, Any]:
        return {
            "next_pr": self._next_pr,
            "events": sorted(self._events),
            "records": {
                key: {
                    "ok": record.ok,
                    "action": record.action,
                    "branch": record.branch,
                    "pr_number": record.pr_number,
                    "head_sha": record.head_sha,
                    "check_status": record.check_status,
                    "review_status": record.review_status,
                    "queue_status": record.queue_status,
                    "pr_url": record.pr_url,
                }
                for key, record in self._records.items()
            },
        }

    @classmethod
    def load(cls, document: dict[str, Any]) -> FakeDelivery:
        fake = cls()
        next_pr = document.get("next_pr")
        if isinstance(next_pr, int) and next_pr >= 1:
            fake._next_pr = next_pr
        events = document.get("events")
        if isinstance(events, list):
            fake._events = {str(item) for item in cast(list[object], events)}
        records = document.get("records")
        if not isinstance(records, dict):
            return fake
        typed = cast(dict[str, Any], records)
        for raw_key, item in typed.items():
            if not isinstance(item, dict):
                continue
            row = cast(dict[str, Any], item)
            fake._records[str(raw_key)] = DeliveryRecord(
                ok=bool(row.get("ok", True)),
                action="RECORDED",
                branch=str(row.get("branch", "")),
                pr_number=int(row.get("pr_number", 0) or 0),
                head_sha=str(row.get("head_sha", "")),
                check_status=str(row.get("check_status", "")),
                review_status=str(row.get("review_status", "")),
                queue_status=str(row.get("queue_status", "")),
                pr_url=str(row.get("pr_url", "")),
            )
        return fake

    def _forget_events(self, key: str) -> None:
        prefix = f"{key}:"
        self._events = {item for item in self._events if not item.startswith(prefix)}


def _pipeline_key(request: DeliveryRequest) -> str:
    return request.pipeline_id or request.name


def _branch_name(request: DeliveryRequest) -> str:
    project = request.project_id or "prj_local"
    pipeline = request.pipeline_id or "pl_local"
    return f"hermes/{project}/{pipeline}"


def _pick(value: str, allowed: frozenset[str], current: str) -> str:
    if value in allowed:
        return value
    return current


__all__ = ["FakeDelivery"]
