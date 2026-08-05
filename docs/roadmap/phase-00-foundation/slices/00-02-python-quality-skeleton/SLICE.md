# Slice 00-02 — Python Quality Skeleton

Slice ID: `slice-00-02`

Phase: `phase-00`

Status: `READY`

Document revision: `1`

Predecessor: `slice-00-01` accepted at `6c9623a3a8ad6a124d5d4a1bcddce94a5938e0b4`

Base SHA: `6c9623a3a8ad6a124d5d4a1bcddce94a5938e0b4`

Assigned Managed Worktree: `C:/Users/a2691/AppData/Local/hermes/managed-worktrees/hermes-software-pipeline/slice-00-02`

## Developer path

From a clean Windows or Linux checkout, install the exact frozen Python 3.12 development environment once, then run formatting, lint, type, unit, contract, architecture, and offline integration checks without credentials or further network access.

## Must scope

- add `pyproject.toml`, a committed cross-platform `uv.lock`, `.python-version`, and an installable `src/hermes_pipeline` skeleton;
- use Python `>=3.12,<3.13`, `uv 0.12.1`, the `uv_build` backend, and no runtime dependency;
- expose package version `0.1.0` from installed metadata and the `hermes-pipeline-runtime` / `python -m hermes_pipeline.cli` entry points;
- create the architecture package layout already fixed by `docs/architecture/system-and-module-design.md`, without implementing business behavior;
- configure Ruff, Pyright, pytest, pytest-asyncio, and Hypothesis centrally in `pyproject.toml` and freeze their full resolution in `uv.lock`;
- provide deterministic UTC clock, identity-sequence, and temporary-root pytest fixtures;
- implement a standard-library AST architecture checker with stable diagnostics and deliberately invalid fixtures;
- expose `contracts check` as a direct Python delegation to the existing bootstrap Schema checker and `architecture check` as the canonical architecture gate;
- make repository-root documentation discovery ignore `reference/`, `.venv`, and standard tool caches while still checking governed unignored files, with positive and negative regression tests;
- add a separate read-only Windows/Linux `python-quality.yml` workflow without weakening or changing `documentation-contracts.yml`;
- document exact frozen and offline commands and keep compatibility targets synchronized.

## Out of scope

- Controller rules, state transitions, HTTP transport, database tables, migrations, LangGraph, Hermes Shim, runtime supervision, Agent or browser invocation;
- Pydantic contract authoring, generated JSON Schema/OpenAPI, RFC 8785 implementation, compatibility migrations, or Schema fixture expansion owned by Slice 00-03;
- public production CLI semantics beyond version, contract-check, and architecture-check bootstrap commands;
- runtime dependencies or a second package/build/tool family;
- release publication, tag creation, branch protection, deployment, or acceptance of later Slices.

## Interfaces and authority

- Distribution name: `hermes-pipeline`; import name: `hermes_pipeline`.
- Internal console entry point: `hermes-pipeline-runtime`.
- Canonical module entry point: `python -m hermes_pipeline.cli`.
- Package metadata in `pyproject.toml` is the sole version source; runtime code reads it through `importlib.metadata`.
- The architecture checker owns import-direction validation only; it does not define runtime policy.
- The Executor may read every tracked file but may edit only the machine contract's permitted paths in the assigned worktree.

## Acceptance criteria

| ID | Trace | Observable result |
| --- | --- | --- |
| `AC-01` | `EC-00-01`, `XPLAT-01` | `uv sync --frozen --all-groups` succeeds from the committed lock on required Windows and Linux runners. |
| `AC-02` | `EC-00-02` | Ruff format, Ruff lint, Pyright, pytest, contract, architecture, and bootstrap regression commands all pass. |
| `AC-03` | `BOOT-03` | After the install step, frozen sync and CLI integration checks rerun with `--offline` and no credentials. |
| `AC-04` | `XCON-01` | `--version`, installed distribution metadata, and `hermes_pipeline.__version__` all report `0.1.0`. |
| `AC-05` | `XARCH-01` | The AST checker accepts the skeleton and deterministically rejects forbidden absolute, relative, dynamic, and adapter-to-core import fixtures. |
| `AC-06` | `XTEST-01` | Clock, identity, temp-root, async, and Hypothesis smoke tests are deterministic and leave no repository artifact. |
| `AC-07` | `BOOT-01` | Ignored `reference/`, `.venv`, and tool-cache content cannot break documentation checks, while equivalent unignored invalid content is rejected. |
| `AC-08` | `XSEC-01` | Workflows are read-only, persist no checkout credential, consume no secret, and required tests perform no network operation after installation. |
| `AC-09` | approved Slice scope | Changed paths contain no business, transport, persistence, workflow-engine, Shim, Agent, browser, or provider behavior. |

## Required demonstration

On the exact Candidate, both Windows and Linux jobs install the frozen environment, execute every canonical check, repeat frozen sync and version/contract/architecture smoke checks offline, and prove negative architecture and ignored-path fixtures without modifying the checkout.

## Planning decisions

- Branch flow is `feature/*` through reviewed Pull Request to `main`; signed releases remain separately gated.
- The ignored-path regression is an authorized correction to Slice 00-01, not a waiver.
- Architecture enforcement uses the Python standard library AST and no `import-linter`.
- Exact package resolution belongs in `uv.lock`; direct dependency constraints in `pyproject.toml` must be narrow enough to prevent an unreviewed tool-major upgrade.
