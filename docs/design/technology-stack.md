# Version 1 Technology Stack

This document is the accepted version 1 technology-stack projection under ADR-0019 through ADR-0025. Phase 00 feasibility Slices must still prove its platform and workload assumptions; failed evidence requires a superseding ADR rather than an Executor-selected substitution.

## Decisive Hermes constraint

Hermes source installation clones a plugin into the plugin directory and enables it; it does not install arbitrary Python dependencies declared by that repository. The Hermes process imports the plugin's root `__init__.py` directly.

Therefore, importing LangGraph, an ORM, a web framework, or another plugin-owned dependency inside the Hermes process would be non-reproducible and could conflict with Hermes itself.

Version 1 should use two runtime layers:

```text
Hermes process
└── thin plugin shim
    ├── plugin.yaml
    ├── standard-library + Hermes-guaranteed imports only
    ├── registers high-level tools, CLI commands, and lifecycle hooks
    └── authenticated local client
            ↓ loopback transport
Managed Pipeline Runtime
├── isolated, lockfile-controlled Python environment
├── Pipeline Controller
├── LangGraph Stage Executor
├── persistence, Artifact Store, Runtime Broker, and Adapters
└── independently started, stopped, upgraded, and health-checked
```

The plugin shim never owns Pipeline state and never falls back to running the Controller in the Hermes process.

## Accepted stack

| Area | Version 1 selection | Reason |
| --- | --- | --- |
| Language | Python 3.12 for the managed runtime | Stable cross-platform target; decoupled from the Python used by Hermes |
| Environment and lock | `uv`, committed `pyproject.toml` and `uv.lock` | Reproducible Windows/Linux environment and staged versioned runtime installation |
| Hermes integration | Thin root plugin using Hermes `register(ctx)`, high-level tools, CLI commands, and lifecycle hooks | Uses the supported standalone plugin seam without modifying Hermes core |
| Process topology | One local Controller sidecar per Hermes Workspace | Preserves one-Workspace semantics and isolates dependencies, crashes, and upgrades |
| Local transport | Authenticated HTTP/JSON on loopback with a random port and rotated opaque token | Cross-platform across Windows/Linux and callable by a standard-library shim |
| Control Interface | FastAPI plus Uvicorn | Typed local control surface, OpenAPI generation, async command and health handling |
| Contracts | Pydantic 2 models with generated JSON Schema | One typed validation source for Commands, Events, artifacts, role inputs, and review outputs |
| Domain implementation | Framework-independent Python package | Controller rules remain testable without FastAPI, LangGraph, filesystem, network, or wall clock |
| Business persistence | SQLite in WAL mode with a single Controller writer | Lowest operational burden for one installed Workspace while retaining ACID Command/Event/Outbox transactions |
| Persistence abstraction | SQLAlchemy 2 Core and Alembic migrations | Explicit SQL and transaction control with a viable later PostgreSQL Adapter |
| Outbox dispatch | Database-backed Outbox poller inside the Controller process | No external broker is justified for a single local Controller in version 1 |
| Stage orchestration | LangGraph `StateGraph` behind the Stage Executor Interface | Durable Stage-level orchestration while keeping Pipeline authority in the Controller |
| LangGraph checkpoints | Separate SQLite checkpoint database | Checkpoints and business Events remain operationally and logically separate |
| Artifact storage | Local content-addressed filesystem store plus manifest metadata in the Controller database | Reproducible offline operation and integrity verification without a remote object-store dependency |
| Agent execution | Versioned Codex CLI and OpenCode CLI Adapters using structured non-interactive output | Keeps vendor-specific process and output behavior behind the Runtime Broker seam |
| Browser verification | OpenCode Adapter with Chrome DevTools MCP in a clean Verification Sandbox | Matches the accepted independent E2E responsibility |
| First Git provider | Polling GitHub App Adapter | Works behind NAT while exercising protected PR, checks, review, and merge-queue behavior |
| Human interaction | Hermes Feishu Gateway bridge plus CLI fallback | Reuses authenticated long-connection card actions without exposing the sidecar publicly |
| Configuration | YAML user configuration validated into immutable Pydantic settings | Matches Hermes conventions while preventing untyped configuration at runtime |
| Logging | Structured JSON logging with Pipeline, Stage, Attempt, Run, Command, and trace identities | Supports reconciliation, audit, and later aggregation |
| Metrics and traces | OpenTelemetry Interfaces; local logging exporter in version 1 | Vendor-neutral instrumentation without requiring a hosted observability product |
| Tests | Pytest, pytest-asyncio, Hypothesis, deterministic fake Adapters | Supports state-machine, crash, concurrency, and Interface-level testing |
| Quality | Ruff formatting/linting and Pyright strict type checking | Fast deterministic checks suitable for Agent execution and CI |
| CI | GitHub Actions on Windows and Linux, runtime Python 3.12 | Matches the initial provider and required operating systems |
| Public UI | CLI and Feishu first; Dashboard deferred until Controller contracts stabilize | Prevents UI work from defining unstable domain Interfaces |

All dependency ranges follow the Hermes upstream policy: a lower bound plus a next-major upper bound, with exact versions resolved in `uv.lock`. Stable runtime installation uses the lockfile without opportunistic upgrades.

## Initial repository and Module layout

```text
plugin.yaml
__init__.py                         thin Hermes shim
pyproject.toml
uv.lock
src/hermes_pipeline/
├── domain/                         pure state, policy, events, and errors
├── controller/                     submit/read deep Module
├── contracts/                      versioned Pydantic models and JSON Schemas
├── stage_executor/                 Stage Executor Interface and LangGraph implementation
├── runtime_broker/                 Codex, OpenCode, browser, and fake Adapters
├── artifacts/                      Artifact Store Interface and local CAS Adapter
├── delivery/                       Remote Delivery Interface and GitHub Adapter
├── persistence/                    transaction, projection, migration, and checkpoint Adapters
├── transport/                      FastAPI Control Interface and Hermes event bridge
├── operations/                     health, reconciliation, backup, restore, and update
└── cli/                            runtime-side setup and operator commands
schemas/                            generated committed JSON Schemas
tests/
├── domain/
├── contracts/
├── adapters/
├── integration/
├── scenarios/
├── adversarial/
└── agent_eval/
```

Dependency direction is inward:

- `domain` imports no Adapter, framework, CLI, filesystem, network, model SDK, or wall clock;
- `controller` depends on domain types and private ports, not concrete Adapters;
- external frameworks and provider SDKs live only in Adapter Modules;
- the FastAPI and Hermes layers translate transport data into Controller Commands;
- LangGraph nodes call Controller and Runtime Broker Interfaces but never persistence implementations;
- tests cross the same public Module Interfaces as production callers.

The external Controller Interface remains `submit(command)` and `read(pipeline_id)`. Internal seams are introduced only when production and deterministic test Adapters both exist.

## Database limits and migration path

SQLite is accepted for version 1 only under these invariants:

- exactly one active Controller writer per Workspace;
- all business acceptance transactions occur in that process;
- workers submit Commands rather than writing the database;
- busy timeouts, WAL checkpointing, backup, integrity checking, and disk-full behavior are tested;
- no network filesystem hosts the live database;
- load and database-size thresholds emit warnings before reliability degrades.

PostgreSQL becomes required when the product needs multiple active Controller replicas, remote workers that cannot use the local Command Interface, sustained write concurrency beyond the tested envelope, or high-availability failover. The Event, projection, and Adapter Interfaces must not expose SQLite-specific behavior.

## Required Phase 0 feasibility Slices

The following evidence is required before the accepted design becomes a supported implementation:

1. **Hermes shim and lifecycle spike** — install a minimal source plugin, register a tool and CLI command, bootstrap the isolated runtime, start/restart it through supported Hermes lifecycle behavior, and prove no third-party import enters the Hermes process.
2. **Authenticated local transport spike** — exercise health, Command submission, timeout, restart, token rotation, port collision, and stale-client behavior on Windows and Linux.
3. **Controller transaction spike** — atomically deduplicate a Command, append Events, update a projection, append an Outbox Effect, crash at each boundary, and rebuild the projection.
4. **LangGraph replay spike** — crash after a Controller Command succeeds but before its graph checkpoint records the receipt, then prove replay returns the original Command receipt without a duplicate business transition.
5. **CLI Adapter spike** — pin and exercise real Codex and OpenCode structured runs, cancellation, timeout, malformed output, and result provenance.
6. **Capability enforcement spike** — prove the selected Windows and Linux runtime can enforce the first read-only and writable profiles; do not accept a prompt-only substitute.
7. **SQLite envelope spike** — measure concurrent Command submissions, Outbox processing, backup, recovery, and disk/error behavior against an explicit version 1 workload.
8. **External-event spike** — intercept a generic Hermes Feishu card action before Agent dispatch and reconcile a GitHub PR through conditional polling without a public callback endpoint.

Failure of a spike requires a superseding decision; it does not authorize an Executor to invent a replacement stack inside an implementation Slice.

## Deliberately deferred product choices

These choices are not needed to begin the deterministic kernel after Phase 0:

- hosted deployment or multiple Controller replicas;
- PostgreSQL production Adapter;
- Redis, RabbitMQ, Kafka, or another external broker;
- S3-compatible Artifact Store;
- GitLab delivery Adapter;
- native Hermes Dashboard or desktop UI;
- Kubernetes or container orchestration;
- hosted LangSmith, Datadog, or another observability vendor.

They remain behind existing Interfaces and require a real second implementation or deployment need before a new seam is exposed.

## Accepted decisions and evidence gate

The Repository Governance Owner accepted:

1. thin Hermes shim plus isolated local sidecar;
2. Python 3.12 and `uv`;
3. FastAPI loopback control Interface;
4. SQLite-first single-writer persistence with a defined PostgreSQL trigger;
5. LangGraph `StateGraph` only inside Stage execution;
6. GitHub and Feishu as the first external Adapters;
7. CLI/Feishu-first operation with Dashboard deferred.

These choices are recorded in ADR-0019 through ADR-0025. Successful Phase 00 feasibility evidence promotes them from accepted design to supported implementation; failed evidence requires a superseding ADR.
