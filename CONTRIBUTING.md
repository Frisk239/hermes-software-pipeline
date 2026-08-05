# Contributing

Hermes Software Pipeline is in its foundation phase. Contributions must preserve its deterministic authority, least-privilege execution, exact-source evidence, and recovery invariants.

## Before proposing a change

Read:

- `CONTEXT.md` for canonical domain language;
- `AGENTS.md` for binding repository rules;
- accepted ADRs relevant to the change;
- the owning architecture, security, operations, and development documents;
- the approved Phase Plan and current Slice Contract once they exist.

Open a discussion before preparing changes that alter product scope, architecture, security boundaries, dependency families, public Interfaces, migrations, destructive behavior, licensing, or governance. Such changes require human approval and usually an ADR or Contract Change Request.

## Change discipline

- Keep each change independently reviewable and revertible.
- Do not combine unrelated cleanup with behavior changes.
- Change versioned Pydantic contract sources before regenerating JSON Schema/OpenAPI artifacts.
- Do not independently edit generated contract artifacts.
- Add deterministic tests at the lowest boundary that proves the behavior.
- Update normative documentation, fixtures, compatibility notes, and runbooks with the behavior they govern.
- Never weaken, skip, delete, or mark tests merely to make a Candidate pass.
- Never include credentials, raw model transcripts, private Project content, or sensitive evidence.

## Development commands

The canonical command set will be introduced by Phase 00:

```text
uv sync --frozen --all-groups
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv run python -m hermes_pipeline.cli contracts check
uv run python -m hermes_pipeline.cli architecture check
```

Until the Phase 00 skeleton exists, a Slice Contract must state the exact bootstrap checks it introduces. A documentation-only change must at minimum validate UTF-8 decoding, local links, ADR status consistency, JSON parsing, and JSON Schema meta-schema/reference integrity.

## Pull requests

A pull request must state:

- the problem and observable result;
- the governing Slice Contract or approved maintenance authority;
- affected Interfaces, ADRs, Schemas, migrations, and security boundaries;
- exact verification commands and results;
- changed paths and generated artifacts;
- residual risks, deferred work, and rollback approach.

Review binds to exact Git object identities. A branch name, chat summary, screenshot, or mutable file path is not sufficient evidence.

## Commit and remote authority

Agent Executors do not commit, push, merge, rebase, reset, clean, modify hooks/remotes/config, or hold Git/provider credentials. The trusted Git Custodian and protected GitHub workflow own Candidate creation and remote delivery.

## License

Unless explicitly marked otherwise, intentional contributions submitted for inclusion are licensed under Apache License 2.0 as described by the repository `LICENSE`.
