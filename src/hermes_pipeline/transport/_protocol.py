"""Loopback protocol validation and handlers (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE

The fixed loopback protocol as pure, framework-independent logic so the
full matrix is deterministically testable in the dev environment without
FastAPI/Uvicorn: Host must equal ``127.0.0.1:<port>`` or ``[::1]:<port>``
(else ``400`` + ``POLICY_REJECTED``); Origin must be absent or exactly the
matching loopback origin (else ``403`` + ``POLICY_REJECTED``); protocol
header ``X-Hermes-Pipeline-Protocol: 1`` is required (missing/unsupported
→ ``400`` + ``VALIDATION_ERROR``, fixed message ``unsupported protocol
version``); bearer token from the descriptor is required (bad/missing →
``401`` + ``AUTHENTICATION_FAILED``); body limit 64 KiB on
``/v1/commands`` (exceeded → ``413`` + ``VALIDATION_ERROR``); rate limit
one client window of 60 seconds with at most 60 requests (exceeded →
``429`` + ``RATE_LIMITED``); unknown path → ``404`` + ``NOT_FOUND``.
Responses never contain file paths, shell commands, SQL, raw exceptions,
or sensitive content.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from ._constants import (
    BODY_LIMIT_BYTES,
    CODE_AUTHENTICATION_FAILED,
    CODE_INTERNAL_ERROR,
    CODE_NOT_FOUND,
    CODE_POLICY_REJECTED,
    CODE_RATE_LIMITED,
    CODE_VALIDATION_ERROR,
    CONTRACT_SCHEMA_RANGE,
    PROTOCOL_VERSION,
    RATE_MAX_REQUESTS,
    RATE_WINDOW_SECONDS,
    RELEASE,
    RUNTIME_VERSION,
    UNSUPPORTED_PROTOCOL_MESSAGE,
)

# Loopback-only host/origin forms (the descriptor port).
_LOOPBACK_HOSTS = ("127.0.0.1", "[::1]")
_LOOPBACK_ORIGINS = ("http://127.0.0.1", "http://[::1]")

# Stable error body shape.
ERROR_BODY = dict[str, str]


@dataclass(frozen=True)
class RequestContext:
    """One parsed inbound request (framework-agnostic)."""

    method: str
    path: str
    host: str
    origin: str | None
    protocol_header: str | None
    authorization: str | None
    body: bytes
    now: int  # injected epoch seconds (deterministic clock)


@dataclass(frozen=True)
class Response:
    """One typed loopback response."""

    status: int
    body: dict[str, Any]


@dataclass
class FixedWindowRateLimiter:
    """One client fixed-window rate limiter (60 s / 60 requests)."""

    window_seconds: int = RATE_WINDOW_SECONDS
    max_requests: int = RATE_MAX_REQUESTS
    _window_start: int | None = field(default=None, init=False)
    _count: int = field(default=0, init=False)

    def allow(self, now: int) -> bool:
        if (
            self._window_start is None
            or now - self._window_start >= self.window_seconds
        ):
            self._window_start = now
            self._count = 0
        self._count += 1
        return self._count <= self.max_requests


class ReceiptStoreProtocol(Protocol):
    """Minimal receipt-store surface consumed by the protocol handlers."""

    def process(self, command_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class ServerState:
    """Runtime-side state injected into the protocol handlers."""

    token: str
    port: int
    receipt_store: ReceiptStoreProtocol
    rate_limiter: FixedWindowRateLimiter
    state_root_identity: str
    ready: bool = True
    runtime_version: str = RUNTIME_VERSION
    protocol_version: int = PROTOCOL_VERSION
    contract_schema_range: str = CONTRACT_SCHEMA_RANGE
    release: str = RELEASE
    clock: Callable[[], int] = field(default_factory=lambda: lambda: int(time.time()))


def _error_response(status: int, code: str, message: str) -> Response:
    return Response(status, {"code": code, "message": message})


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def validate_and_handle(ctx: RequestContext, state: ServerState) -> Response:
    """Validate the fixed protocol and dispatch one request.

    The validation order is fixed so every failure mode returns a stable
    typed code: Host → Origin → protocol → path → authentication → rate
    limit → body size → handler.
    """
    port = state.port
    # 1. Host header must be the exact loopback host with the descriptor port.
    host = ctx.host.strip()
    allowed_hosts = {f"{h}:{port}" for h in _LOOPBACK_HOSTS}
    if host not in allowed_hosts:
        return _error_response(400, CODE_POLICY_REJECTED, "untrusted Host header")
    # 2. Origin absent or exactly the matching loopback origin.
    if ctx.origin is not None:
        origin = ctx.origin.strip()
        allowed_origins = {f"{o}:{port}" for o in _LOOPBACK_ORIGINS}
        if origin not in allowed_origins:
            return _error_response(403, CODE_POLICY_REJECTED, "untrusted Origin header")
    # 3. Protocol version header.
    if ctx.protocol_header is None or ctx.protocol_header.strip() != str(
        PROTOCOL_VERSION
    ):
        return _error_response(400, CODE_VALIDATION_ERROR, UNSUPPORTED_PROTOCOL_MESSAGE)
    # 4. Known path.
    if ctx.path not in ("/livez", "/readyz", "/v1/version", "/v1/commands"):
        return _error_response(404, CODE_NOT_FOUND, "unknown path")
    # 5. Bearer token from the descriptor.
    token = _bearer_token(ctx.authorization)
    if token is None or token != state.token:
        return _error_response(401, CODE_AUTHENTICATION_FAILED, "authentication failed")
    # 6. Rate limit (one client window). Unversioned health probes
    #    (/livez, /readyz) are deliberately excluded: readiness polling
    #    must never consume the authenticated command budget.
    if ctx.path not in ("/livez", "/readyz"):
        now = ctx.now
        if not state.rate_limiter.allow(now):
            return _error_response(429, CODE_RATE_LIMITED, "rate limit exceeded")
    # 7. Body-size limit on /v1/commands.
    if ctx.path == "/v1/commands" and len(ctx.body) > BODY_LIMIT_BYTES:
        return _error_response(413, CODE_VALIDATION_ERROR, "request body too large")
    # Handler dispatch.
    try:
        if ctx.path == "/livez":
            return Response(200, {"status": "alive"})
        if ctx.path == "/readyz":
            return Response(
                200 if state.ready else 503,
                {
                    "ready": state.ready,
                    "status": "ready" if state.ready else "not-ready",
                },
            )
        if ctx.path == "/v1/version":
            return _handle_version(state)
        return _handle_command(ctx, state)
    except Exception:
        # Never leak raw exceptions across the HTTP surface.
        return _error_response(500, CODE_INTERNAL_ERROR, "internal error")


def _handle_version(state: ServerState) -> Response:
    return Response(
        200,
        {
            "runtime_version": state.runtime_version,
            "protocol_version": state.protocol_version,
            "contract_schema_range": state.contract_schema_range,
            "release": state.release,
            "state_root_identity": state.state_root_identity,
        },
    )


def _handle_command(ctx: RequestContext, state: ServerState) -> Response:
    if ctx.method != "POST":
        return _error_response(405, CODE_VALIDATION_ERROR, "method not allowed")
    try:
        envelope = json.loads(ctx.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _error_response(400, CODE_VALIDATION_ERROR, "invalid JSON body")
    if not isinstance(envelope, dict):
        return _error_response(400, CODE_VALIDATION_ERROR, "envelope must be an object")
    envelope = cast(dict[str, Any], envelope)
    command_id = envelope.get("command_id")
    payload = envelope.get("payload")
    if not isinstance(command_id, str) or not command_id:
        return _error_response(400, CODE_VALIDATION_ERROR, "command_id required")
    if not isinstance(payload, dict):
        return _error_response(400, CODE_VALIDATION_ERROR, "payload must be an object")
    receipt = state.receipt_store.process(command_id, cast(dict[str, Any], payload))
    return Response(202, {"receipt": receipt})


__all__ = [
    "FixedWindowRateLimiter",
    "RequestContext",
    "Response",
    "ServerState",
    "validate_and_handle",
]
