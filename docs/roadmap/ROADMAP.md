# Engineering Roadmap

This roadmap defines capability order for building the Hermes Software Pipeline. It is not an execution plan. At the start of each Phase, inspect the accepted repository state, design the Slice dependency graph for that Phase, and get human approval for material scope.

Candidate Slices below may be combined, split, reordered, or removed by that Phase Plan, but its exit capability may not be weakened silently.

## Phase 0 — Engineering foundation and technology lock

**Exit capability:** a clean clone has a fixed repository identity, accepted architectural and technology decisions, machine-validated planning/review contracts, a proven Hermes shim/managed-runtime topology, and executable local/CI checks.

Candidate Slices:

1. repository name, `main` branch, initial documentation baseline, README, license, governance, and contribution contract;
2. architecture-package review and ADR-0014 through ADR-0018 closure;
3. version 1 stack decision ADRs and dependency/version policy;
4. Phase Plan, Slice Contract, Context Manifest, Execution Report, Review Verdict, change request, evidence, and closeout Schemas;
5. concise root `AGENTS.md`, Codex and Executor role contracts, and deterministic context assembly;
6. Hermes plugin shim, isolated runtime bootstrap, authenticated local transport, lifecycle, and update feasibility;
7. Controller transaction, LangGraph replay, CLI Adapter, capability-enforcement, and SQLite workload feasibility;
8. package/Module skeleton, lockfile, exact developer commands, deterministic fakes, and executable Windows/Linux CI.

No product behavior is implemented in Phase 0.

## Phase 1 — Deterministic Controller kernel

Approved plan: `docs/roadmap/phase-01-controller-kernel/PHASE.md` (attestation `engapr_phase-01_20260813_01`). Next Slice draft: `slices/01-01-domain-kernel/`.

**Exit capability:** a fake Pipeline Command is accepted or rejected deterministically, survives restart, produces deduplicated Events/projections/Outbox Effects, and cannot be advanced by a stale worker.

Candidate Slices:

1. domain identities, typed errors, policy clock, and pure aggregate transitions;
2. Event Log, Command Inbox, optimistic revision, and atomic transaction;
3. rebuildable projections and authorized `read(pipeline_id)`;
4. Outbox dispatch, idempotent effect receipts, and replay;
5. Stage Attempt, Execution Run, lease, heartbeat, and fencing;
6. reconciliation, pause/cancel, cleanup, and crash-consistency demonstration.

## Phase 2 — Local execution substrate

**Exit capability:** one fake and one real Agent Stage run through the same Stage Executor Interface under a versioned capability profile and return verified content-addressed artifacts.

Candidate Slices:

1. Artifact Manifest, Evidence Bundle, local CAS, access, and retention;
2. capability-profile compiler and runtime enforcement on Windows/Linux;
3. deterministic fake Runtime Broker and Stage Executor;
4. LangGraph Stage graph, checkpoint identity, interrupt, retry, and replay;
5. Codex CLI Adapter with structured result and cancellation contracts;
6. OpenCode CLI Adapter plus Chrome DevTools MCP test-runtime contract.

## Phase 3 — Planning-to-Candidate flow

**Exit capability:** confirmed requirement input moves through independent Codex PRD and Architecture, human Solution Baseline Approval, OpenCode Development/self-test, and Controller-created local Candidate SHA.

Candidate Slices:

1. Project registration, local identity/RBAC foundation, and requirement intake;
2. PRD Stage contract, context, artifacts, and automatic Gate;
3. Architecture/test-plan Stage and Requirement Question routing;
4. Solution Baseline Approval and stale-decision protection;
5. Managed Worktree Development, self-test, and rework;
6. Candidate validation, secret/scope checks, audited commit, and recovery.

## Phase 4 — Independent verification and integration

**Exit capability:** an exact Integration Candidate passes isolated OpenCode E2E with Chrome MCP and fresh Codex Acceptance, or returns deterministic evidence to the correct Development attempt.

Candidate Slices:

1. fake Remote Delivery Adapter and trusted Integration Candidate builder;
2. clean Verification Sandbox and test-environment lifecycle;
3. OpenCode Chrome MCP E2E execution and evidence;
4. fresh Codex Acceptance and baseline-question routing;
5. failure classification and Development rework loop;
6. target drift, new Integration Candidate, and automatic revalidation.

## Phase 5 — Team interaction and GitHub delivery

**Exit capability:** authenticated team members operate a Pipeline through Hermes/Feishu, and an exact verified Candidate reaches a protected GitHub PR whose approval and merge remain native GitHub authority.

Candidate Slices:

1. Workspace and Project administration, membership requests, and audit visibility;
2. Feishu notification, authenticated Hermes card action, feedback, timeout, and CLI fallback;
3. least-privilege GitHub App and signed Delivery Package;
4. namespaced branch and single-PR lifecycle;
5. conditional polling, provider-event deduplication, protected checks, review attestation, and merge queue;
6. real end-to-end team Pipeline and exception-recovery demonstration.

## Phase 6 — Operations and public release

**Exit capability:** a new user can source-install, configure, operate, observe, back up, upgrade, roll back, and safely recover a signed public-preview release on Windows or Linux.

Candidate Slices:

1. idempotent `setup`, `doctor`, start, stop, status, and uninstall;
2. structured logs, metrics, traces, health/readiness, and audit query;
3. backup, restore, reconciliation, incident, and disaster-recovery runbooks;
4. staged update, migration, rollback, and Last Known Good;
5. Agent regression corpus, cost/latency budgets, and promotion Gate;
6. Dashboard or operator UI only after stable Controller contracts;
7. release automation, SBOM, provenance, signatures, compatibility matrix, and public documentation.

## Global ordering rules

- Default development mode is Slice Owner (ADR-0031). The planner / Executor split is optional.
- Every accepted cut leaves the checks that prove its path green and is independently reviewable and revertible.
- Real external Adapters follow deterministic fakes and contract tests.
- Security, migration, recovery, documentation, and evaluation work are delivered with the behavior they govern rather than postponed to a final cleanup Phase.
- The next Phase cannot begin until the current Phase Closeout exists and the human approves any material scope or technology changes.
