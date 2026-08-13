# Slice 01-02 — Durable Transaction (READY, revision 1)

Status: **READY**. Assigned worktree: `C:\Users\a2691\AppData\Local\hermes\managed-worktrees\hermes-software-pipeline\slice-01-02`.

Base: `cdf0872078151af8b4f84319c4a30c196bdbc8e3` (01-01 integrated). Predecessor: `slice-01-01`.

## Must

Rewrite (do not import as the public kernel) 00-04 Inbox/Event/revision atomicity onto the 01-01 aggregate.

- `src/hermes_pipeline/controller/kernel.py`: `KernelController` implements `ControllerPort.submit`. `read` returns `PipelineView(status='UNKNOWN', revision=0)` until 01-03.
- Command types: `CONFIRM_REQUIREMENT` payload `{"text": str}`, `REJECT_REQUIREMENT` payload `{"reason": str}`. Other types → `REJECTED`/`VALIDATION_ERROR` message `unsupported command`.
- Map domain `EMPTY_REQUIREMENT` and `INVALID_TRANSITION` → `REJECTED`/`VALIDATION_ERROR` with those exact messages (`empty requirement`, `invalid transition`).
- Same `command_id` + same canonical payload hash → original receipt (`DEDUPLICATED` or `ACCEPTED` as already stored). Same `command_id` + different hash → `CONFLICT`/`CONFLICT` message `command identity conflict`.
- `expected_revision` mismatch → `CONFLICT`/`CONFLICT` message `expected revision conflict`.
- Persistence failure including SQLITE_FULL → non-durable `REJECTED`/`INTERNAL_ERROR` message `persistence unavailable` `retryable=true`; no partial rows.
- `src/hermes_pipeline/persistence/kernel_store.py`: stdlib `sqlite3` only. One transaction writes `inbox`, `events`, `pipelines` (id, status, revision, text). No Outbox, no projection table.
- Reopening the same file after process restart returns the same receipt for a duplicate `command_id`.
- Keep `spike_controller.py` / `sqlite_spike.py` as `KEEP_MARKED_EVIDENCE`. Do not call `CounterSpike` from the kernel.
- Tests: `tests/controller/test_kernel_submit.py`.

## Out

Projections, `read` semantics beyond UNKNOWN, Outbox, leases, LangGraph, new Schemas, new dependency families.
