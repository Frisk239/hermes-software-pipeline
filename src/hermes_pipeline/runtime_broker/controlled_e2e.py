"""Standalone Host runner: controlled OpenCode + MCP E2E.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE
"""

from __future__ import annotations

import sys

from hermes_pipeline.runtime_broker._host import run_controlled_e2e


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Never pytest-collected."""
    return run_controlled_e2e(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
