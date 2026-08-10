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
| CPython managed runtime | uv-managed CPython `3.12.13` (Astral build), pinned exactly | `.python-version` = `3.12.13` and `python-quality.yml` `setup-uv` `python-version: "3.12.13"` with `UV_MANAGED_PYTHON=1` (revision 7, slice-00-04 CCR); `requires-python` stays `>=3.12,<3.13`. |
| `uv` | compatible with `0.12.x`; exact version recorded by Slice | `0.12.1` |
| Git | `>=2.45,<3`; exact binary/version recorded by each repository operation | `2.53.0.windows.2` |
| Codex CLI | capability-probed; initial target `0.146.x` | `codex-cli 0.146.0` |
| OpenCode CLI | capability-probed; initial target `1.18.x` | `1.18.12` |
| Google Chrome | current stable capability-probed through Chrome DevTools MCP | `150.0.7871.187` |
| Chrome DevTools MCP | exact package/server version selected and frozen by Slice 00-06 | Not yet selected; blocks the browser feasibility probe, not the documentation baseline. |

## Revision-7 managed interpreter pin and SQLite gate (slice-00-04 CCR)

Slice 00-04 attempt 1 stopped with `BLOCKED_CONTRACT`: the managed Windows
runtime (CPython 3.12.10) linked SQLite `3.49.1`, which fails the exact
WAL-reset repair-version predicate (`>=3.51.3 OR (>=3.50.7 AND <3.51.0) OR
(>=3.44.6 AND <3.45.0)`). The human-approved revision-7 resolution keeps the
predicate unchanged and pins the interpreter instead:

- `.python-version` = `3.12.13` (exact, no `+`); `python-quality.yml` pins
  `python-version: "3.12.13"` and sets `UV_MANAGED_PYTHON=1` so uv uses only
  its managed (Astral) builds — a system interpreter of the same version may
  link a different SQLite library and must never satisfy the gate.
- `documentation-contracts.yml` stays on `"3.12"`: it runs only stdlib-only
  bootstrap checks and carries no SQLite persistence conclusion, so it is not
  bound to the source-only `3.12.13` patch.
- The SQLite WAL-reset predicate remains the independent acceptance gate
  (AC-08): `sqlite3.sqlite_version` is recorded on both platforms and must
  satisfy the predicate before any spike persistence conclusion is claimed.
  Windows initial observation (2026-08-08): uv-managed CPython `3.12.13`
  links SQLite `3.53.1` (passes). The Linux value is recorded here after the
  first dual-platform CI run with the pinned interpreter.

## Explicit SQLite driver transaction mode (slice-00-04, AC-03/AC-08)

The slice-00-04 SQLite spike Adapter never relies on the legacy `sqlite3`
implicit transaction control. The chosen explicit driver transaction mode
(`DRIVER_TRANSACTION_MODE` in `src/hermes_pipeline/persistence/sqlite_spike.py`)
is: the `connect` event sets `isolation_level = None` on every pooled
connection (native autocommit, so the driver never opens an implicit
transaction), and the `begin` event emits an explicit `BEGIN` for every
transaction; SQLAlchemy issues the matching `COMMIT`/`ROLLBACK`. The
five-record Controller commit (Inbox, Event, projection, Outbox, receipt)
is therefore atomic only through this explicit BEGIN/COMMIT pair.
Behavior-difference tests prove at the driver level that a raw DML
statement on the Adapter's engine leaves `in_transaction == False` and is
immediately durable (the legacy default silently opens an implicit
transaction, holds the write invisibly, and loses it on close), and that a
failing explicit transaction still rolls back all five records.

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

## Slice-00-04 dev-only spike dependency locks, workload envelope, and measured metrics

ADR-0027 approves the domain and persistence spike dependency family
(`SQLAlchemy Core`, `Alembic`, `LangGraph`, `langgraph-checkpoint-sqlite`,
and their complete transitive shape including `sqlite-vec`) as
development/CI-only; `[project].dependencies` stays empty and the Hermes
plugin entry, `--version`, and the normal runtime path never import them
(AC-13). The exact locks below are read from the frozen `uv.lock` at the
time of the slice-00-04 rework-2 verification (2026-08-10) and are enforced
by a consistency test (`test_dependency_isolation.py`) that parses both
`uv.lock` and this table.

| Component | Exact locked version | Role |
| --- | --- | --- |
| `sqlalchemy` | `2.0.51` | SQLAlchemy Core engine and explicit BEGIN-event transaction mode for the Controller spike Adapter (AC-03/AC-08). |
| `alembic` | `1.19.0` | Upgrade/rollback migration spike on a temporary database (AC-12). |
| `langgraph` | `1.2.10` | Stage spike graph with `durability="sync"` on every invoke (AC-11). |
| `langgraph-checkpoint-sqlite` | `3.1.1` | `SqliteSaver` checkpoint store for the spike checkpoint database (AC-11). |
| `sqlite-vec` | `0.1.9` | Transitive extension loaded by `langgraph-checkpoint-sqlite`; platform wheels only (no sdist). |
| `langgraph-checkpoint` | `4.2.0` | LangGraph checkpoint primitives (transitive). |
| `langgraph-sdk` | `0.4.2` | LangGraph client surface (transitive). |
| `langchain-core` | `1.5.3` | LangGraph runtime core (transitive). |
| `orjson` | `3.11.9` | Fast JSON used by the LangGraph stack (transitive). |
| `greenlet` | `3.5.4` | SQLAlchemy sync/async adapter support (transitive). |
| `typing-extensions` | `4.16.0` | Shared typing backport for SQLAlchemy/LangGraph (transitive). |

`sqlite-vec` wheel admission evidence (from `uv.lock`): the lock admits
only platform wheels — `win_amd64`
(`sha256:4a28dc12fa4b53d7b1dced22da2488fade444e96b5d16fd2d698cd670675cf32`),
`manylinux_2_17_x86_64`
(`sha256:1515727990b49e79bcaf75fdee2ffc7d461f8b66905013231251f1c8938e7786`),
and `manylinux_2_17_aarch64`
(`sha256:4e921e592f24a5f9a18f590b6ddd530eb637e2d474e3b1972f9bbeb773aa3cb9`),
plus the two `macosx` wheels that are not required (macOS is not a version 1
support target). There is no `sdist`, so the frozen environment never
builds this extension from source.

### Fixed workload envelope (slice-00-04, AC-09)

| Limit | Value |
| --- | --- |
| Accepted commands | 1,000 |
| Producers | 4 (single writer) |
| Queue capacity | 32 |
| Command and event payloads | each no larger than 1 KiB |
| p95 acknowledged latency | `<= 2s` |
| Busy count | `= 0` |
| WAL high-water | `<= 16 MiB` |
| Checkpoint / online backup / fresh-process recovery | each `<= 5s` |

The envelope is the acceptance boundary: an exceeded limit or unrecordable
evidence triggers the replacement-ADR path (Phase risk `R-03`), never a
claim that SQLite scales indefinitely.

### Measured metrics (local Windows verification run, 2026-08-10)

Recorded on the rework-2 local verification run: Windows / AMD64 /
uv-managed CPython `3.12.13` / SQLite `3.53.1`, runner label `local`.

| Metric | Measured value | Envelope limit | Status |
| --- | --- | --- | --- |
| Accepted commands | 1,000 | 1,000 | within |
| p95 acknowledged latency | 0.0019 s | `<= 2s` | within |
| Busy count | 0 | `= 0` | within |
| WAL high-water | 3.98 MiB | `<= 16 MiB` | within |
| Queue high-water | 32 | `<= 32` | within |
| Checkpoint | 0.0041 s | `<= 5s` | within |
| Online backup | 0.0321 s | `<= 5s` | within |
| Fresh-process recovery | 0.1092 s | `<= 5s` | within |
| Selected PRAGMAs (from the actual spike database) | `journal_mode=wal`, `synchronous=2`, `wal_autocheckpoint=1000`, `page_size=4096`, `max_page_count=4294967294` | recorded, not limits | recorded |

### SQLite runtime version gate (AC-08) — measured values

The exact WAL-reset repair-version predicate is
`>=3.51.3 OR (>=3.50.7 AND <3.51.0) OR (>=3.44.6 AND <3.45.0)`; a linked
library failing the predicate on either platform stops the Slice with a
Contract Change Request before any spike persistence conclusion is claimed.

| Platform | Interpreter | `sqlite3.sqlite_version` evidence | Predicate |
| --- | --- | --- | --- |
| Windows | uv-managed CPython `3.12.13` | `3.53.1` (passes) | passes |
| Windows and Linux CI | uv-managed CPython `3.12.13` | Every Candidate-bound `pytest` matrix log prints the exact linked value in the bounded `slice-00-04 platform-evidence` header; the gate asserts the predicate in that same job. | must pass before a persistence conclusion |

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
