"""Fenced spawn helper for product runtime adapters.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

import os
import threading

from hermes_pipeline.runtime_broker._process import BoundedResult, run_fenced
from hermes_pipeline.runtime_broker._redaction import child_environment

_DROP = frozenset({"GITHUB_TOKEN", "GH_TOKEN"})


def cleaned_child_env(base: dict[str, str] | None = None) -> dict[str, str]:
    source = dict(os.environ if base is None else base)
    allow = [key for key in source if key not in _DROP]
    return child_environment(source, allow=allow, canaries=())


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
        env=cleaned_child_env(),
        timeout_s=timeout_s,
        output_bytes=1_048_576,
        cancel_event=cancel,
    )


def decode_out(result: BoundedResult) -> str:
    return result.stdout.decode("utf-8", errors="replace").strip()


__all__ = ["cleaned_child_env", "decode_out", "spawn_fenced"]
