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
- `scripts/check_documentation.py` — dependency-free governed-text checker (UTF-8, replacement characters, Markdown fences, root-confined local links, ADR status, required root entry points; workflow YAML syntax, read-only permissions, exact command/OS binding via `--check-workflow`).
- `scripts/check_schemas.py` — dependency-free Schema integrity checker (JSON parsing, `$id` uniqueness and locked 14-Schema identity set, `$ref` and JSON Pointer resolution).
- `scripts/fixtures/` — positive and deliberately broken bootstrap fixtures for the checkers; `--self-test-negative` executes the checkers against them and asserts nonzero exits with sanitized bounded output.
- `.github/workflows/documentation-contracts.yml` — the same offline checks on Windows and Linux runners.

## Supporting material

- `docs/research/` records dated evidence and may inform a decision but is not normative.
- `docs/design/design-review-roadmap.md` records review history and known gaps.
- ignored `reference/` clones are local research inputs and are never build dependencies.

When documents disagree, accepted ADRs and committed Schemas take precedence, followed by normative architecture/security documents, the approved Phase Plan, and then the immutable Slice Contract. Pydantic authoring sources and their generated Schema/OpenAPI projections must be identical by construction; any drift blocks dispatch rather than creating a new authority tier. A conflict must be resolved in the documents; an Agent cannot choose silently.
