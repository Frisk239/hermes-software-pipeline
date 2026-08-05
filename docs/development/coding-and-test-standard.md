# Coding and Test Standard

## Design

- Prefer deep Modules with small typed Interfaces.
- Domain code is pure and depends on no framework, database, process, provider, or model package.
- Dependency direction follows the architecture document; Adapters depend inward.
- Make invalid state unrepresentable where practical and validate at every trust boundary.
- Use explicit clocks, identity generators, canonicalizers, policy evaluators, and effect ports.
- Avoid shared mutable globals, ambient current directories, import-time I/O, and hidden retries.

## Python

- Python 3.12, full type annotations on public and internal Interfaces.
- Pydantic models exist at external serialization boundaries; domain values remain framework-independent.
- SQLAlchemy Core statements and explicit transactions are preferred over an active-record domain.
- Async is used for concurrent I/O orchestration, not to obscure pure state transitions.
- Exceptions do not cross Interface boundaries without translation to typed errors.
- Logs are structured; never interpolate secrets or entire untrusted payloads.

Ruff formatting and linting plus Pyright strictness are configured centrally in `pyproject.toml`. Per-file exemptions require a comment explaining the boundary and review approval.

## Tests

The test pyramid is:

1. pure domain examples and properties;
2. Module Interface contract tests;
3. persistence/replay/migration tests;
4. Adapter tests against recorded or local fakes;
5. process and Hermes integration tests;
6. a small set of Windows/Linux end-to-end scenarios;
7. quarantined live-Agent evaluations.

Tests must be deterministic by default. Freeze time, seed randomness, use allocated ports, isolate data roots, and never depend on developer credentials or internet access in required CI.

Each bug fix adds a failing regression test at the lowest boundary that proves the fault. Each migration tests upgrade from every supported source version and downgrade/rollback policy. Concurrency tests exercise duplicate delivery, stale revisions, stale leases, crash points, and replay.

## Coverage and mutation policy

Coverage is a diagnostic, not the acceptance oracle. Phase 0 sets an initial line/branch floor after the skeleton exists; safety-critical Controller, authorization, hashing, Git path, and migration Modules additionally require mutation-test sampling or equivalent adversarial evidence before public preview.

## Documentation

Behavior, Schema, configuration, migration, security, or operator changes update their normative docs and examples in the same Slice. `CONTEXT.md` changes only for domain vocabulary. ADRs capture hard-to-reverse decisions, not routine implementation details.

