"""Bounded last-exit marker for the managed runtime.

DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

from pathlib import Path

_MAX = 40


def record_runtime_exit(root: Path, reason: str) -> None:
    token = reason.strip().split()[0] if reason.strip() else "unknown"
    text = "".join(ch for ch in token if ch.isalnum() or ch in "-_")[:_MAX]
    if not text:
        text = "unknown"
    path = root / "logs" / "last-exit.txt"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    except OSError:
        return


__all__ = ["record_runtime_exit"]
