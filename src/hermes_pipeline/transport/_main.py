"""Managed runtime entry (slice-00-05, launched by the Hermes shim).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE

``python -m hermes_pipeline.transport --state-root <path>`` starts the
fake managed runtime:

1. validates the state root and acquires the singleton lock (a second
   start on the same state root fails closed with
   ``DEPENDENCY_UNAVAILABLE`` and leaves no descriptor);
2. removes a stale descriptor only via the start-identity algorithm;
3. binds a fresh random loopback port (at most 3 attempts; after 3
   failures the runtime exits with ``DEPENDENCY_UNAVAILABLE`` and leaves
   no descriptor);
4. writes the descriptor atomically with owner-only ACL/mode (PID, start
   identity, creation time, port, token, token generation, release,
   state-root identity);
5. serves the authenticated loopback FastAPI/Uvicorn Control Interface.

Uvicorn is imported lazily (ADR-0028: framework packages exist only in the
isolated Managed Runtime). The runtime is disposable spike code; any
startup-step failure leaves the runtime not-ready.
"""

# pyright: basic
# pyright: ignore[reportMissingImports]
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ._constants import (
    CODE_DEPENDENCY_UNAVAILABLE,
    MAX_PORT_ATTEMPTS,
)
from ._descriptor import (
    build_descriptor,
    new_start_identity,
    new_token,
    read_descriptor,
    remove_descriptor_if_inside,
    write_descriptor,
)
from ._exitlog import record_runtime_exit
from ._identity import process_matches_identity, read_process_start_marker
from ._lock import StateRootLock, StateRootLockError
from ._protocol import FixedWindowRateLimiter, ServerState
from ._receipts import ReceiptStore
from ._state import (
    StateRootBoundaryError,
    ensure_inside_state_root,
    state_root_identity,
)

EXIT_OK = 0
EXIT_UNAVAILABLE = 1

# SPIKE-EXPERIMENTAL crash injection (documented disposition): when set,
# the runtime exits immediately after persisting a receipt and before the
# response is sent, exercising crash point B of the exactly-once matrix.
SPIKE_CRASH_AFTER_PERSIST = "SPIKE_CRASH_AFTER_PERSIST"

# SPIKE-EXPERIMENTAL port-collision injection (documented disposition):
# ``SPIKE_PORT_COLLISION_FIRST=<port>`` forces the first binding attempt to
# the given port (normally already held by the test), proving the bounded
# fresh-port retry path; ``SPIKE_FAIL_BIND=1`` makes every binding attempt
# fail, proving the exit with DEPENDENCY_UNAVAILABLE and no descriptor.
SPIKE_PORT_COLLISION_FIRST = "SPIKE_PORT_COLLISION_FIRST"
SPIKE_FAIL_BIND = "SPIKE_FAIL_BIND"


def _parse_argv(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m hermes_pipeline.transport",
        description="Fake managed runtime (slice-00-05 spike)",
    )
    parser.add_argument("--state-root", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="store_true")
    return parser.parse_args(argv)


def _emit_failure(code: str, message: str) -> None:
    # Bounded, redacted startup failure on stderr (no paths, no exceptions).
    print(
        json.dumps({"code": code, "message": message}, separators=(",", ":")),
        file=sys.stderr,
    )


def _remove_stale_descriptor(root: Path) -> None:
    document = read_descriptor(root)
    if document is None:
        return
    pid = int(document["pid"])
    marker = document.get("process_start_marker")
    if not process_matches_identity(pid, marker):
        # Removal is itself a write: the descriptor path must stay inside
        # the state root (an escaping symlink is never unlinked).
        remove_descriptor_if_inside(root)


def _probe_free_port() -> int:
    """Probe one fresh random loopback port (released before uvicorn binds).

    The probe-close-bind window is the standard TOCTOU trade-off of
    uvicorn's own port binding; a collision is handled by the bounded
    fresh-port retry loop in ``_serve``.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _serve(app: Any, state: ServerState, root: Path, token: str) -> int:
    """Serve the loopback app with bounded fresh-port retries.

    Each attempt probes a fresh random loopback port, binds the protocol
    state and the descriptor to that port, and lets uvicorn bind it. A
    binding collision (OSError) removes the descriptor and retries; after
    MAX_PORT_ATTEMPTS failures the runtime exits with
    DEPENDENCY_UNAVAILABLE and leaves no descriptor.
    """
    import uvicorn  # pyright: ignore[reportMissingImports] - managed runtime only

    for attempt in range(MAX_PORT_ATTEMPTS):
        if os.environ.get(SPIKE_FAIL_BIND) == "1":
            _remove_descriptor_now(root)
            continue
        port = _probe_free_port()
        forced = os.environ.get(SPIKE_PORT_COLLISION_FIRST)
        if attempt == 0 and forced:
            port = int(forced)
        state.port = port
        document = _descriptor_with_port(root, token, port)
        problems = write_descriptor(root, document)
        if problems:
            _remove_descriptor_now(root)
            _emit_failure(CODE_DEPENDENCY_UNAVAILABLE, "; ".join(problems))
            return EXIT_UNAVAILABLE
        try:
            uvicorn.run(
                app,
                host="127.0.0.1",
                port=port,
                log_level="warning",
                access_log=False,
            )
            return EXIT_OK
        except OSError:
            # Port collision (or an unserviceable bind): fresh attempt.
            _remove_descriptor_now(root)
            continue
        except SystemExit as exc:
            # uvicorn exits with code 3 when startup (socket bind) fails
            # instead of raising; treat that as a collision and retry. Any
            # other SystemExit is not ours and propagates.
            if exc.code != 3:
                raise
            _remove_descriptor_now(root)
            continue
    _emit_failure(CODE_DEPENDENCY_UNAVAILABLE, "port binding failed")
    return EXIT_UNAVAILABLE


def _remove_descriptor_now(root: Path) -> None:
    # Unlink is itself a write: never remove a descriptor whose path
    # escapes the state root (attacker-controlled symlink).
    remove_descriptor_if_inside(root)


def _descriptor_with_port(root: Path, token: str, port: int) -> dict[str, Any]:
    """One descriptor document bound to the current binding attempt."""
    marker = read_process_start_marker(os.getpid())
    return build_descriptor(
        pid=os.getpid(),
        start_identity=new_start_identity(),
        creation_time=datetime.now(UTC),
        process_start_marker=marker or {"value": "", "source": "unavailable"},
        port=port,
        token=token,
        token_generation=1,
        state_root_identity=state_root_identity(root),
    )


def _build_state(
    root: Path,
    port: int,
    token: str,
    ready: bool,
) -> ServerState:
    inner = ReceiptStore(root)
    inner.open()
    store: object = inner
    try:
        from hermes_pipeline.transport.kernel_bridge import KernelBridge

        store = KernelBridge(root, inner)
    except Exception:
        store = inner
    if os.environ.get(SPIKE_CRASH_AFTER_PERSIST) == "1":
        original_process = store.process

        def _crash_after_persist(
            command_id: str, payload: dict[str, Any]
        ) -> dict[str, Any]:
            original_process(command_id, payload)
            # Crash after persistence, before the response (crash point B).
            os._exit(42)

        store.process = _crash_after_persist  # type: ignore[method-assign]
    return ServerState(
        token=token,
        port=port,
        receipt_store=store,
        rate_limiter=FixedWindowRateLimiter(),
        state_root_identity=state_root_identity(root),
        ready=ready,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_argv(list(sys.argv[1:] if argv is None else argv))
    if args.version:
        from ._constants import RUNTIME_VERSION

        print(RUNTIME_VERSION)
        return EXIT_OK
    if not args.state_root:
        _emit_failure(CODE_DEPENDENCY_UNAVAILABLE, "state root required")
        return EXIT_UNAVAILABLE
    # Preserve the lexical state-root path until the no-follow boundary guard
    # has rejected a symlink, junction, or reparse-point root.  Calling
    # resolve() first would erase that evidence and permit an external write.
    root = Path(args.state_root)
    try:
        ensure_inside_state_root(root, root)
        root.mkdir(parents=True, exist_ok=True)
    except (OSError, StateRootBoundaryError):
        _emit_failure(CODE_DEPENDENCY_UNAVAILABLE, "state root unavailable")
        return EXIT_UNAVAILABLE

    try:
        lock = StateRootLock(root)
        lock.acquire()
    except StateRootLockError:
        _emit_failure(CODE_DEPENDENCY_UNAVAILABLE, "state root locked")
        return EXIT_UNAVAILABLE

    # Stale-descriptor cleanup via the start-identity algorithm only.
    _remove_stale_descriptor(root)

    token = new_token()
    marker = read_process_start_marker(os.getpid())
    if marker is None:
        lock.release()
        _emit_failure(CODE_DEPENDENCY_UNAVAILABLE, "identity unavailable")
        return EXIT_UNAVAILABLE

    import atexit

    finished = False

    def _on_exit() -> None:
        if not finished:
            record_runtime_exit(root, "atexit")

    def _on_exception(exc_type: Any, exc: Any, tb: Any) -> None:
        record_runtime_exit(root, getattr(exc_type, "__name__", "error"))
        sys.__excepthook__(exc_type, exc, tb)

    atexit.register(_on_exit)
    sys.excepthook = _on_exception
    state = _build_state(root, port=0, token=token, ready=True)
    from ._server import create_app

    app = create_app(state)
    code = _serve(app, state, root, token)
    finished = True
    record_runtime_exit(root, "serve-returned")
    lock.release()
    return code


if __name__ == "__main__":
    sys.exit(main())
