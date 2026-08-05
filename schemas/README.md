# Generated Contract Schemas

Committed Schemas are the normative cross-language boundary artifacts. Versioned Pydantic 2 models are their sole authoring source under ADR-0024; these files are generated deterministically and are never edited independently.

The files present before the initial repository commit are bootstrap contract candidates because the Pydantic toolchain does not yet exist. The Repository Governance Owner may approve them only as part of the non-behavioral documentation baseline. Slice 00-03 must adopt them into the Pydantic authoring source, regenerate byte-equivalent or explicitly versioned replacements, and establish the drift check before behavior-bearing Slice 00-04. After that adoption, direct edits are prohibited.

- `common/` contains reusable scalar and envelope definitions.
- `engineering/` governs the repository's Codex-planned, Executor-implemented workflow.
- `runtime/` governs the installed production Pipeline.

All schemas use JSON Schema Draft 2020-12, reject unknown top-level fields, and carry a stable `$id`. CI regenerates JSON Schema and OpenAPI from the Pydantic source and fails on any drift. Contract compatibility, examples, and invalid fixtures are reviewed with the source change.

Phase 0 must add minimal and maximal examples plus invalid fixtures for every schema before any behavior-bearing implementation consumes it.
