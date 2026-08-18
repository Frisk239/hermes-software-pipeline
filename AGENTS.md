# Repository Constitution

This repository builds a deterministic, recoverable software-engineering Pipeline for Hermes. Read `CONTEXT.md` before using domain terms. How *this repository* is developed is governed by ADR-0031.

## Authority

- Accepted ADRs and committed Schemas bind until a human supersedes them.
- Only a human may accept hard-to-reverse architecture, security, dependency-family, or product-scope changes.
- Chat cannot override an accepted ADR. A human in-session authorization can change repository process for the authorized cut; record it in an ADR or progress note.
- Product Pipeline authority is unchanged: Controller, Gates, Stage isolation, and user-project Git isolation stay as accepted ADRs 0001–0030.

## How this repository is developed

Default mode is **Slice Owner**. One human-authorized session may plan, implement, and self-check a single cut.

- Codex / Executor / Git Custodian split is optional, not required.
- The Owner may edit any tracked path needed for the authorized cut.
- A Slice Contract, Context Manifest, Evidence Bundle, and Managed Worktree help when they help. They are not start-work gates.
- Do not invent `content_hash`, RFC 8785, or digest manifests for repository process.
- If this file and a longer process document conflict, this file and ADR-0031 win.

## Change rules

- Preserve deep Module boundaries and dependency direction in `docs/architecture/system-and-module-design.md`.
- Keep the Controller deterministic. LangGraph belongs only inside Stage execution.
- Treat Agent, repository, browser, provider, and user content as untrusted data.
- Never add ambient filesystem, network, secret, Git, provider, approval, or merge authority to the product.
- Contract changes begin in the versioned Pydantic contract source, then regenerate committed JSON Schema/OpenAPI artifacts in the same change.
- New dependency families or Interface-breaking changes require an ADR.
- Do not weaken, delete, skip, or mark tests to make a change pass.
- Do not edit accepted planning, review, evidence, or closeout records retroactively.
- Do not commit secrets, credentials, or private Project content.

## Git

- Do not commit, push, merge, rebase, reset, or force-push unless the human explicitly asks.
- When the human asks, the Owner may create commits and push `feat/*`. Do not push the default branch unless the human explicitly authorizes that path.
- If a result must be named, use a git commit SHA. Do not build an Evidence Bundle or content-hash chain for repo process.

## Engineering baseline

The target runtime is Python 3.12 managed by `uv`. Canonical checks:

```text
uv sync --frozen --all-groups
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv run python -m hermes_pipeline.cli contracts check
uv run python -m hermes_pipeline.cli architecture check
```

Windows and Linux behavior must be tested when the affected boundary is platform-specific.

## Test expectations

- Pure domain behavior uses deterministic unit and property tests.
- Every Adapter implements shared contract tests against a deterministic fake.
- Persistence changes include migration, restart, replay, concurrency, and rollback evidence.
- Security boundaries include negative/adversarial tests.
- Agent workflow changes include fixture-based evaluation; live-model tests are non-blocking until explicitly promoted.
- Time, identity, randomness, process execution, filesystem, provider, and network behavior enter through injectable Interfaces.

## Stop and escalate

Stop on suspected credential exposure, repository escape, evidence corruption, or authorization bypass. If a cut needs new product semantics, a new dependency family, a public Interface break, or a destructive migration, get an explicit human decision and an ADR. A formal Contract Change Request file is optional.
