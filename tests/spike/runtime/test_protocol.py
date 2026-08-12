"""Loopback protocol matrix (slice-00-05, AC-05/AC-10).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Deterministic framework-independent protocol matrix: Host/Origin strict
validation, protocol-version header, bearer authentication, 64 KiB body
limit, 60 s / 60-request fixed window, unknown-path 404, stable typed
codes, and no raw exception or sensitive content in any response. The
real FastAPI/Uvicorn surface is exercised end-to-end by the provision
harness tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hermes_pipeline.transport._protocol import (
    FixedWindowRateLimiter,
    RequestContext,
    ServerState,
    validate_and_handle,
)
from hermes_pipeline.transport._receipts import ReceiptStore

TOKEN = "t" * 64
PORT = 49152
NOW = 1_700_000_000


def _make_state(tmp_path: Path) -> ServerState:
    store = ReceiptStore(tmp_path)
    store.open()
    return ServerState(
        token=TOKEN,
        port=PORT,
        receipt_store=store,
        rate_limiter=FixedWindowRateLimiter(),
        state_root_identity="0" * 64,
        ready=True,
    )


def _ctx(
    *,
    method: str = "GET",
    path: str = "/livez",
    host: str | None = None,
    origin: str | None = None,
    protocol: str | None = "1",
    token: str | None = TOKEN,
    body: bytes = b"",
    now: int = NOW,
) -> RequestContext:
    host = host if host is not None else f"127.0.0.1:{PORT}"
    authorization = f"Bearer {token}" if token is not None else None
    return RequestContext(
        method=method,
        path=path,
        host=host,
        origin=origin,
        protocol_header=protocol,
        authorization=authorization,
        body=body,
        now=now,
    )


def test_livez_happy_path(tmp_path: Path) -> None:
    state = _make_state(tmp_path)
    response = validate_and_handle(_ctx(path="/livez"), state)
    assert response.status == 200
    assert response.body == {"status": "alive"}


def test_readyz_reports_ready(tmp_path: Path) -> None:
    state = _make_state(tmp_path)
    response = validate_and_handle(_ctx(path="/readyz"), state)
    assert response.status == 200
    assert response.body["ready"] is True


def test_version_reports_fixed_fields(tmp_path: Path) -> None:
    state = _make_state(tmp_path)
    response = validate_and_handle(_ctx(path="/v1/version"), state)
    assert response.status == 200
    assert response.body["protocol_version"] == 1
    assert response.body["runtime_version"] == "0.1.0"
    assert "contract_schema_range" in response.body
    assert "release" in response.body
    assert "state_root_identity" in response.body


def test_command_happy_path_returns_receipt(tmp_path: Path) -> None:
    state = _make_state(tmp_path)
    body = json.dumps({"command_id": "cmd_1", "payload": {"op": "fake"}}).encode()
    response = validate_and_handle(
        _ctx(method="POST", path="/v1/commands", body=body), state
    )
    assert response.status == 202
    receipt = response.body["receipt"]
    assert receipt["command_id"] == "cmd_1"
    assert receipt["deduplicated"] is False


def test_command_duplicate_dedups(tmp_path: Path) -> None:
    state = _make_state(tmp_path)
    body = json.dumps({"command_id": "cmd_2", "payload": {"op": "fake"}}).encode()
    first = validate_and_handle(
        _ctx(method="POST", path="/v1/commands", body=body), state
    )
    second = validate_and_handle(
        _ctx(method="POST", path="/v1/commands", body=body), state
    )
    assert first.status == second.status == 202
    # The duplicate returns the original receipt unchanged.
    assert second.body["receipt"] == first.body["receipt"]
    assert second.body["receipt"]["deduplicated"] is False
    assert (
        first.body["receipt"]["effect_count"]
        == second.body["receipt"]["effect_count"]
        == 1
    )


@pytest.mark.parametrize(
    ("name", "ctx_kwargs", "expected_status", "expected_code"),
    [
        ("bad-token", {"token": "deadbeef"}, 401, "AUTHENTICATION_FAILED"),
        ("missing-token", {"token": None}, 401, "AUTHENTICATION_FAILED"),
        ("wrong-protocol", {"protocol": "0"}, 400, "VALIDATION_ERROR"),
        ("missing-protocol", {"protocol": None}, 400, "VALIDATION_ERROR"),
        ("host-mismatch", {"host": "127.0.0.1:9999"}, 400, "POLICY_REJECTED"),
        ("host-wildcard", {"host": "0.0.0.0:49152"}, 400, "POLICY_REJECTED"),
        ("host-name", {"host": "localhost:49152"}, 400, "POLICY_REJECTED"),
        ("origin-mismatch", {"origin": "http://evil.example"}, 403, "POLICY_REJECTED"),
        (
            "origin-nonloopback",
            {"origin": "http://127.0.0.1:9999"},
            403,
            "POLICY_REJECTED",
        ),
        ("unknown-path", {"path": "/nope"}, 404, "NOT_FOUND"),
    ],
)
def test_fixed_failure_matrix(
    tmp_path: Path,
    name: str,
    ctx_kwargs: dict[str, Any],
    expected_status: int,
    expected_code: str,
) -> None:
    state = _make_state(tmp_path)
    response = validate_and_handle(_ctx(**ctx_kwargs), state)
    assert response.status == expected_status, name
    assert response.body["code"] == expected_code, name
    # No raw exception or sensitive content in any failure body.
    text = json.dumps(response.body).lower()
    assert "traceback" not in text
    assert "exception" not in text


def test_unsupported_protocol_fixed_message(tmp_path: Path) -> None:
    state = _make_state(tmp_path)
    response = validate_and_handle(_ctx(protocol="2"), state)
    assert response.status == 400
    assert response.body["code"] == "VALIDATION_ERROR"
    assert response.body["message"] == "unsupported protocol version"


def test_body_limit_exceeded_returns_413(tmp_path: Path) -> None:
    state = _make_state(tmp_path)
    body = json.dumps({"command_id": "big", "payload": {"pad": "x" * 70_000}}).encode()
    assert len(body) > 64 * 1024
    response = validate_and_handle(
        _ctx(method="POST", path="/v1/commands", body=body), state
    )
    assert response.status == 413
    assert response.body["code"] == "VALIDATION_ERROR"


def test_body_at_limit_accepted(tmp_path: Path) -> None:
    state = _make_state(tmp_path)
    payload = {"pad": "x" * (64 * 1024 - 200)}
    body = json.dumps({"command_id": "ok", "payload": payload}).encode()
    assert len(body) <= 64 * 1024
    response = validate_and_handle(
        _ctx(method="POST", path="/v1/commands", body=body), state
    )
    assert response.status == 202


def test_rate_limit_window_60_seconds_60_requests(tmp_path: Path) -> None:
    _make_state(tmp_path)
    limiter = FixedWindowRateLimiter(window_seconds=60, max_requests=60)
    allowed = 0
    for _ in range(61):
        if limiter.allow(NOW):
            allowed += 1
    assert allowed == 60
    # New window resets the count.
    assert limiter.allow(NOW + 60) is True


def test_rate_limit_exceeded_returns_429(tmp_path: Path) -> None:
    state = _make_state(tmp_path)
    for _ in range(60):
        validate_and_handle(_ctx(path="/v1/version"), state)
    response = validate_and_handle(_ctx(path="/v1/version"), state)
    assert response.status == 429
    assert response.body["code"] == "RATE_LIMITED"


def test_health_probes_exempt_from_rate_limit(tmp_path: Path) -> None:
    """Unversioned health probes never consume the command budget."""
    state = _make_state(tmp_path)
    for _ in range(200):
        response = validate_and_handle(_ctx(path="/livez"), state)
        assert response.status == 200
    response = validate_and_handle(
        _ctx(
            path="/v1/commands",
            method="POST",
            body=json.dumps({"command_id": "rl", "payload": {}}).encode(),
        ),
        state,
    )
    assert response.status == 202


def test_malformed_command_json_returns_validation_error(tmp_path: Path) -> None:
    state = _make_state(tmp_path)
    response = validate_and_handle(
        _ctx(method="POST", path="/v1/commands", body=b"{not json"), state
    )
    assert response.status == 400
    assert response.body["code"] == "VALIDATION_ERROR"


def test_missing_command_id_returns_validation_error(tmp_path: Path) -> None:
    state = _make_state(tmp_path)
    body = json.dumps({"payload": {"op": "fake"}}).encode()
    response = validate_and_handle(
        _ctx(method="POST", path="/v1/commands", body=body), state
    )
    assert response.status == 400
    assert response.body["code"] == "VALIDATION_ERROR"


def test_get_on_commands_rejected(tmp_path: Path) -> None:
    state = _make_state(tmp_path)
    response = validate_and_handle(_ctx(method="GET", path="/v1/commands"), state)
    del state
    assert response.status == 405
    assert response.body["code"] == "VALIDATION_ERROR"


def test_internal_error_never_leaks(tmp_path: Path) -> None:
    """A store failure must surface as a bounded internal error."""
    state = _make_state(tmp_path)

    def _broken(command_id: str, payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("raw internal failure")

    state.receipt_store.process = _broken  # type: ignore[method-assign]
    body = json.dumps({"command_id": "x", "payload": {}}).encode()
    response = validate_and_handle(
        _ctx(method="POST", path="/v1/commands", body=body), state
    )
    assert response.status == 500
    assert response.body["code"] == "INTERNAL_ERROR"
    assert "raw internal failure" not in json.dumps(response.body)


def test_ipv6_loopback_host_and_origin_accepted(tmp_path: Path) -> None:
    state = _make_state(tmp_path)
    response = validate_and_handle(
        _ctx(host=f"[::1]:{PORT}", origin=f"http://[::1]:{PORT}"), state
    )
    assert response.status == 200


def test_secret_canary_never_in_responses(tmp_path: Path) -> None:
    state = _make_state(tmp_path)
    state.token = "canary-secret-abc123"
    response = validate_and_handle(_ctx(token="wrong"), state)
    assert "canary-secret-abc123" not in json.dumps(response.body)
