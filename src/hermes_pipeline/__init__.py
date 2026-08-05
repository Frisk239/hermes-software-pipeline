"""hermes_pipeline — installed distribution for the Hermes Software Pipeline.

The package version is read from installed distribution metadata through
``importlib.metadata``; ``pyproject.toml`` is the sole version source
(Slice 00-02 interface contract). The distribution intentionally has no
runtime dependency: the plugin entry and every bootstrap check run on the
Python standard library (ADR-0020, ci-and-testing.md).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

try:
    __version__: str = _distribution_version("hermes-pipeline")
except PackageNotFoundError:  # pragma: no cover - uninstalled source import
    __version__ = "0.0.0+uninstalled"

__all__ = ["__version__"]
