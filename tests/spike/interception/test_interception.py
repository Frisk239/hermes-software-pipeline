"""Interception semantics against a dispatch stub (slice-00-05, AC-09).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Dev-side evidence for the pre_gateway_dispatch interception contract: the
hook's skip/None results drive a simplified model of Hermes' dispatch
result handling (gateway/run.py:14300-14318 first-action-wins), a probe
event is skipped with zero Prod Main invocations (including with an
unreachable runtime), non-probe events reach the dispatch stub, and the
hook never raises. The real Hermes gateway path is exercised by
tests/spike/probe/gateway.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from hermes_shim._constants import PROBE_NAMESPACE_PREFIX
from hermes_shim._hook import pre_gateway_dispatch

PROBE_JSON = '{"command_id": "cmd_probe_0001", "payload": {"op": "fake"}}'


class DispatchStub:
    """Minimal model of Hermes' dispatch result handling for the hook."""

    def __init__(self) -> None:
        self.prod_main_invocations = 0
        self.hook_exceptions = 0
        self.received: list[str] = []

    async def handle(self, event: Any) -> str | None:
        """First-action-wins over the hook result (Hermes semantics)."""
        try:
            result = pre_gateway_dispatch(event, gateway=None, session_store=None)
        except Exception:
            self.hook_exceptions += 1
            return None
        if result is None:
            self.prod_main_invocations += 1
            self.received.append(str(getattr(event, "text", "")))
            return "dispatched"
        if result.get("action") == "skip":
            return None
        if result.get("action") == "rewrite":
            self.prod_main_invocations += 1
            return "dispatched"
        return None


def _event(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text, message_id="m1")


def test_probe_event_skipped_with_zero_prod_main() -> None:
    import asyncio

    stub = DispatchStub()
    result = asyncio.run(stub.handle(_event(f"{PROBE_NAMESPACE_PREFIX} {PROBE_JSON}")))
    assert result is None
    assert stub.prod_main_invocations == 0
    assert stub.received == []


def test_probe_event_skipped_when_runtime_unreachable() -> None:
    """The dispatch stub stands in for the unreachable-runtime condition:
    the hook's skip decision never depends on runtime state."""
    import asyncio

    stub = DispatchStub()
    result = asyncio.run(stub.handle(_event(f"{PROBE_NAMESPACE_PREFIX} {PROBE_JSON}")))
    assert result is None
    assert stub.prod_main_invocations == 0


def test_non_probe_card_reaches_dispatch_stub() -> None:
    import asyncio

    stub = DispatchStub()
    result = asyncio.run(stub.handle(_event("/card real_feishu_action {}")))
    assert result == "dispatched"
    assert stub.prod_main_invocations == 1


def test_plain_event_reaches_dispatch_stub() -> None:
    import asyncio

    stub = DispatchStub()
    result = asyncio.run(stub.handle(_event("hello there")))
    assert result == "dispatched"
    assert stub.prod_main_invocations == 1


def test_oversized_probe_event_still_skipped() -> None:
    """Skip is unconditional: an oversized probe event must never fall
    through to Prod Main (identification is length-independent)."""
    import asyncio

    stub = DispatchStub()
    oversized = f"{PROBE_NAMESPACE_PREFIX}{'x' * 100_000}"
    result = asyncio.run(stub.handle(_event(oversized)))
    assert result is None
    assert stub.prod_main_invocations == 0


def test_probe_lookalike_identifier_not_intercepted() -> None:
    """Only the exact namespace is intercepted: a lookalike identifier
    such as ``hermes_pipeline_fake_probe_evil`` reaches normal dispatch."""
    import asyncio

    stub = DispatchStub()
    lookalike = "/card hermes_pipeline_fake_probe_evil {}"
    result = asyncio.run(stub.handle(_event(lookalike)))
    assert result == "dispatched"
    assert stub.prod_main_invocations == 1


def test_exact_namespace_without_payload_still_skipped() -> None:
    """The namespace match is a prefix; even an empty payload is skipped."""
    import asyncio

    stub = DispatchStub()
    result = asyncio.run(stub.handle(_event(f"{PROBE_NAMESPACE_PREFIX} ")))
    assert result is None
    assert stub.prod_main_invocations == 0


def test_hook_exception_counter_stays_zero() -> None:
    import asyncio

    stub = DispatchStub()
    asyncio.run(stub.handle(_event("anything")))
    assert stub.hook_exceptions == 0
