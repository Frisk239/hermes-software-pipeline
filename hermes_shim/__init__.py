"""Hermes Software Pipeline shim package (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Standard-library and Hermes-guaranteed shim loaded inside the Hermes
process (ADR-0019). It registers the ``pipeline`` CLI command tree, the
``pre_gateway_dispatch`` hook, and one declared tool. It contains no
Controller logic, no Agent executor, no Git, no database, no network
beyond loopback, and no runtime-dependency import; it never imports
``src/hermes_pipeline`` (FastAPI/Uvicorn and the declared local package
live only inside the ADR-0028-authorized Managed Runtime).
"""

from __future__ import annotations

from ._cli import register as _register_cli
from ._hook import register as _register_hook
from ._tool import register as _register_tool


def register(ctx: object) -> None:
    """The plugin register(ctx) implementation (called exactly once)."""
    _register_cli(ctx)
    _register_hook(ctx)
    _register_tool(ctx)


__all__ = ["register"]
