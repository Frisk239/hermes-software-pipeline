# Phase 00 Compatibility Targets

Snapshot date: 2026-08-05

These are feasibility and CI targets for Phase 00, not a public support promise. Slice Contracts bind exact probed versions and evidence. Phase Closeout converts successful targets into a versioned compatibility statement or records a superseding decision.

## Host and plugin surface

| Component | Phase 00 target | Evidence/status |
| --- | --- | --- |
| Hermes Agent release | `v2026.8.3` | Current upstream release on 2026-08-05; plugin and lifecycle probe baseline. |
| Hermes Agent main reference | commit `aec331899e4748739927fddf02a54327e64419a0` | Current upstream `main` inspected for plugin CLI and gateway hooks; research reference only. |
| Hermes host Python | `>=3.11,<3.14` | Declared by the pinned Hermes release. Shim tests cover 3.11, 3.12, and 3.13 where runners are available. |
| Hermes plugin CLI | `ctx.register_cli_command(name="pipeline", ...)` → `hermes pipeline ...` | Confirmed by the pinned upstream plugin authoring contract. |
| Supported host OS | Windows and Linux | Both required for Phase exit; macOS is not a version 1 support target. |

## Managed runtime and tool probes

| Component | Phase 00 target | Initial local observation |
| --- | --- | --- |
| CPython managed runtime | `>=3.12,<3.13` | `.python-version` and `uv.lock` constrain the Python 3.12 minor line; slice-00-02 locally exercised 3.12.10, while CI may resolve another compatible 3.12 patch. |
| `uv` | compatible with `0.12.x`; exact version recorded by Slice | `0.12.1` |
| Git | `>=2.45,<3`; exact binary/version recorded by each repository operation | `2.53.0.windows.2` |
| Codex CLI | capability-probed; initial target `0.146.x` | `codex-cli 0.146.0` |
| OpenCode CLI | capability-probed; initial target `1.18.x` | `1.18.12` |
| Google Chrome | current stable capability-probed through Chrome DevTools MCP | `150.0.7871.187` |
| Chrome DevTools MCP | exact package/server version selected and frozen by Slice 00-06 | Not yet selected; blocks the browser feasibility probe, not the documentation baseline. |

## Slice-00-02 frozen Python quality resolution

`uv.lock` freezes the complete resolution; direct constraints in
`pyproject.toml` allow only compatible releases, so an unreviewed
tool-major upgrade cannot enter through a fresh lock. Versions observed
when slice-00-02 froze the lock on 2026-08-05:

| Component | Frozen version | Role |
| --- | --- | --- |
| CPython managed runtime | `3.12.*` | `.python-version` selects 3.12; the local verification interpreter was 3.12.10. |
| `uv` | `0.12.1` | Managed runtime and toolchain installer. |
| `uv_build` | resolved by `uv.lock` build metadata | `pyproject.toml` build backend. |
| Ruff | `0.16.1` | Formatting and linting. |
| Pyright | `1.1.411` | Strict static type checking with the locked `nodejs` extra; the Python wrapper resolves `nodejs-wheel-binaries` before global Node, so verification requires no ambient or post-sync Node download. |
| pytest | `8.4.2` | Unit tests. |
| pytest-asyncio | `1.4.0` | Async smoke tests (`asyncio_mode = "auto"`). |
| Hypothesis | `6.165.1` | Deterministic property smoke tests (`derandomize`). |
| `hermes-pipeline` distribution | `0.1.0` | Package metadata is the sole version source. |

## Slice-00-03 dev-only contract toolchain

ADR-0026 approves a development/CI-only dependency family for the contract
toolchain; `[project].dependencies` stays empty. The resolution is frozen in
`uv.lock`; versions observed when slice-00-03 froze the lock on 2026-08-06:

| Component | Frozen version | Role |
| --- | --- | --- |
| Pydantic | `2.13.4` | Sole authoring source for the 14 committed Schemas (ADR-0024); strict models with `extra="forbid"`. |
| jsonschema | `4.26.0` | Draft 2020-12 meta-validation, `$ref` closure, and corpus instance validation; the frozen installation lacks the optional RFC 3339 checker, so each toolchain validator receives a fresh deterministic shared-rule `date-time` checker (revision 7) without mutating the default checker. |
| rfc8785 | `0.1.4` | Single RFC 8785 (JCS) implementation for canonical JSON and `content_hash`; committed golden vectors lock its output. |

The toolchain is lazy-imported only after the `contracts` subcommand is
parsed; the Hermes plugin entry, `--version`, and the normal runtime path
stay pure standard library (AC-10). Generation output is byte-identical on
Windows and Linux (LF, UTF-8, no timestamps or paths); the read-only
`contracts drift-check` gate runs offline in CI on both operating systems.
Compatibility evidence: the f36 Schema snapshots under
`tests/fixtures/contracts/` with their raw-digest manifest, the 174-entry
three-way corpus gate (including the revision-6 finite-integral-number and
RFC 3339 parity cases), and the RFC 8785 golden vectors.

## Compatibility policy

- Exact dependency versions and hashes belong in `uv.lock`; this document records tested product/tool ranges.
- Every Adapter performs version and capability detection before readiness.
- A matching version number without required structured output, cancellation, isolation, or protocol behavior is unsupported.
- Required CI does not download moving dependencies after the frozen environment is prepared.
- Phase 00 records minimum/maximum verified versions and failure behavior in `CLOSEOUT.md`.
- Later changes outside a verified range require a compatibility Slice, updated fixtures, and migration/rollback evidence where applicable.

## Source references

- Hermes release: <https://github.com/NousResearch/hermes-agent/releases/tag/v2026.8.3>
- Hermes inspected commit: <https://github.com/NousResearch/hermes-agent/commit/aec331899e4748739927fddf02a54327e64419a0>
- Hermes plugin authoring guide at the inspected commit: <https://github.com/NousResearch/hermes-agent/blob/aec331899e4748739927fddf02a54327e64419a0/website/docs/developer-guide/plugins/index.md>
