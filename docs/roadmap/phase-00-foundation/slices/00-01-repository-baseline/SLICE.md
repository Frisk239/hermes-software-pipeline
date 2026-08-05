# Slice 00-01 — Repository Baseline

Slice ID: `slice-00-01`

Phase: `phase-00`

Status: `DRAFT`

Document revision: `1`

Base SHA: `9a73b39f2eb1653e7345b27a39760cb55ef95af4`

Assigned Managed Worktree: pending Phase approval and Git Custodian assignment

## Operator path

Clone the exact repository baseline on Windows or Linux, locate every normative entry point, run the documentation and contract checks, and observe deterministic rejection of a broken Schema fixture.

## Must scope

- establish portable line-ending policy;
- add deterministic documentation and JSON Schema validation scripts;
- validate UTF-8, replacement characters, Markdown fences, local links, ADR status, Schema syntax, meta-schema, `$id`, `$ref`, and JSON Pointer resolution;
- add minimal positive and deliberately broken bootstrap fixtures for the checker itself;
- add Windows/Linux GitHub Actions for the offline documentation/contract checks;
- update baseline documentation only where required by the implemented checks;
- keep `README.md`, repository policies, documentation map, and readiness audit synchronized.

## Out of scope

- Python package/runtime skeleton, `pyproject.toml`, or `uv.lock`;
- Ruff, Pyright, pytest, Hypothesis, or application unit tests;
- Pydantic authoring models or generated-model drift;
- Hermes Shim, HTTP server, database, LangGraph, Agent, browser, Git mutation, or provider behavior;
- acceptance of Phase 00 or any later Slice.

## Interfaces and authority

This Slice changes no production Interface. It is bound by ADR-0024 for future Pydantic authoring and by the repository bootstrap rule. The Executor may edit only the paths named by the machine contract and may not commit, push, change Git configuration, or alter remotes.

## Acceptance criteria

| ID | Trace | Observable result | Verification |
| --- | --- | --- | --- |
| `AC-01` | `BOOT-01` | A clean clone exposes all required root entry points and every indexed local documentation link resolves. | `docs-check` |
| `AC-02` | `BOOT-02`, `XCON-01` | All 14 bootstrap Schemas parse, pass Draft 2020-12 validation, have unique `$id` values, and resolve every `$ref`/fragment through a standards-compliant registry. | `contracts-check` |
| `AC-03` | `BOOT-02` | A deliberately broken fixture is rejected with a stable nonzero exit and actionable bounded output. | `contracts-negative` |
| `AC-04` | `BOOT-03`, `XPLAT-01` | The same offline check commands run on required Windows and Linux GitHub Actions jobs. | `workflow-check`, CI evidence |
| `AC-05` | `XSEC-01` | Validation reads repository data only, performs no network access, executes no repository-provided shell string, and emits no secret or Project content. | design review and `scope-check` |
| `AC-06` | approved Slice scope | The Candidate changes no runtime/application path and contains no production behavior. | `scope-check` |

## Required evidence

- exact Base and Candidate SHAs;
- changed-path manifest;
- bounded output and exit code for every verification command;
- Windows and Linux CI job URLs/artifacts;
- positive and negative fixture results;
- explicit residual risks and bootstrap limitations.

## Risks and stop conditions

Stop and request a Contract Change if validation requires a new dependency family, network access, runtime code, a public Interface, a change to accepted ADR semantics, or paths outside the permitted set. Do not silently expand this Slice into the Python quality or contract-generation toolchain.

## Demonstration

From fresh Windows and Linux clones of the exact Candidate, run the documented offline commands successfully, then substitute the deliberately broken fixture and show deterministic rejection without modifying repository state.
