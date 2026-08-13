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
| Chrome DevTools MCP | exact package/server version selected and frozen by Slice 00-06 | `chrome-devtools-mcp@1.7.0`, pinned by the committed npm lock and SRI under accepted ADR-0029; Chrome for Testing remains an experimental non-sealed target. |

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

## Slice-00-05 Hermes shim and managed-runtime spike (accepted ADR-0028)

Slice 00-05 proves the Hermes plugin surface (thin shim, source install,
PluginManager load, `pre_gateway_dispatch` interception), the isolated
Managed Runtime (FastAPI/Uvicorn under accepted ADR-0028), and the
authenticated loopback Control Interface. All spike components carry an
explicit `SPIKE-EXPERIMENTAL` marker with
`DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07`; nothing becomes production
foundation without an explicit Slice 00-07 adoption.

### Hermes pin and evidence sources

| Component | Pinned value | Evidence |
| --- | --- | --- |
| Hermes release | tag `v2026.8.3` = commit `3c27eb6234bf91b8ceee9e9071591b31e9b148cb` (2026-08-03) | GitHub release page fetched 2026-08-10; provisioned in `hermes-integration.yml` with Hermes' own `uv.lock` |
| Hermes probe environment | independent `HERMES_PIPELINE_PROBE_HERMES` (Hermes environment Python) | probe suites skip without it, fail when set but broken; required in CI |
| Host Python | `>=3.11,<3.14` (declared by the pinned Hermes release) | research report §1.1 |
| Probe design | PluginManager load/registration probe; source-install Candidate binding; `GatewayRunner._handle_message` synthetic `/card` probe (fixture-based, offline; Hermes' own test seam is the reference) | research report §1.6/§1.10/§3.5/§3.6 |

### Managed Runtime pin (accepted ADR-0028)

FastAPI/Uvicorn and the declared local `hermes-pipeline==0.1.0` package
exist **only** inside the dedicated `runtime-env/` project (own
`pyproject.toml` + committed `runtime-env/uv.lock`) and materialize
beneath `<state-root>/runtimes/<version>/` via the cross-platform harness
(`UV_PROJECT_ENVIRONMENT` + controlled `uv sync --frozen --project
runtime-env` argv). The root `[project].dependencies` stays empty; the
root `uv.lock` is untouched; Hermes never imports those dependencies.

| Component | Frozen version | Role |
| --- | --- | --- |
| FastAPI | `0.141.1` | Loopback Control Interface framework (ADR-0022), loopback-only |
| Uvicorn | `0.52.1` | ASGI server, bound to `127.0.0.1` only |
| `hermes-pipeline` | `0.1.0` (path source, editable false) | Runtime entry `python -m hermes_pipeline.transport`; no `PYTHONPATH` |

### Fixed spike decisions (research report §5)

| ID | Decision | Fixed value |
| --- | --- | --- |
| D1 | FastAPI/Uvicorn + local package authorization | accepted ADR-0028: only in the isolated Managed Runtime |
| D2 | Runtime installation/isolation | dedicated `runtime-env/` project with committed lock; state-root target interpreter/sys.prefix proof |
| D3 | Windows descriptor ACL | exactly one grant ACE for the current user SID with `(F)`; `icacls <path> /inheritance:r /grant:r *<sid>:(F)`; verification rejects every other subject incl. Everyone/Users/SYSTEM/Administrators; POSIX `0o600`; residual host-admin boundary documented outside the DACL |
| D4 | Fake receipt store | stdlib `sqlite3` in the disposable state root; JSON/memory rejected |
| D5 | Lifecycle state root | `<HERMES_HOME>/software-pipeline/` with `descriptor/`, `runtimes/`, `logs/` children and ownership markers |
| D6 | Hermes CI provision | pinned release commit, Hermes' own `uv.lock`, independent environment, dependency-bootstrap network cutoff |
| D7 | Interception probe topology | real Hermes process + real plugin load + synthetic `MessageEvent` through `GatewayRunner._handle_message` (offline) |

### Fixed protocol and recovery values

Host must equal `127.0.0.1:<port>` or `[::1]:<port>` (else `400` +
`POLICY_REJECTED`); Origin absent or the matching loopback origin (else
`403` + `POLICY_REJECTED`); `X-Hermes-Pipeline-Protocol: 1` required
(else `400` + `VALIDATION_ERROR`, message `unsupported protocol
version`); bearer token from the descriptor (else `401` +
`AUTHENTICATION_FAILED`); 64 KiB body limit on `/v1/commands` (else `413`
+ `VALIDATION_ERROR`); 60-second / 60-request fixed window (else `429` +
`RATE_LIMITED`); shim client timeouts 5 s, runtime request budget 10 s;
unknown path `404` + `NOT_FOUND`; stale/absent descriptor at the client
`DEPENDENCY_UNAVAILABLE` (fail closed). Token rotation happens only when
the runtime process starts; a Hermes restart re-reads the existing
descriptor/token without rotation or rewrite. Descriptor and protocol
versioning is fixed as spike versioned constants plus golden JSON fixtures
(`tests/fixtures/transport/`); the contract-toolchain path is out of
scope.

### Spike dispositions

| Spike component | Paths | Disposition |
| --- | --- | --- |
| Hermes shim | `plugin.yaml`, `__init__.py`, `hermes_shim/` | retain candidate for 00-07 adoption (stdlib-only entry) |
| Fake managed runtime | `src/hermes_pipeline/transport/` | DELETE_UNLESS_ADOPTED_BY_00-07 (loopback spike only) |
| Receipt store | `transport/_receipts.py` + disposable sqlite file | DELETE_UNLESS_ADOPTED_BY_00-07 (never production persistence) |
| Lifecycle CLI | `hermes_shim/_cli.py`, `_lifecycle.py` | retain candidate for 00-07 adoption (idempotent non-production skeleton) |
| Probe harness | `tests/spike/probe/`, `tests/spike/runtime/_harness.py` | retain as CI evidence machinery |
| Provision topology | `runtime-env/` | retain candidate under accepted ADR-0028 |

### Workflow governance extension (fixed in-Slice scope)

`scripts/check_documentation.py` gains `check_hermes_integration_workflow`
(`--check-hermes-workflow` / `--check-hermes-workflow-negative`) and
`scripts/fixtures/workflows/` positive/negative fixtures; the two existing
workflows and their checkers are unchanged.

### Residual risks

- The loopback client explicitly bypasses any system-configured HTTP proxy
  (empty `ProxyHandler`): a resident proxy (e.g. Clash/v2ray) could observe
  or rewrite the bearer token. The runtime's strict Host/Origin validation
  rejects proxied/rewritten requests, tokens rotate on every runtime start,
  and a regression test proves requests never traverse a dead proxy; a
  local proxy process remains inside the documented host-software trust
  boundary.
- `pre_gateway_dispatch` interception semantics depend on the pinned
  Hermes release; behavior drift on upstream `main` requires re-probing.
- Windows descriptor DACL verification covers the DACL only; a local
  administrator or SYSTEM can still access the file through host-admin
  mechanisms outside the DACL (documented host-admin boundary).
- The loopback port is probed then rebound by uvicorn (small TOCTOU
  window); collisions are bounded to 3 fresh-port attempts.
- The fake runtime and receipt store are disposable spike artifacts; they
  never become production foundation without explicit Slice 00-07
  adoption.

## Slice-00-06 agent and runtime security spikes (accepted ADR-0029 and ADR-0030)

Slice 00-06 is READY at Contract revision 14 after a fresh independent Standards
and Spec review closed the rejected r13 real-probe, E2E, digest-chain, and
isolation-evidence findings, and after Git Custodian assignment of a clean execution worktree at
Base `9cf24b876cc7422386ed54c277900ff1e3c2c2bf`. The accepted ADRs confine
the 00-06 browser and Agent-CLI tool families to a disposable Verification
Sandbox. They do not authorize root-project, Hermes-process, or production
dependencies; READY authorizes only the bounded experimental Slice contract.

Authoritative texts: `docs/adr/0029-confine-browser-tool-runtime.md` and
`docs/adr/0030-confine-agent-cli-tool-runtime.md`. Human attestation:
`engadr_0029-0030_20260813_01` (2026-08-13, Repository Governance Owner
`Frisk239`).

| Decision | Accepted meaning |
| --- | --- |
| ADR-0029 | Node `22.23.2`, committed npm inputs, and `chrome-devtools-mcp@1.7.0` SRI are the sealed browser-tool claim. Chrome for Testing `151.0.7922.77` is an experimental unsealed target and cannot satisfy a hard gate. |
| ADR-0030 | Codex `0.146.0` and OpenCode `1.18.12` stay outside the root. Windows sealed Codex is `UNSUPPORTED_RUNTIME` until an independently sourced exact Authenticode signer is pinned. Host is the privileged 00-06 test runner, not Host Operator. |

Exact asset identities and closed argv remain in the 00-06 `tool-lock.json`.
00-07 may retain, rewrite, or delete these spike pins. A later ADR is
required before any of these tools enter the root, Hermes, or a production
service.

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
