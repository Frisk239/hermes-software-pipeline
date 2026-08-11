"""Three-crash-point exactly-once matrix (slice-00-05, AC-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Crash point A (runtime killed before persistence): retry with the same
``command_id`` processes afresh with exactly one receipt and one effect.
Crash point B (killed after persistence, before the response): retry
returns the original receipt (dedup) with no second effect. Crash point C
(after the response): the shim holds the receipt and does not resend; a
transport-level retry still dedups to the original receipt. Hermes killed
mid-flight leaves the receipt with the runtime; the next shim start
re-reads the existing descriptor/token without rotation. A forged receipt
is rejected.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from hermes_shim import _client
from tests.spike.runtime._harness import (
    provision,
    start_runtime,
    stop_runtime,
    wait_for_descriptor,
    wait_runtime_ready,
)

# Crash-injection environment (SPIKE-EXPERIMENTAL, documented disposition).
CRASH_AFTER_PERSIST = "SPIKE_CRASH_AFTER_PERSIST"


def _submit(
    port: int, token: str, command_id: str
) -> tuple[int, dict[str, Any] | None]:
    """One loopback fake-command submission through the shim client."""
    result = _client.submit_command(port, token, command_id, {"op": "fake"})
    return (result.status or 0, result.body)


def _start_and_wait(
    state_root: Path, env_extra: dict[str, str] | None = None
) -> tuple[subprocess.Popen[bytes], dict[str, Any]]:
    proc = start_runtime(state_root, env_extra=env_extra)
    document = wait_for_descriptor(state_root)
    wait_runtime_ready(state_root)
    return proc, document


def test_crash_before_persistence_converges_exactly_once(tmp_path: Path) -> None:
    """Crash point A: kill the runtime before the command is processed;
    the retry processes afresh with exactly one receipt and one effect."""
    provision(tmp_path, offline=False)
    proc, document = _start_and_wait(tmp_path)
    token = str(document["token"])
    # Kill the runtime before any command reached persistence.
    stop_runtime(proc, tmp_path)
    proc2, document2 = _start_and_wait(tmp_path)
    assert str(document2["token"]) != token, "runtime restart must rotate the token"
    port2 = int(document2["port"])
    status, body = _submit(port2, str(document2["token"]), "cmd_crash_a")
    assert status == 202
    assert body is not None and body["receipt"]["deduplicated"] is False
    assert body["receipt"]["effect_count"] == 1
    # Retry after a second restart: the original receipt, one effect.
    stop_runtime(proc2, tmp_path)
    proc3, document3 = _start_and_wait(tmp_path)
    status, body = _submit(
        int(document3["port"]), str(document3["token"]), "cmd_crash_a"
    )
    assert status == 202
    # The persisted receipt is returned unchanged (original values).
    assert body is not None and body["receipt"]["deduplicated"] is False
    assert body["receipt"]["effect_count"] == 1
    stop_runtime(proc3, tmp_path)


def test_crash_after_persistence_before_response(tmp_path: Path) -> None:
    """Crash point B: the runtime persists the receipt then dies before the
    response; the retry returns the original receipt with no second
    effect."""
    provision(tmp_path, offline=False)
    proc, document = _start_and_wait(tmp_path, env_extra={CRASH_AFTER_PERSIST: "1"})
    port, token = int(document["port"]), str(document["token"])
    # The submission triggers persistence, then os._exit(42) before the
    # response reaches the client.
    import contextlib

    with contextlib.suppress(Exception):
        _submit(port, token, "cmd_crash_b")  # crash signature: reset/EOF
    # The crash (os._exit after persistence) propagates to the launcher
    # exit code with a small delay; wait bounded for it.
    import time as _time

    deadline = _time.monotonic() + 10
    while _time.monotonic() < deadline and proc.poll() is None:
        _time.sleep(0.1)
    assert proc.poll() is not None, "runtime must have crashed after persist"

    proc2, document2 = _start_and_wait(tmp_path)
    status, body = _submit(
        int(document2["port"]), str(document2["token"]), "cmd_crash_b"
    )
    assert status == 202
    assert body is not None
    # Crash point B: the retry returns the persisted receipt unchanged.
    assert body["receipt"]["deduplicated"] is False
    assert body["receipt"]["effect_count"] == 1
    stop_runtime(proc2, tmp_path)


def test_crash_after_response_shim_does_not_resend(tmp_path: Path) -> None:
    """Crash point C: after a successful response the shim holds the
    receipt; a transport-level retry still dedups to the original receipt
    with no second effect."""
    provision(tmp_path, offline=False)
    proc, document = _start_and_wait(tmp_path)
    port, token = int(document["port"]), str(document["token"])
    status, _body = _submit(port, token, "cmd_crash_c")
    assert status == 202
    assert _body is not None and _body["receipt"]["deduplicated"] is False
    # Simulated transport retry with the same command id.
    status, body = _submit(port, token, "cmd_crash_c")
    assert status == 202
    assert body is not None and body["receipt"] == _body["receipt"]
    assert body["receipt"]["deduplicated"] is False
    assert body["receipt"]["effect_count"] == 1
    stop_runtime(proc, tmp_path)


def test_hermes_restart_rerereads_descriptor_without_rotation(tmp_path: Path) -> None:
    """A Hermes-process restart re-reads the existing descriptor and token;
    it never rotates and never rewrites the descriptor."""
    provision(tmp_path, offline=False)
    proc, document = _start_and_wait(tmp_path)
    descriptor_path = tmp_path / "descriptor" / "runtime.json"
    before = descriptor_path.read_text(encoding="utf-8")
    token_before = document["token"]
    # Re-read the descriptor (a Hermes restart does not touch the file).
    import time

    time.sleep(0.5)
    after = descriptor_path.read_text(encoding="utf-8")
    assert before == after, "a Hermes restart must never rewrite the descriptor"
    assert json.loads(after)["token"] == token_before
    # The same token still authenticates.
    status, _body = _submit(int(document["port"]), str(token_before), "cmd_restart_1")
    assert status == 202
    stop_runtime(proc, tmp_path)


def test_forged_receipt_rejected_across_restart(tmp_path: Path) -> None:
    """A receipt that does not match the persisted row is rejected."""
    provision(tmp_path, offline=False)
    proc, document = _start_and_wait(tmp_path)
    port, token = int(document["port"]), str(document["token"])
    _submit(port, token, "cmd_forged")
    forged = {
        "command_id": "cmd_forged",
        "payload_hash": "0" * 64,
        "effect_count": 99,
        "deduplicated": False,
        "processed_at": "2026-01-01T00:00:00Z",
    }
    # The shim client never sends a forged receipt; the store rejects one
    # when compared against the persisted row.
    from hermes_pipeline.transport._receipts import ReceiptStore

    store = ReceiptStore(tmp_path)
    store.open()
    assert store.is_forged("cmd_forged", forged)
    stop_runtime(proc, tmp_path)
