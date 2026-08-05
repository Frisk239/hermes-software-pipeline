# Design Review Roadmap

This document records how the mainstream-practice audit was converted into the accepted architecture package and the remaining execution-readiness queue. Research evidence remains non-normative in `docs/research/`.

## Confirmed corrections

The following audit conclusions have already been accepted and incorporated:

1. PRD and Architecture remain independent Codex Stages, but the standard Pipeline uses one combined Solution Baseline Approval instead of separate routine PRD and technical approvals.
2. The second routine human boundary is the repository-native MR or PR review and merge after automatic self-test, E2E, and Codex Acceptance.
3. Each Pipeline has one persistent writable Development Worktree; read-only planning uses immutable source views and independent verification uses clean short-lived Verification Sandboxes.
4. Local reference repositories are ignored, read-only, manually refreshed, and pinned by `reference.lock.yaml`; they are never production dependencies.

## Accepted architecture package

The architecture package resolves every previously identified gap. The rows below were accepted as a coherent package because their safety guarantees depend on one another.

| Order | Decision area | Accepted resolution |
| ---: | --- | --- |
| 1 | Durable Controller protocol | Event Log authority; transactional Inbox, Events, projections, and Outbox; revisions, leases, fencing, replay, and reconciliation |
| 2 | Stage runtime capability model | Immutable enforceable profiles; unsupported hard isolation fails closed |
| 3 | Immutable artifact model | Content-addressed Artifact Manifests and typed Evidence Bundles outside mutable worktrees |
| 4 | Remote Delivery Adapter | Separate least-privilege credential boundary; one namespaced branch and MR/PR; no approve or merge permission |
| 5 | Planning and integration baselines | Immutable Planning Base plus automatically revalidated Integration Base and Integration Candidate |
| 6 | Approval authority and attestation | Controller records solution approval; Git host owns final approval and merge; both bind exact actor and artifact/head |
| 7 | Retry and escalation taxonomy | Infrastructure Run retry separated from semantic Stage Attempt rework, with bounded budgets and fail-closed policy paths |
| 8 | Cross-cutting lifecycle | Orthogonal operational state for pause, cancel, timeout, reassignment, recovery, and idempotent cleanup |

Normative design: `docs/design/controller-and-execution-architecture.md`.

Supporting accepted ADRs: ADR-0014 through ADR-0018.

## Decision discipline

- Resolve the queue one dependency at a time.
- Record domain terms in `CONTEXT.md` only after their meaning is accepted.
- Create or supersede an ADR only for a confirmed, hard-to-reverse trade-off.
- Update the state machine only after the relevant transition semantics are accepted.
- Do not treat a reference implementation as a dependency or authority; copy no code without license and fit review.

## Current review boundary

The design package now includes:

- the Codex planner-designer-reviewer and independent Executor operating model;
- the version 1 stack and focused ADR-0019 through ADR-0025;
- process, Module, Interface, data, security, lifecycle, and recovery design;
- root and role Agent contracts;
- initial runtime and engineering Schemas;
- a detailed Phase 00 Plan and seven-Slice map.

The current audit is `docs/development/development-readiness-audit.md`.

The remaining execution-readiness order is:

1. complete and validate the repository documentation baseline;
2. authorize the initial documentation baseline commit on `main`;
3. generate the exact Phase Base SHA and machine-valid Phase Plan projection;
4. expand the first dependency-ready Slice into a machine-valid immutable Slice Contract;
5. execute and review the Phase 00 feasibility Slices;
6. revise any failed technology decision through a superseding ADR;
7. close Phase 00 before any production behavior Slice begins.

The repository is design-ready but not yet Phase-00 execution-ready because the unborn repository has no Base SHA or machine-valid first Slice Contract.
