"""pre_gateway_dispatch hook behavior (slice-00-05, AC-09 dev side).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Probe-namespace events (``/card hermes_pipeline_fake_probe ...``) are
skipped unconditionally — including when the runtime is unreachable — with
a stable reason; non-probe events pass through untouched (None); the hook
never raises. The real Hermes gateway-dispatch probe lives in
tests/spike/probe/gateway.
"""

from __future__ import annotations

from types import SimpleNamespace

from hermes_shim._constants import PROBE_NAMESPACE_PREFIX
from hermes_shim._hook import (
    SKIP_REASON,
    pre_gateway_dispatch,
)

PROBE_JSON = '{"command_id": "cmd_probe_0001", "payload": {"op": "fake"}}'


def _event(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text, message_id="m1")


def test_probe_event_skipped_with_reason() -> None:
    result = pre_gateway_dispatch(
        _event(f"{PROBE_NAMESPACE_PREFIX} {PROBE_JSON}"), None, None
    )
    assert result == {"action": "skip", "reason": SKIP_REASON}


def test_probe_event_skipped_without_json_suffix() -> None:
    result = pre_gateway_dispatch(_event(PROBE_NAMESPACE_PREFIX), None, None)
    assert result == {"action": "skip", "reason": SKIP_REASON}


def test_probe_event_skipped_when_runtime_unreachable() -> None:
    """Skip must not depend on gateway or runtime state (unconditional)."""
    result = pre_gateway_dispatch(
        _event(f"{PROBE_NAMESPACE_PREFIX} {PROBE_JSON}"),
        gateway=object(),  # any broken/partial gateway object
        session_store=None,
    )
    assert result == {"action": "skip", "reason": SKIP_REASON}


def test_non_probe_card_event_passes_through() -> None:
    result = pre_gateway_dispatch(_event("/card other_tag {}}"), None, None)
    assert result is None


def test_plain_event_passes_through() -> None:
    result = pre_gateway_dispatch(_event("hello"), None, None)
    assert result is None


def test_non_string_text_passes_through() -> None:
    event = SimpleNamespace(text=None)
    assert pre_gateway_dispatch(event, None, None) is None
    event = SimpleNamespace(text=12345)
    assert pre_gateway_dispatch(event, None, None) is None


def test_hook_never_raises_on_broken_event() -> None:
    """A malformed event must never raise (Hermes fail-open risk)."""

    class _Broken:
        @property
        def text(self) -> str:
            raise RuntimeError("broken event")

    assert pre_gateway_dispatch(_Broken(), None, None) is None


def test_oversized_probe_event_still_skipped() -> None:
    """Skip is unconditional: an oversized probe event is still intercepted
    and can never fall through to Prod Main (identification is
    length-independent)."""
    event = _event(PROBE_NAMESPACE_PREFIX + "x" * 100_000)
    assert pre_gateway_dispatch(event, None, None) == {
        "action": "skip",
        "reason": SKIP_REASON,
    }


def test_probe_lookalike_identifier_passes_through() -> None:
    """Only the exact namespace is intercepted: a lookalike identifier
    such as ``hermes_pipeline_fake_probe_evil`` is not a probe event."""
    lookalike = "/card hermes_pipeline_fake_probe_evil {}"
    assert pre_gateway_dispatch(_event(lookalike), None, None) is None


def test_hook_signature_matches_hermes_call_site() -> None:
    """Hermes invokes the hook with event/gateway/session_store kwargs."""
    import inspect

    signature = inspect.signature(pre_gateway_dispatch)
    assert list(signature.parameters) == ["event", "gateway", "session_store"]
