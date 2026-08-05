"""hermes_pipeline.cli — bootstrap command entry points (slice-00-02).

Exposes the canonical ``hermes-pipeline-runtime`` console script and the
``python -m hermes_pipeline.cli`` module entry. Version output, the
``contracts check`` Schema delegation, and the ``architecture check`` AST
gate live in sibling private modules so the public surface stays minimal.
"""

from __future__ import annotations

from ._main import main

__all__ = ["main"]
