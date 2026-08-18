"""pre_gateway_dispatch hook for the Hermes Shim (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: ADOPTED_BY_00-07

The hook fires once per incoming user-originated MessageEvent before auth
and agent dispatch. Contract-pinned semantics:

- the callback never raises;
- any event whose text belongs to the shim's fake-probe namespace
  (``/card hermes_pipeline_fake_probe ...``) is answered with
  ``{"action": "skip", "reason": ...}`` **unconditionally** — including
  when the runtime is unreachable — so a probe event can never fall
  through to Prod Main;
- all other events are left untouched (``None``);
- no other /card or plain event is intercepted.
"""

from __future__ import annotations

import hashlib
from typing import Any

from ._constants import INTAKE_NAMESPACE_PREFIX, PROBE_NAMESPACE_PREFIX

# Stable, bounded skip reason (never includes event content).
SKIP_REASON = "hermes-pipeline fake probe intercepted"
INTAKE_SKIP_REASON = "hermes-pipeline intake intercepted"


def pre_gateway_dispatch(
    event: Any,
    gateway: Any = None,
    session_store: Any = None,
) -> dict[str, str] | None:
    """Intercept probe-namespace events; never raises; never touches others.

    ``gateway`` and ``session_store`` are accepted for Hermes' hook
    signature but are deliberately unused: the probe decision must not
    depend on gateway state, so skip works identically when the runtime is
    unreachable.

    Identification is exact (``PROBE_NAMESPACE_PREFIX`` ends in a space,
    so a lookalike identifier cannot match) and independent of event
    length: an oversized probe event is still skipped unconditionally and
    can never fall through to Prod Main. Every other event returns None.
    """
    del gateway, session_store
    try:
        text = getattr(event, "text", None)
        if not isinstance(text, str):
            return None
        if text.startswith(PROBE_NAMESPACE_PREFIX):
            _submit_probe_command(event)
            return {"action": "skip", "reason": SKIP_REASON}
        if text.startswith(INTAKE_NAMESPACE_PREFIX):
            _submit_intake_command(event, text)
            return {"action": "skip", "reason": INTAKE_SKIP_REASON}
        return None
    except Exception:
        # Defensive: a hook that raises would let Hermes fail open and
        # forward the event to normal dispatch. Never raise.
        return None


def _submit_probe_command(event: Any) -> None:
    """Submit one authenticated loopback fake command (best effort)."""
    try:
        from . import _client
        from ._descriptor import is_stale, read_descriptor
        from ._state import hermes_home, state_root

        root = state_root(hermes_home())
        document = read_descriptor(root)
        if document is None or is_stale(root):
            return
        message_id = str(getattr(event, "message_id", "")) or "probe"
        command_id = (
            "probe_" + hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:16]
        )
        _client.submit_command(
            int(document["port"]),
            str(document["token"]),
            command_id,
            {"op": "fake-probe"},
        )
    except Exception:
        return


def _submit_intake_command(event: Any, text: str) -> None:
    try:
        import json

        from . import _client
        from ._descriptor import is_stale, read_descriptor
        from ._state import hermes_home, state_root

        raw = text[len(INTAKE_NAMESPACE_PREFIX) :].strip()
        payload: dict[str, Any] = {}
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
        body_text = payload.get("text")
        if not isinstance(body_text, str):
            return
        root = state_root(hermes_home())
        document = read_descriptor(root)
        if document is None or is_stale(root):
            return
        message_id = str(getattr(event, "message_id", "")) or "intake"
        command_id = str(payload.get("command_id") or "")
        if not command_id.startswith("cmd_"):
            command_id = (
                "cmd_hook_"
                + hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:16]
            )
        _client.submit_command(
            int(document["port"]),
            str(document["token"]),
            command_id,
            {
                "text": body_text,
                "workspace_id": str(payload.get("workspace_id", "ws_local")),
                "project_id": str(payload.get("project_id", "prj_local")),
                "pipeline_id": str(payload.get("pipeline_id", "pl_local")),
                "principal_id": str(payload.get("principal_id", "operator")),
            },
        )
    except Exception:
        return


def register(ctx: object) -> None:
    """Register the hook on a Hermes PluginContext."""
    ctx.register_hook("pre_gateway_dispatch", pre_gateway_dispatch)


__all__ = ["pre_gateway_dispatch", "register"]
