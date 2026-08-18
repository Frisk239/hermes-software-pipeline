"""Least-privilege GitHub PR adapter. No approve or merge.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from hermes_pipeline.delivery.ports import DeliveryRecord, DeliveryRequest

GitHubTransport = Callable[
    [str, str, dict[str, str], dict[str, object]],
    tuple[int, object],
]


class GitHubDelivery:
    def __init__(
        self,
        repo: str,
        token: str,
        transport: GitHubTransport,
        base: str = "main",
    ) -> None:
        self._repo = repo
        self._token = token
        self._transport = transport
        self._base = base or "main"
        self._records: dict[str, DeliveryRecord] = {}

    def publish(self, request: DeliveryRequest) -> DeliveryRecord:
        if not self._token or "/" not in self._repo:
            return DeliveryRecord(ok=False, action="RECORDED")
        key = request.pipeline_id or request.name
        existing = self._records.get(key)
        if existing is not None and existing.head_sha == request.name:
            return existing
        branch = existing.branch if existing is not None else _branch_name(request)
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
        }
        body: dict[str, object] = {
            "title": f"hermes {request.pipeline_id or request.name}",
            "head": branch,
            "base": self._base,
        }
        status, raw = self._transport(
            "POST", f"/repos/{self._repo}/pulls", headers, body
        )
        payload: object = raw
        if status == 422 and existing is not None:
            return existing
        if status == 422:
            owner = self._repo.split("/", 1)[0]
            query = f"head={owner}:{branch}&state=open"
            status, raw = self._transport(
                "GET",
                f"/repos/{self._repo}/pulls?{query}",
                headers,
                {},
            )
            payload = raw
            if status >= 300:
                return DeliveryRecord(ok=False, action="RECORDED", branch=branch)
            if isinstance(payload, list) and payload:
                payload = cast(object, payload[0])
        if status >= 300 or not isinstance(payload, dict):
            return DeliveryRecord(ok=False, action="RECORDED", branch=branch)
        document = cast(dict[str, Any], payload)
        number = int(document.get("number", 0) or 0)
        url = str(document.get("html_url", ""))
        if self._token and self._token in url:
            url = ""
        record = DeliveryRecord(
            ok=number > 0,
            action="RECORDED",
            branch=branch,
            pr_number=number,
            head_sha=request.name,
            pr_url=url,
        )
        self._records[key] = record
        return record

    def reconcile(self, request: DeliveryRequest) -> DeliveryRecord:
        key = request.pipeline_id or request.name
        stored = self._records.get(key)
        if stored is not None:
            return stored
        return self.publish(request)


def _branch_name(request: DeliveryRequest) -> str:
    project = request.project_id or "prj_local"
    pipeline = request.pipeline_id or "pl_local"
    return f"hermes/{project}/{pipeline}"


__all__ = ["GitHubDelivery", "GitHubTransport"]
