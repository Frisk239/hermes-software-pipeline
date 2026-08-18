# Phase 01 — Deterministic Controller Kernel

Phase ID: `phase-01`

Status: `APPROVED`

Owner: Repository Governance Owner `Frisk239`

Document revision: `1`

Base SHA: `e778a5246c4bec3f6a54aec2fdb315ab66ca756e`

Human approval: chat attestation `engapr_phase-01_20260813_01` (P1–P5 accepted)

## Outcome

A fake Pipeline Command is accepted or rejected deterministically, survives process restart, produces deduplicated Events, rebuildable projections, and Outbox Effects, and cannot be advanced by a stale worker generation.

## Entry conditions

- Phase 00 integrated through `e778a52` (PR #18 Closeout);
- P1–P5 accepted: fake Pipeline aggregate only; rewrite 00-04 persistence into the Controller kernel (no silent promote); SQLite single-writer (ADR-0021); Controller has no LangGraph; `read` has no Project RBAC; no new dependency family.

## Slice map

| Slice | Demonstrable result | Depends on | Owns |
| --- | --- | --- | --- |
| `slice-01-01` Domain kernel | pure fake-Pipeline transitions, typed errors, injectable Clock | entry | `EC-01-01` |
| `slice-01-02` Durable transaction | Inbox/Event/revision atomicity, restart, conflict, dedup | `01-01` | `EC-01-02` |
| `slice-01-03` Projection and read | rebuildable projection; `ControllerPort.read` fixture view | `01-02` | `EC-01-03` |
| `slice-01-04` Outbox and replay | Outbox dispatch, idempotent receipts, no double effect | `01-03` | `EC-01-04` |
| `slice-01-05` Lease and fencing | Attempt/Run/lease/heartbeat; stale generation cannot advance | `01-02` | `EC-01-05` |
| `slice-01-06` Crash demonstration | pause/cancel/cleanup + fault injection; Phase Closeout | `01-04`, `01-05` | `EC-01-06` |

WIP is limited by collision risk, not a one-Slice rule (ADR-0031).

## Exit criteria

| ID | Observable criterion |
| --- | --- |
| `EC-01-01` | Domain evaluator is pure and deterministic; invalid commands leave state unchanged. |
| `EC-01-02` | One atomic SQLite transaction covers Inbox, Events, and revision; restart neither loses nor duplicates an acknowledged command. |
| `EC-01-03` | Projection rebuilds from the Event Log; `read` returns only authorized fixture fields. |
| `EC-01-04` | Outbox replay is idempotent; a second delivery does not append a second business Event. |
| `EC-01-05` | Results from an expired lease generation cannot change Pipeline state. |
| `EC-01-06` | Crash/pause/cancel demonstration and Phase Closeout are recorded on the integrated Candidate. |

## Exclusions

- full production Stage state machine (PRD/Architecture/Development);
- Project RBAC, Feishu, GitHub, Agent execution, Managed Worktree;
- promoting keep-marked transport/runtime_broker/CfT/isolation as sealed runtime;
- new dependency families.

## Stop conditions

Stop for human review if SQLite loses or duplicates an acknowledged command, LangGraph is required inside the Controller, a new dependency family appears, or the fake aggregate is insufficient and a real Stage machine is demanded.
