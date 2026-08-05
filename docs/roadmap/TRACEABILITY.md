# Capability and Verification Traceability

This document prevents Roadmap capabilities, Phase outcomes, Slice acceptance criteria, tests, and evidence from drifting apart. It defines stable planning identifiers; it does not replace the owning normative document.

## Product capability map

| ID | Target capability | Governing design | Owning Phase | Verification destination |
| --- | --- | --- | --- | --- |
| `CAP-01` | Confirmed requirement input creates one durable, authorized Pipeline. | `CONTEXT.md`, state machine, Controller architecture | Phase 3 | Intake/identity contract, authorization, duplicate/stale command, and scenario tests |
| `CAP-02` | Deterministic Controller decisions survive restart without duplicate transitions or stale advancement. | ADR-0014, Controller architecture, data contracts | Phase 1 | Domain properties, transaction fault injection, replay, fencing, and reconstruction tests |
| `CAP-03` | Agent Stages execute through versioned capabilities and return verified immutable evidence. | ADR-0015/0016/0023, security design | Phase 2 | Runtime contract, hostile fixture, artifact integrity, cancellation, and replay tests |
| `CAP-04` | Independent PRD and Architecture produce an approved solution baseline and constrained local Candidate. | ADR-0004/0012/0013, state machine, Git design | Phase 3 | Stage contract, question routing, approval staleness, worktree scope, and Candidate integrity tests |
| `CAP-05` | Exact Integration Candidates receive isolated E2E and fresh acceptance with deterministic rework routing. | ADR-0018, state machine, Git design | Phase 4 | Integration drift, sandbox, E2E, acceptance, evidence conflict, and revalidation scenarios |
| `CAP-06` | Authenticated team members operate through Hermes/Feishu while protected GitHub remains merge authority. | ADR-0002/0003/0017/0025 | Phase 5 | RBAC decision table, provider identity, card replay, delivery idempotency, protected-check, and merge-queue tests |
| `CAP-07` | A user can install, observe, back up, restore, update, roll back, and recover a signed release. | operations and source-update design | Phase 6 | Clean-install, upgrade, rollback, restore, disaster-recovery, SBOM/provenance, and compatibility tests |

## Cross-cutting requirements

| ID | Requirement | First proving Phase | Continues through |
| --- | --- | --- | --- |
| `XSEC-01` | Untrusted Agent, repository, browser, provider, and user content never carries ambient authority. | Phase 0 feasibility | Every Phase |
| `XREL-01` | Acknowledged commands, approvals, Events, and Candidate identities survive a single-process crash without duplication. | Phase 0 feasibility / Phase 1 implementation | Every persistence or effect Slice |
| `XGIT-01` | Agents never mutate Git or hold remote credentials; exact Git objects, not branch names, bind evidence. | Phase 0 feasibility | Every source/delivery Slice |
| `XCON-01` | Versioned Pydantic sources deterministically generate committed Schema/OpenAPI artifacts with compatibility evidence. | Phase 0 | Every contract change |
| `XPLAT-01` | Required behavior is reproducible on supported Windows and Linux boundaries. | Phase 0 | Every platform-sensitive Slice |
| `XOPS-01` | Behavior ships with observability, recovery, cleanup, migration, documentation, and runbook impact addressed. | Phase 0 skeleton | Every behavior-bearing Slice |
| `XEVAL-01` | Agent workflow promotion is evidence-based, versioned, budgeted, and isolated from required deterministic CI. | Phase 2 foundations | Phases 3–6 |

## Phase 00 exit ownership

| Exit criterion | Primary Slice | Supporting Slice(s) |
| --- | --- | --- |
| `EC-00-01` frozen Windows/Linux environment | `slice-00-02` | `slice-00-07` |
| `EC-00-02` mandatory quality/contract/architecture checks | `slice-00-02` | `slice-00-03`, `slice-00-07` |
| `EC-00-03` Pydantic/Schema/OpenAPI fixtures and drift | `slice-00-03` | `slice-00-07` |
| `EC-00-04` atomic Controller transaction and fencing | `slice-00-04` | `slice-00-07` |
| `EC-00-05` SQLite workload/recovery envelope | `slice-00-04` | `slice-00-07` |
| `EC-00-06` LangGraph replay cannot advance business state | `slice-00-04` | `slice-00-07` |
| `EC-00-07` real Hermes Shim/runtime protected transport | `slice-00-05` | `slice-00-07` |
| `EC-00-08` Codex/OpenCode structured execution and cancellation | `slice-00-06` | `slice-00-07` |
| `EC-00-09` isolated OpenCode/Chrome MCP feasibility | `slice-00-06` | `slice-00-07` |
| `EC-00-10` negative platform-security suite | `slice-00-06` | `slice-00-05`, `slice-00-07` |
| `EC-00-11` idempotent non-production lifecycle CLI | `slice-00-05` | `slice-00-07` |
| `EC-00-12` complete Phase Closeout and Phase 1 prerequisites | `slice-00-07` | every accepted Slice Closeout |

## Repository bootstrap requirements

| ID | Requirement | Owning Slice |
| --- | --- | --- |
| `BOOT-01` | A clean clone exposes product status, trust limits, governance, contribution, security, support, domain language, normative documentation, and Roadmap entry points without ambiguity. | `slice-00-01` |
| `BOOT-02` | Dependency-free offline checks validate governed text, JSON parsing, Schema identity/reference integrity, and representative broken fixtures; full Draft 2020-12 semantics and generation drift remain `slice-00-03`. | `slice-00-01` |
| `BOOT-03` | Required documentation and bootstrap-contract checks execute identically in Windows and Linux CI. | `slice-00-01` |

## Slice traceability rules

Every Slice Contract must:

1. reference at least one `CAP-*`, `X*-*`, Phase exit, ADR, or explicitly approved maintenance requirement in each acceptance criterion;
2. bind every acceptance criterion to one or more verification command identities;
3. state required tests and the exact path-level demonstration;
4. record data, migration, compatibility, security, and documentation implications, including an explicit `none` with rationale when not applicable;
5. name the evidence roles proving each criterion;
6. carry forward unresolved predecessor findings and Phase risks;
7. stop for a Contract Change Request when implementation reveals an unapproved requirement or changes an observable result.

Phase Closeout must show that every Phase exit criterion has accepted evidence and that no capability requirement was silently deferred. A deliberate deferral names the destination Phase/Slice and receives human approval when it changes the approved outcome.
