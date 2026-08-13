"""Hermes plugin entry for the Hermes Software Pipeline shim (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: ADOPTED_BY_00-07

This root module is loaded by the Hermes PluginManager as the plugin
package (``importlib.util.spec_from_file_location`` with the plugin
directory as the package path, so the relative import resolves inside the
Hermes process). It imports only the controlled root directory
``hermes_shim/`` (standard library and Hermes-guaranteed modules only,
ADR-0019) and never imports ``src/hermes_pipeline``; the managed runtime
dependencies (FastAPI/Uvicorn and the declared local ``hermes-pipeline``
package) live only inside the ADR-0028-authorized ``runtime-env/`` Managed
Runtime.

The absolute-import fallback exists only for non-Hermes import contexts
(e.g. pytest collecting this repository root as a plain package): it still
imports only ``hermes_shim`` and never ``src/hermes_pipeline``.
"""

try:
    from .hermes_shim import register
except Exception:  # pragma: no cover - Hermes-only relative import context
    import hermes_shim

    register = hermes_shim.register

__all__ = ["register"]
