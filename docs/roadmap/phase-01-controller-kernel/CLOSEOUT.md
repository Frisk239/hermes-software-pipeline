# Phase 01 Closeout — Deterministic Controller Kernel

Status: `PENDING_HUMAN_GATE`

Feature tip: `feat/slice-01-06-crash-demo` (unmerged; parent `b6a5291`)

Integrated SHA: `unmerged`

## Exit criteria coverage on this branch

| ID | Covered by |
| --- | --- |
| `EC-01-01` | `tests/domain/test_pipeline_aggregate.py` |
| `EC-01-02` | `tests/controller/test_kernel_submit.py` |
| `EC-01-03` | `tests/controller/test_kernel_read.py` |
| `EC-01-04` | `tests/controller/test_kernel_outbox.py` |
| `EC-01-05` | `tests/controller/test_kernel_lease.py` |
| `EC-01-06` | `tests/controller/test_kernel_control.py` |

## Delivered capability

- fake-Pipeline aggregate (`UNCONFIRMED` / `OPEN` / `REJECTED`) with typed apply errors;
- durable Inbox/Event/revision/Outbox write behind `ControllerTransactionStore` (memory + SQLAlchemy Core SQLite);
- rebuildable projection and fixture `read`;
- idempotent Outbox `replay` without a second Event;
- lease acquire / heartbeat / fencing; stale generation cannot advance state;
- pause / cancel / cleanup; `trip_commit_failure` submit leaves no residue, including after reopening the same SQLite file.

## Residual

- Human merge of `feat/slice-01-02-durable-transaction`, `feat/slice-01-03-projection`, and `feat/slice-01-06-crash-demo`.
- No real process kill, Stage Executor, or Project RBAC.

PHASE.md stays `APPROVED` until a human integrates the Candidate.
