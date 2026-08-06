# Slice 00-02 Closeout — Python Quality Skeleton

Status: `ACCEPTED`

Contract revision: `4`

Base SHA: `6c9623a3a8ad6a124d5d4a1bcddce94a5938e0b4`

Candidate SHA: `0d521365476602cdb0f5bcfc9c8ae0bdb0bee4f9`

Integrated SHA: `f36ba6a2930267e2d90682ff61930c82fd1237bb`

Pull Request: [#4 — ci: add managed python quality skeleton (slice-00-02)](https://github.com/Frisk239/hermes-software-pipeline/pull/4)

Closed: 2026-08-05

## Accepted capability

- `pyproject.toml`, a committed cross-platform `uv.lock`, `.python-version`, and the installable `src/hermes_pipeline` package skeleton exist, with Python `>=3.12,<3.13` and `uv 0.12.1` as the managed bootstrap targets;
- the distribution is `hermes-pipeline` / `hermes_pipeline` with zero runtime dependencies; `--version`, installed metadata, and `hermes_pipeline.__version__` all report `0.1.0` from the single metadata source;
- Ruff, Pyright (locked `nodejs` extra, ambient Node forbidden), pytest, pytest-asyncio, and Hypothesis are configured centrally and frozen in `uv.lock`;
- deterministic UTC clock, identity-sequence, temporary-root, async, and Hypothesis fixtures live in `tests/conftest.py` and `tests/facilities.py`; the final verification suppresses bytecode and audits repository artifacts;
- the standard-library AST architecture checker enforces the accepted inward dependency direction with positive and deliberately invalid import fixtures;
- `contracts check` and `architecture check` are bootstrap CLI commands; `contracts check` delegates in-process to the Slice 00-01 bootstrap Schema checker with no second validation implementation and no shell execution;
- repository-root documentation discovery honors ignored `reference/`, `.venv`, and tool-cache content while still checking governed unignored files, with positive and negative regression fixtures;
- the read-only `python-quality.yml` workflow runs the canonical checks offline on Windows and Linux, persists no checkout credential, consumes no secret, and leaves no cache or bytecode artifact behind.

## Evidence

- Candidate push CI run [31009120142](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/31009120142) (`python-quality`, Ubuntu and Windows jobs `success`);
- Candidate push CI run [31009120942](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/31009120942) (`documentation-contracts`, Ubuntu and Windows jobs `success`);
- Pull Request CI run [31009123469](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/31009123469) (`python-quality`, Ubuntu and Windows jobs `success`);
- Pull Request CI run [31009123473](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/31009123473) (`documentation-contracts`, Ubuntu and Windows jobs `success`);
- all four runs bind to the exact Candidate `0d521365476602cdb0f5bcfc9c8ae0bdb0bee4f9`, giving two required workflows × two required operating systems, all green;
- the Candidate changed exactly 45 permitted paths, introduced no runtime dependency, no HTTP, persistence, LangGraph, Shim, Agent, browser, or provider behavior, and left the committed `uv.lock` digest bound to the run evidence;
- PR #4 merged to `main` as `f36ba6a2930267e2d90682ff61930c82fd1237bb` on 2026-08-05; the merge commit's second parent is the Candidate.

## Residual debt

- `contracts check` and `architecture check` locate the source checkout by probing for `scripts/check_schemas.py` and `src/hermes_pipeline`; the default commands therefore require a source checkout, and a standalone wheel environment supports only `--version` outside a checkout;
- the final local artifact audit inherits `PYTHONDONTWRITEBYTECODE=1` from the CI job environment (`python-quality.yml`); local reproductions must export the same variable so bytecode suppression and the artifact scan match CI;
- `scripts/check_schemas.py` intentionally remains the dependency-free Slice 00-01 bootstrap gate with its locked 14-Schema identity set; it is not yet a full Draft 2020-12 meta-schema validator;
- Pydantic authoring adoption, generated Schema/OpenAPI drift, RFC 8785 canonical hashing, compatibility fixtures and registry, and secret-canary redaction coverage remain owned by Slice 00-03;
- the `scripts/check_documentation.py` workflow parser still accepts only the strict YAML subset of the committed workflows;
- OS-level network capability enforcement remains owned by Slice 00-06.

## Next prerequisites

- Slice 00-03 uses integrated SHA `f36ba6a2930267e2d90682ff61930c82fd1237bb` as its implementation Base;
- the planning worktree for Slice 00-03 is created clean from that Base SHA by the Git Custodian on branch `docs/slice-00-03-planning`;
- the accepted Slice 00-01 and 00-02 Candidate, PR, and Closeout evidence is durable; their managed worktrees may be removed, and the Git Custodian creates a new clean Slice 00-03 planning/implementation worktree from the exact Base SHA;
- the frozen environment remains credential-free and offline after the single dependency-install step; Slice 00-03 adds Pydantic, jsonschema, and RFC 8785 to the development dependency group only, keeping `[project].dependencies` empty per `ci-and-testing.md` runtime-dependency rules;
- required checks continue to run identically on Windows and Linux.

## Handover to Slice 00-03

- **Pydantic authoring** — the 14 bootstrap Schemas become generated outputs of versioned Pydantic v2 models under `src/hermes_pipeline/contracts/`; `$id` identities and strict unknown-field semantics (`extra="forbid"`) must be preserved;
- **Schema/OpenAPI drift** — deterministic generation and committed JSON Schema Draft 2020-12 plus OpenAPI projections, with a CI drift check;
- **Compatibility** — minimal/maximal/legacy-version fixtures per Schema and a finite compatibility-range registry with a pure migration Interface;
- **RFC 8785** — canonical JSON, `content_hash` field-exclusion rules, and UTF-8 SHA-256 golden vectors;
- **Fixtures and redaction** — per-Schema valid/invalid/legacy/secret-canary fixtures and proof that canaries never reach errors, logs, Events, or reports.
