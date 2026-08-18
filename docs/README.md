# Documentation Map

## Repository entry points

- `README.md` — product promise, status, trust limits, and navigation.
- `LICENSE` — Apache License 2.0.
- `GOVERNANCE.md` — maintainer authority and delegation.
- `CONTRIBUTING.md` — contribution and review requirements.
- `SECURITY.md` — private vulnerability-reporting policy.
- `SUPPORT.md` — support scope and reporting information.
- `CODE_OF_CONDUCT.md` — participation and enforcement expectations.

## Normative after approval

- `CONTEXT.md` — ubiquitous language.
- `AGENTS.md` — repository constitution.
- `docs/adr/` — hard-to-reverse decisions; only entries marked `accepted` are binding.
- `docs/architecture/` — process, Module, Interface, and data-contract design.
- `docs/design/pipeline-state-machine.md` — production Pipeline state model.
- `docs/design/git-isolation-and-protection.md` — Git authority and isolation.
- `docs/security/` — threat model and trust boundaries.
- `docs/operations/` — configuration, lifecycle, observability, and recovery.
- `schemas/` — normative machine contracts.

## Engineering execution

- `docs/development/phase-and-slice-operating-model.md`;
- `docs/development/coding-and-test-standard.md`;
- `docs/development/ci-and-testing.md`;
- `docs/development/compatibility-targets.md`;
- `docs/agents/roles/` (default: `slice-owner.md`; planner/executor optional);
- `docs/roadmap/ROADMAP.md`;
- `docs/roadmap/TRACEABILITY.md`;
- `docs/roadmap/phase-00-foundation/`.

## Repository checks

- `.gitattributes` — cross-platform LF line-ending policy.
- `.gitignore` — ignored local content (`reference/`, `.venv/`, bytecode, tool caches); governed-file discovery honors it.
- `pyproject.toml` / `uv.lock` / `.python-version` — managed Python `>=3.12,<3.13` under uv 0.12.1 with the frozen development-tool resolution (Ruff, Pyright, pytest, pytest-asyncio, Hypothesis, plus the ADR-0026 dev-only contract toolchain: pydantic, jsonschema, rfc8785).
- `src/hermes_pipeline/` — the installable distribution `hermes-pipeline` 0.1.0 with the fixed Module package layout and the `hermes-pipeline-runtime` / `python -m hermes_pipeline.cli` entry points. `--version` is standalone; default repository checks (`contracts check`, `contracts drift-check`, `architecture check`) require a source checkout, while `architecture check --root <path>` accepts an explicit package root.
- `src/hermes_pipeline/contracts/` — the versioned Pydantic v2 authoring source (13 root contracts plus the `common/definitions` $defs library) that deterministically generates `schemas/`, `contracts/openapi.json`, and `contracts/compatibility-registry.json`; the toolchain is lazy-imported only after the `contracts` subcommand is parsed.
- `schemas/` — the 14 committed JSON Schema Draft 2020-12 documents generated from the authoring source (never hand-edited).
- `contracts/` — the generated OpenAPI 3.1.0 catalog (`openapi.json`) and the compatibility registry (`compatibility-registry.json`).
- `tests/fixtures/contracts/` — immutable f36 Schema snapshots with a raw-digest manifest, per-root-contract instance corpora (minimal, maximal, invalid, legacy, secret-canary), and RFC 8785 golden vectors used by the three-way corpus gate.
- `scripts/check_documentation.py` — dependency-free governed-text checker (UTF-8, replacement characters, Markdown fences, root-confined local links, ADR status, required root entry points; both workflow YAML files, read-only permissions, exact command/OS binding, and bundled-Node policy via `--check-workflows`; `.gitignore`-aware discovery).
- `scripts/check_schemas.py` — dependency-free bootstrap Schema integrity checker (JSON parsing, `$id` uniqueness and locked 14-Schema identity set, `$ref` and JSON Pointer resolution); the full validator keeps a consistency test aligned with it.
- `scripts/fixtures/` — positive and deliberately broken bootstrap fixtures for the checkers; `--self-test-negative` executes the checkers against them and asserts nonzero exits with sanitized bounded output.
- `scripts/check_repository_artifacts.py` — source-tree cache and bytecode audit run after verification.
- `.github/workflows/documentation-contracts.yml` — the same offline checks on Windows and Linux runners.
- `.github/workflows/python-quality.yml` — the frozen uv environment, bundled Pyright Node runtime, canonical quality checks (format, lint, type, unit, contract, contract drift, architecture, bootstrap checks, artifact audit), and offline sync/version/contract/architecture smokes on Windows and Linux.

## Supporting material

- `docs/research/` records dated evidence and may inform a decision but is not normative.
- `docs/design/design-review-roadmap.md` records review history and known gaps.
- ignored `reference/` clones are local research inputs and are never build dependencies.

When documents disagree, accepted ADRs and committed Schemas take precedence. For how this repository is developed, ADR-0031 and `AGENTS.md` win over longer process documents. Product architecture and security documents still bind product behavior. Pydantic authoring sources and their generated Schema/OpenAPI projections must be identical by construction. A conflict must be resolved in the documents; an Agent cannot choose silently.
