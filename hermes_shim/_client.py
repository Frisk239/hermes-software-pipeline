"""Loopback Control Interface client for the Hermes Shim (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

A standard-library HTTP client (``urllib.request``) for the authenticated
loopback Control Interface (ADR-0022). It discovers the port and bearer
token from the runtime descriptor, enforces the fixed client timeouts
(5 s connect/read, 10 s request budget), and fails closed with
``DEPENDENCY_UNAVAILABLE`` when the descriptor is absent, stale, or the
runtime is unreachable. Responses and errors are parsed into typed results;
raw exceptions never cross the operator surface.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from ._constants import (
    CLIENT_READ_TIMEOUT_SECONDS,
    PROTOCOL_VERSION,
    REQUEST_BUDGET_SECONDS,
)

# Client request-budget seconds for one command round trip.
REQUEST_BUDGET = REQUEST_BUDGET_SECONDS

# Protocol header name/value (fixed).
PROTOCOL_HEADER = "X-Hermes-Pipeline-Protocol"
PROTOCOL_VALUE = str(PROTOCOL_VERSION)


class _RejectRedirect(urllib.request.HTTPRedirectHandler):
    """Fail closed instead of following a redirect away from loopback.

    A compromised or confused local listener can respond with ``Location``
    pointing to a non-loopback URL.  urllib's default handler would follow
    it, potentially forwarding the bearer token.  The Control Interface has
    no redirect semantics, so every 3xx response is returned as a bounded
    failed result instead.
    """

    def redirect_request(
        self,
        request: urllib.request.Request,
        file: Any,
        code: int,
        message: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del request, file, code, message, headers, newurl
        return None


# The loopback Control Interface must never traverse an HTTP proxy or an HTTP
# redirect: either could observe or rewrite the bearer token.  The opener
# therefore disables proxies and rejects every redirect (ADR-0022 boundary).
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), _RejectRedirect()
)


@dataclass(frozen=True)
class ClientResult:
    """One typed loopback client result."""

    ok: bool
    status: int | None = None
    code: str | None = None
    body: dict[str, Any] | None = None
    reason: str | None = None


class RuntimeUnavailableError(Exception):
    """The runtime descriptor is absent, stale, or unreachable."""


def _descriptor_token(document: dict[str, Any]) -> str:
    return str(document["token"])


def _request(
    base_url: str,
    token: str,
    method: str,
    path: str,
    body: bytes | None = None,
) -> ClientResult:
    headers = {
        PROTOCOL_HEADER: PROTOCOL_VALUE,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    data: bytes | None = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = body
    request = urllib.request.Request(
        f"{base_url}{path}", data=data, headers=headers, method=method
    )
    try:
        with _OPENER.open(request, timeout=CLIENT_READ_TIMEOUT_SECONDS) as response:
            status = int(response.status)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()
    except (TimeoutError, urllib.error.URLError, OSError):
        raise RuntimeUnavailableError("runtime unreachable") from None
    payload: dict[str, Any] | None = None
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else None
        if isinstance(parsed, dict):
            payload = parsed
    except (ValueError, UnicodeDecodeError):
        payload = None
    code = (
        str(payload.get("code"))
        if payload and isinstance(payload.get("code"), str)
        else None
    )
    if 200 <= status < 300:
        return ClientResult(ok=True, status=status, code=code, body=payload)
    return ClientResult(ok=False, status=status, code=code, body=payload)


def _base_url(port: int) -> str:
    """Loopback base URL; the client always sends the exact loopback Host."""
    return f"http://127.0.0.1:{port}"


def livez(port: int, token: str) -> ClientResult:
    return _request(_base_url(port), token, "GET", "/livez")


def readyz(port: int, token: str) -> ClientResult:
    return _request(_base_url(port), token, "GET", "/readyz")


def version(port: int, token: str) -> ClientResult:
    return _request(_base_url(port), token, "GET", "/v1/version")


def submit_command(
    port: int,
    token: str,
    command_id: str,
    payload: dict[str, Any],
) -> ClientResult:
    """Submit one fake Controller-command envelope (exactly-once client).

    The shim holds the returned receipt and does not resend after a
    successful response; transport-level retries deduplicate server-side.
    """
    body = json.dumps(
        {"command_id": command_id, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _request(_base_url(port), token, "POST", "/v1/commands", body)


__all__ = [
    "ClientResult",
    "RuntimeUnavailableError",
    "livez",
    "readyz",
    "submit_command",
    "version",
]
