---
status: accepted
---

# Authorize FastAPI and Uvicorn only in the isolated Managed Runtime

The Hermes-loaded plugin remains a thin, standard-library and Hermes-guaranteed Shim.  It must not import FastAPI, Uvicorn, or the repository's Pipeline Runtime package in the Hermes process.

For the Slice 00-05 feasibility spike, FastAPI, Uvicorn, and the declared local `hermes-pipeline==0.1.0` package are authorized only through the dedicated `runtime-env/` project and its committed `runtime-env/uv.lock`.  Provisioning creates the environment beneath the plugin state root at `<state-root>/runtimes/<version>/`, using a controlled `uv sync --frozen --project <repo>/runtime-env` invocation and `UV_PROJECT_ENVIRONMENT` for that state-root target.  The root project's `[project].dependencies` and root `uv.lock` remain unchanged.

The Shim launches the Managed Runtime as a separately interpreted process with a controlled argv array.  The runtime owns the authenticated loopback FastAPI/Uvicorn Control Interface defined by ADR-0022; it is never a public service and is not a substitute for a future production deployment design.  Dependency bootstrap is bounded to the declared provisioning step; later verification runs offline and use only the recorded lock.

Any future change that places these dependencies in Hermes, in the root runtime path, or in a production service requires a separate accepted ADR and Slice Contract.
