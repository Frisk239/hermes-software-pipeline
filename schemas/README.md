# Generated Contract Schemas

Committed Schemas are the normative cross-language boundary artifacts. Versioned Pydantic 2 authoring types under `src/hermes_pipeline/contracts/` are their sole authoring source under ADR-0024 and ADR-0026; these files are generated deterministically and are never edited independently.

- `common/` contains reusable scalar and envelope definitions (the `$defs` type library).
- `engineering/` governs the repository's Codex-planned, Executor-implemented workflow.
- `runtime/` governs the installed production Pipeline.

All schemas use JSON Schema Draft 2020-12, reject unknown top-level fields, and carry a stable `$id`. The identity set of the 14 bootstrap Schemas is locked and unchanged since Slice 00-01.

## Authoring and drift

`contracts generate` is the only command that writes the generated projections; the toolchain is lazy-imported only after the `contracts` subcommand is parsed. `contracts drift-check` regenerates every projection into a temporary directory and byte-compares it with the committed files, so a hand edit, a timestamp, or a platform-dependent byte fails CI. `contracts check` runs the full read-only validator: the identity lock, Draft 2020-12 meta-validation, `$ref` closure, local RFC 3339 `FormatChecker` instance validation, the f36 baseline corpus three-way gate (immutable snapshots under `tests/fixtures/contracts/`, strict models, generated Schemas), OpenAPI and compatibility-registry checks, canonical hashes, and the canary scan.

```text
uv run python -m hermes_pipeline.cli contracts generate
uv run python -m hermes_pipeline.cli contracts check
uv run python -m hermes_pipeline.cli contracts drift-check
```

Slice 00-01 provides the dependency-free integrity gate `scripts/check_schemas.py`: JSON parsing, `$id` uniqueness, resolution of every local or absolute `$ref` and JSON Pointer fragment against the declared Schema registry, and an exact match of the declared `$id` set against the locked identity set of the 14 bootstrap Schemas, using only the Python standard library. It remains the untouched bootstrap gate; a consistency test keeps it aligned with the full validator.

The OpenAPI document at `contracts/openapi.json` is a fixed 3.1.0 contract catalog (Draft 2020-12 dialect, explicit empty `paths`, the fixed 14 component keys enumerated in the Slice contract) whose components fully embed the generated Schemas, and `contracts/compatibility-registry.json` records the finite supported version ranges per `$id`.
