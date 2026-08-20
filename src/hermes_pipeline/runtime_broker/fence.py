"""Fenced spawn helper for product runtime adapters.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

import threading

from hermes_pipeline.runtime_broker._process import BoundedResult, run_fenced


def spawn_fenced(
    argv: list[str],
    *,
    cwd: str,
    timeout_s: float,
    cancel: threading.Event,
) -> BoundedResult:
    return run_fenced(
        argv,
        cwd=cwd,
        timeout_s=timeout_s,
        output_bytes=1_048_576,
        cancel_event=cancel,
    )


def decode_out(result: BoundedResult) -> str:
    return result.stdout.decode("utf-8", errors="replace").strip()


__all__ = ["decode_out", "spawn_fenced"]
