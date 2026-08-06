---
status: accepted
---

# Restrict the contract toolchain to development dependencies

Slice 00-03 adopts `pydantic>=2,<3`, `jsonschema>=4,<5`, and `rfc8785==0.1.4` as a development/CI-only contract-toolchain dependency family, declared in the `dev` dependency group and frozen in `uv.lock`; `[project].dependencies` stays empty. Pydantic v2 remains the sole authoring source for versioned contracts under ADR-0024, and jsonschema plus the single RFC 8785 implementation back the committed Draft 2020-12 meta-validation, baseline-corpus verification, and canonical hashing. The toolchain is imported only after the `contracts` subcommand is parsed; the Hermes plugin entry, `--version`, and the normal runtime path remain pure standard library, and `contracts` returns a bounded error when development dependencies are absent. Any future runtime execution of Pydantic, jsonschema, or JCS inside the Hermes-loaded runtime requires a separate runtime-installation and isolation design ADR and Slice, consistent with the runtime-dependency rule in `docs/development/ci-and-testing.md`; this decision is human-accepted and does not authorize a runtime dependency.
