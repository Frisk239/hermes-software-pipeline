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
- `docs/agents/roles/`;
- `docs/roadmap/ROADMAP.md`;
- `docs/roadmap/TRACEABILITY.md`;
- `docs/roadmap/phase-00-foundation/`.

## Repository checks

- `.gitattributes` — cross-platform LF line-ending policy.
- `.gitignore` — ignored local content (`reference/`, `.venv/`, bytecode, tool caches); governed-file discovery honors it.
- `pyproject.toml` / `uv.lock` / `.python-version` — managed Python `>=3.12,<3.13` under uv 0.12.1 with the frozen development-tool resolution (Ruff, Pyright, pytest, pytest-asyncio, Hypothesis).
- `src/hermes_pipeline/` — the installable distribution `hermes-pipeline` 0.1.0 with the fixed Module package layout and the `hermes-pipeline-runtime` / `python -m hermes_pipeline.cli` entry points (`--version`, `contracts check`, `architecture check`).
- `scripts/check_documentation.py` — dependency-free governed-text checker (UTF-8, replacement characters, Markdown fences, root-confined local links, ADR status, required root entry points; both workflow YAML files, read-only permissions, exact command/OS binding, and bundled-Node policy via `--check-workflows`; `.gitignore`-aware discovery).
- `scripts/check_schemas.py` — dependency-free Schema integrity checker (JSON parsing, `$id` uniqueness and locked 14-Schema identity set, `$ref` and JSON Pointer resolution).
- `scripts/fixtures/` — positive and deliberately broken bootstrap fixtures for the checkers; `--self-test-negative` executes the checkers against them and asserts nonzero exits with sanitized bounded output.
- `scripts/check_repository_artifacts.py` — source-tree cache and bytecode audit run after verification.
- `.github/workflows/documentation-contracts.yml` — the same offline checks on Windows and Linux runners.
- `.github/workflows/python-quality.yml` — the frozen uv environment, bundled Pyright Node runtime, canonical quality checks (format, lint, type, unit, contract, architecture, bootstrap checks, artifact audit), and offline sync/version/contract/architecture smokes on Windows and Linux.

## Supporting material

- `docs/research/` records dated evidence and may inform a decision but is not normative.
- `docs/design/design-review-roadmap.md` records review history and known gaps.
- ignored `reference/` clones are local research inputs and are never build dependencies.

When documents disagree, accepted ADRs and committed Schemas take precedence, followed by normative architecture/security documents, the approved Phase Plan, and then the immutable Slice Contract. Pydantic authoring sources and their generated Schema/OpenAPI projections must be identical by construction; any drift blocks dispatch rather than creating a new authority tier. A conflict must be resolved in the documents; an Agent cannot choose silently.
