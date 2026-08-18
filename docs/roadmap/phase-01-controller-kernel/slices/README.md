# Phase 01 Slice Design

These are planning-level Slice definitions. Expand the next dependency-ready cut from the current default-branch SHA. A machine-valid immutable Slice Contract is optional under ADR-0031.

Slice 01-01 was accepted and integrated at `cdf0872078151af8b4f84319c4a30c196bdbc8e3` (PR #20). Slice 01-02 durable transaction is on `feat/slice-01-02-durable-transaction` (`d755080`). Slices 01-03 and 01-04 are on this branch. The current cut is:

- `01-05-lease-and-fencing/SLICE.md`.

PR #22 implemented the wrong 01-02 contract (stdlib sqlite3, Inbox by `command_id` only) and was reverted.

## 01-01 Domain kernel

Must: frozen fake-Pipeline aggregate (`UNCONFIRMED` / `OPEN` / `REJECTED`), typed errors, injectable `Clock` Protocol that the evaluator does not call, no I/O. Out: persistence, Controller port wiring, RBAC.

## 01-02 Durable transaction

Must: rewrite Inbox/Event/revision atomicity onto the 01-01 aggregate behind `ControllerTransactionStore`; exactly once by `(workspace_id, command_id)` with a full-command RFC 8785 fingerprint; SQLAlchemy Core + Alembic SQLite adapter and in-memory fake share one contract. Out: Outbox, projections, leases.

## 01-03 Projection and read

Must: rebuildable projection; `ControllerPort.read(PipelineQuery) -> PipelineView` with fixture fields only. Out: real Project RBAC.

## 01-04 Outbox and replay

Must: Outbox effects, idempotent receipts, replay without a second Event. Out: real Delivery/Interaction adapters.

## 01-05 Lease and fencing

Must: Stage Attempt, Execution Run, lease, heartbeat, fencing generation. Out: real Stage Executor LangGraph.

## 01-06 Crash demonstration

Must: pause/cancel/cleanup, integrated fault-injection demo, Phase Closeout. Out: Phase 2 substrate.
