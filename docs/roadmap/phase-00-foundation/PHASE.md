# Phase 00 — Engineering Foundation and Technology Lock

Phase ID: `phase-00`  
Status: `DRAFT`  
Owner: Repository Governance Owner `Frisk239`  
Document revision: `1`  
Base SHA: pending initial documentation baseline commit  
Human approval: pending machine-valid projection after Base SHA exists

## Outcome

A clean clone can validate its design and machine contracts, bootstrap a thin Hermes Shim plus separately managed Python runtime, and run deterministic Windows/Linux checks without implementing production Pipeline behavior.

## Entry conditions

- repository name `hermes-software-pipeline`, product name `Hermes Software Pipeline`, default branch `main`, Apache License 2.0, and `Frisk239` as initial Repository Governance Owner are human-confirmed;
- an initial documentation baseline commit exists and becomes the Phase Base SHA;
- ADR-0014 through ADR-0025 are reviewed and accepted or explicitly replaced;
- the human approves Phase scope and the Phase Plan Schema projection;
- Hermes, Codex CLI, OpenCode CLI, Chrome, Git, Python 3.12, and `uv` compatibility targets are recorded in `docs/development/compatibility-targets.md`.

No implementation Slice may be dispatched while a binding ADR remains `proposed`.

## Affected Module boundaries

- Thin Hermes Shim and authenticated Control Interface;
- managed-runtime packaging and lifecycle;
- versioned contract authoring/generation toolchain;
- Controller transaction and persistence feasibility seams;
- Stage Executor/LangGraph authority boundary;
- Runtime Broker capability enforcement;
- repository structure, architecture checks, deterministic fakes, and CI.

Production behavior behind these boundaries remains excluded.

## Binding design

- `CONTEXT.md`;
- accepted ADR-0001 through ADR-0025;
- `docs/architecture/`;
- `docs/security/`;
- `docs/operations/`;
- `docs/development/`;
- committed `schemas/`.

## Cross-Slice invariants

- The Hermes-loaded Shim remains dependency-light and has no Pipeline authority.
- The managed runtime owns Controller state and exposes only authenticated loopback Interfaces.
- Controller domain code has no LangGraph or Adapter dependency.
- LangGraph is confined to Stage execution.
- Agents have no Git mutation or remote credentials.
- All external behavior is behind a typed Interface with a deterministic fake.
- Required CI uses no live model, provider credential, or public network.
- Every Slice is independently reviewable and leaves mandatory checks green.

## Slice map

| Slice | Demonstrable result | Depends on | Owns exit criteria |
| --- | --- | --- | --- |
| `slice-00-01` Repository baseline | clean `main` clone has identity, governance, docs index, and contract validation | entry decisions | none directly; establishes the trusted base |
| `slice-00-02` Python quality skeleton | frozen `uv` environment and canonical checks run on Windows/Linux | `slice-00-01` | `EC-00-01`, `EC-00-02` |
| `slice-00-03` Contract toolchain | Schemas validate examples, compatibility, canonical hashes, and generated models | `slice-00-02` | `EC-00-03` |
| `slice-00-04` Domain and persistence spikes | written feasibility evidence for Controller transaction, SQLite load/recovery, and LangGraph replay | `slice-00-03` | `EC-00-04`, `EC-00-05`, `EC-00-06` |
| `slice-00-05` Hermes Shim/runtime spike | Hermes invokes a protected loopback fake command and survives lifecycle faults | `slice-00-02`, `slice-00-03` | `EC-00-07`, `EC-00-11` |
| `slice-00-06` Agent/runtime security spikes | Codex/OpenCode structured invocation, cancellation, capability enforcement, and Chrome MCP feasibility proven | `slice-00-02`, `slice-00-03` | `EC-00-08`, `EC-00-09`, `EC-00-10` |
| `slice-00-07` Foundation integration | package Modules, fakes, CI, `doctor`, docs, and Phase evidence integrate on a fixed Candidate | `slice-00-04`, `slice-00-05`, `slice-00-06` | revalidates `EC-00-01`–`EC-00-11`; owns `EC-00-12` |

Default WIP is one executing Slice. Slices `slice-00-04`, `slice-00-05`, and `slice-00-06` may be parallel only after Codex proves path and fixture independence in their final Slice Contracts.

## Phase exit criteria

| ID | Observable criterion |
| --- | --- |
| `EC-00-01` | `uv sync --frozen --all-groups` works on supported Windows and Linux runners. |
| `EC-00-02` | Formatting, lint, type, unit, contract, architecture, and offline integration checks pass. |
| `EC-00-03` | Every committed Schema has valid/invalid fixtures and a reproducible Pydantic/Schema/OpenAPI drift check. |
| `EC-00-04` | The Controller transaction spike demonstrates atomic Inbox/Event/projection/Outbox behavior, deduplication, revision conflict, crash recovery, and stale fencing. |
| `EC-00-05` | SQLite workload evidence supports declared v1 concurrency or triggers a replacement ADR. |
| `EC-00-06` | LangGraph checkpoint/replay evidence proves it cannot independently advance Pipeline state. |
| `EC-00-07` | A real Hermes installation loads the Shim and reaches a fake managed runtime through protected loopback transport. |
| `EC-00-08` | Codex and OpenCode Adapters prove structured output, timeout, cancellation, bounded logs, and error classification. |
| `EC-00-09` | An OpenCode E2E probe can use Chrome DevTools MCP in a clean Verification Sandbox without receiving Git authority. |
| `EC-00-10` | Security tests cover descriptor permissions, path escape, environment leakage, shell avoidance, secret canaries, and process-tree cleanup. |
| `EC-00-11` | `hermes pipeline setup`, `doctor`, `start`, `status`, and `stop` operate idempotently for the non-production skeleton. |
| `EC-00-12` | Accepted decisions, feasibility results, limitations, exact commands, residual risks, and Phase 1 prerequisites are recorded in `CLOSEOUT.md`. |

## Acceptance dimensions

| Dimension | Phase requirement |
| --- | --- |
| Testing | Deterministic Windows/Linux required checks use no live model, provider credential, or public network. |
| Migration | Bootstrap Schema adoption, SQLite migration seam, and rollback feasibility are recorded; no production-state migration occurs. |
| Security | Negative tests prove path, process, environment, secret, descriptor, Agent, browser, and Git authority boundaries. |
| Documentation | README, policies, contract fixtures, commands, compatibility targets, feasibility decisions, and Closeout remain synchronized. |
| Demonstration | A real Hermes load reaches the isolated fake runtime and a complete fake command path survives restart on the exact integrated Candidate. |

## Risk register

| ID | Impact | Risk | Mitigation | Trigger |
| --- | --- | --- | --- | --- |
| `R-01` | Critical | Hermes cannot safely load or supervise the Thin Shim/runtime topology. | Prove real source installation and lifecycle before product code. | Shim requires unmanaged third-party imports or cannot recover after restart. |
| `R-02` | Critical | Windows or Linux cannot enforce a required Agent capability boundary. | Run hostile fixtures on both systems and fail closed for unsupported profiles. | A fixture escapes authorized roots, inherits a canary, or leaves an unfenced process. |
| `R-03` | High | SQLite cannot meet the declared single-Workspace workload or recovery envelope. | Measure queue depth, latency, WAL, backup, disk-full, and crash behavior. | Limits exceed the declared envelope or an acknowledged command is lost/duplicated. |
| `R-04` | High | LangGraph replay duplicates a Controller transition. | Persist command identity/receipt and fault-inject every checkpoint boundary. | Replay appends a second business Event. |
| `R-05` | High | Codex/OpenCode structured or cancellation interfaces are unstable. | Pin versions, capability-probe, classify errors, and preserve fallback evidence. | Required structured result or process-tree cleanup cannot be guaranteed. |
| `R-06` | Medium | Bootstrap contract candidates drift from the future Pydantic authoring source. | Complete adoption and zero-drift checks in Slice 00-03 before behavior-bearing spikes. | Generated output differs without an explicit contract version change. |
| `R-07` | Medium | External provider polling or Feishu interception assumptions differ from real Hermes/GitHub behavior. | Use pinned upstream evidence and isolated real integration probes. | Callback interception or conditional polling cannot be made idempotent. |

## Exclusions

- real Pipeline state-machine behavior;
- live Feishu/GitHub production operations;
- real Project RBAC and approval workflows;
- production Agent prompts or model-quality acceptance;
- remote branch publication, PR creation, merge, deployment, or dashboard;
- destructive migration or automatic update application.

## Stop conditions

Stop the Phase for human review if:

- the Hermes plugin surface cannot safely host the thin Shim;
- supported host platforms cannot enforce required process/path boundaries;
- SQLite fails the declared workload or recovery proof;
- Codex/OpenCode lack a stable structured/cancellation Interface;
- Chrome MCP cannot be isolated from development authority;
- a new dependency family, public service, or privileged helper becomes necessary;
- repository identity or licensing blocks public distribution.

## Phase Gate

Codex reviews the integrated Candidate across design conformance, reproducibility, security, compatibility, documentation, and evidence. Required evidence includes every accepted Slice Closeout, the Phase integration Evidence Bundle, Windows/Linux CI results, feasibility decision reports, and the draft Phase Closeout. Phase completion requires `PASS`, a human-approved Closeout for material conclusions, and a protected merge of the exact reviewed head.
