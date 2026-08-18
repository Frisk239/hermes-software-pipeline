---
status: accepted
---

# Authorize the contract toolchain only in the isolated Managed Runtime

**Status: accepted.** Repository owner authorized this cut on 2026-08-18 after an install smoke showed `KernelBridge` falling back because `jsonschema` is absent from `runtime-env`.

ADR-0026 keeps Pydantic, jsonschema, and rfc8785 out of the Hermes-loaded shim and out of root `[project].dependencies`. That stands.

The isolated Managed Runtime (`runtime-env/`, ADR-0028) may install the same three packages so `KernelBridge` can import `Actor`, `KernelController`, and RFC 8785 hashing. FastAPI and Uvicorn stay the HTTP surface. The shim, `--version`, and the Hermes process still must not import those packages.

A future move of this family into Hermes, the root runtime path, or a public service needs a new ADR.
