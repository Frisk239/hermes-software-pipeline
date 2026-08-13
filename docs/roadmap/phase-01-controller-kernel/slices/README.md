# Phase 01 Slice Design

These are planning-level Slice definitions. Codex expands only the next dependency-ready Slice into a machine-valid immutable Slice Contract using the exact current Base SHA.

Slice 01-01 was accepted and integrated at `cdf0872078151af8b4f84319c4a30c196bdbc8e3` (PR #20). The current contract is:

- `01-02-durable-transaction/SLICE.md`;
- `01-02-durable-transaction/slice-contract.json` (READY revision 1, Base `cdf0872`).

## 01-01 Domain kernel

Must: frozen fake-Pipeline aggregate (`UNCONFIRMED` / `OPEN` / `REJECTED`), typed errors, injectable `Clock` Protocol that the evaluator does not call, no I/O. Out: persistence, Controller port wiring, RBAC.

## 01-02 Durable transaction

Must: rewrite 00-04 Inbox/Event/revision atomicity onto the 01-01 aggregate; crash/restart/dedup/conflict. Out: Outbox, projections, leases.

## 01-03 Projection and read

Must: rebuildable projection; `ControllerPort.read(PipelineQuery) -> PipelineView` with fixture fields only. Out: real Project RBAC.

## 01-04 Outbox and replay

Must: Outbox effects, idempotent receipts, replay without a second Event. Out: real Delivery/Interaction adapters.

## 01-05 Lease and fencing

Must: Stage Attempt, Execution Run, lease, heartbeat, fencing generation. Out: real Stage Executor LangGraph.

## 01-06 Crash demonstration

Must: pause/cancel/cleanup, integrated fault-injection demo, Phase Closeout. Out: Phase 2 substrate.
