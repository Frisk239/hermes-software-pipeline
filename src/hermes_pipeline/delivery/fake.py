"""Deterministic Delivery Adapter with no approve or merge methods.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from typing import Any, cast

from hermes_pipeline.delivery.ports import DeliveryRecord, DeliveryRequest


class FakeDelivery:
    def __init__(self) -> None:
        self._records: dict[str, DeliveryRecord] = {}
        self._next_pr = 1

    def publish(self, request: DeliveryRequest) -> DeliveryRecord:
        key = _pipeline_key(request)
        existing = self._records.get(key)
        if existing is not None:
            if existing.head_sha == request.name:
                return existing
            updated = DeliveryRecord(
                ok=True,
                action="RECORDED",
                branch=existing.branch,
                pr_number=existing.pr_number,
                head_sha=request.name,
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
        stored = self._records.get(_pipeline_key(request))
        if stored is not None:
            return stored
        return self.publish(request)

    def lookup(self, pipeline_id: str) -> DeliveryRecord | None:
        return self._records.get(pipeline_id)

    def dump(self) -> dict[str, Any]:
        return {
            "next_pr": self._next_pr,
            "records": {
                key: {
                    "ok": record.ok,
                    "action": record.action,
                    "branch": record.branch,
                    "pr_number": record.pr_number,
                    "head_sha": record.head_sha,
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
            )
        return fake


def _pipeline_key(request: DeliveryRequest) -> str:
    return request.pipeline_id or request.name


def _branch_name(request: DeliveryRequest) -> str:
    project = request.project_id or "prj_local"
    pipeline = request.pipeline_id or "pl_local"
    return f"hermes/{project}/{pipeline}"


__all__ = ["FakeDelivery"]
