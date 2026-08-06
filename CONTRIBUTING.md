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

The canonical command set is established by Phase 00 (slice-00-02/00-03):

```text
uv sync --frozen --all-groups
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv run python -m hermes_pipeline.cli contracts check
uv run python -m hermes_pipeline.cli contracts drift-check
uv run python -m hermes_pipeline.cli architecture check
```

The managed runtime is Python `>=3.12,<3.13` under `uv 0.12.1`; the full development-tool resolution is frozen in `uv.lock`, and the same checks run offline after installation (`uv run --offline ...` and `uv sync --frozen --all-groups --offline`). `contracts check` is the full read-only validator (identity lock, Draft 2020-12 meta-validation, `$ref` closure, FORMAT_CHECKER instance validation, the f36 baseline corpus three-way gate, OpenAPI/registry checks, canonical hashes, canary scan); `contracts drift-check` byte-compares regenerated projections against the committed files; `contracts generate` is the only command that writes the generated artifacts, and the toolchain is lazy-imported only after the `contracts` subcommand is parsed. `scripts/check_schemas.py` remains the untouched dependency-free bootstrap gate, and a consistency test keeps both validators aligned. `architecture check` runs the standard-library AST import-boundary checker. Their default repository targets intentionally require a Hermes Pipeline source checkout; a standalone installed console supports `--version`, while `architecture check --root <path>` remains explicit-path capable. Set `PYTHONDONTWRITEBYTECODE=1` for a final local artifact audit; CI already supplies it to every job process. CI runs these checks on Windows and Linux via `.github/workflows/python-quality.yml`.

The slice-00-01 bootstrap checks are dependency-free and offline:

```text
python scripts/check_documentation.py
python scripts/check_schemas.py
python scripts/check_schemas.py --self-test-negative
python scripts/check_documentation.py --check-workflows
python scripts/check_repository_artifacts.py
```

`scripts/check_documentation.py` checks governed text files (UTF-8, replacement characters, Markdown fences, root-confined local links, ADR status, required root entry points) and honors the checked root's `.gitignore`, so ignored `reference/`, `.venv`, and tool-cache content is never scanned while unignored governed files still are; `scripts/check_schemas.py` checks the committed Schemas (JSON parsing, `$id` uniqueness and the locked 14-Schema identity set, `$ref` and JSON Pointer resolution). `--check-workflows` validates both workflow YAML files and verifies read-only permissions, no persisted checkout credentials, exact Windows/Linux matrix binding, the frozen quality-command inventory, and the bundled-Node policy; `scripts/check_repository_artifacts.py` rejects generated source-tree cache and bytecode artifacts. `--self-test-negative` executes the checkers against the broken fixtures in `scripts/fixtures/` and asserts stable nonzero exits with sanitized bounded output.

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
