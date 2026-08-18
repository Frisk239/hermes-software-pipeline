# Slice 01-02 — Durable Transaction (READY, revision 2)

Status: **READY**. Branch: `feat/slice-01-02-durable-transaction` from `origin/main` `0ab16c0` plus ADR-0031.

Predecessor: `slice-01-01`. PR #22 was reverted; this revision replaces the wrong stdlib-sqlite3 / `command_id`-only contract.

## Must

Durable fake-Pipeline submit: Inbox + Event + pipeline snapshot in one transaction, exactly-once by `(workspace_id, command_id)` with a full-command RFC 8785 fingerprint.

- `controller/transaction_store.py`: private `ControllerTransactionStore` Protocol, records, and typed `PersistenceError`. Protocol only — no SQLAlchemy, sqlite3, os, pathlib, or LangGraph.
- `controller/kernel.py`: `KernelController(store, recorded_at=...)` implements `ControllerPort.submit`. `read` returns `PipelineView(status='UNKNOWN', revision=0)` until 01-03. Inject `recorded_at`; never `datetime.now`.
- Fingerprint is `content_hash` / `canonical_json` of the full `ControllerCommand.model_dump(mode="json")`. Not payload-only. Not `sort_keys`.
- Inbox PK is `(workspace_id, command_id)` and stores the full-command fingerprint plus `receipt_json`.
- Same pair + same fingerprint → return the stored receipt unchanged (do not rewrite status to `DEDUPLICATED`).
- Same pair + different fingerprint → `CONFLICT` / `CONFLICT` / `command identity conflict`.
- `expected_revision` ≠ current `pipelines.revision` (missing row = 0) → `CONFLICT` / `CONFLICT` / `expected revision conflict` before `domain.apply`; no Event.
- `CONFIRM_REQUIREMENT` payload `{"text": str}`; `REJECT_REQUIREMENT` payload `{"reason": str}`. Other type / missing field / wrong type → `REJECTED` / `VALIDATION_ERROR` / `unsupported command`; no write.
- Domain `EMPTY_REQUIREMENT` → `REJECTED` / `VALIDATION_ERROR` / `empty requirement`. `INVALID_TRANSITION` → `REJECTED` / `VALIDATION_ERROR` / `invalid transition`. No write.
- Missing pipelines row = `UNCONFIRMED` revision 0 empty text, then `domain.apply`.
- `ACCEPTED`: one transaction writes inbox + one Event + current aggregate snapshot in `pipelines` (not a projection table). `event_id` matches `evt_[A-Za-z0-9_-]+`.
- Persistence failure including SQLITE_FULL → non-durable `REJECTED` / `INTERNAL_ERROR` / `persistence unavailable` / `retryable=true`; no leftover rows. Adapter translates driver errors to `PersistenceError`; receipts never carry SQL or paths.
- Cross-workspace identical `command_id` values do not interfere.
- `persistence/kernel_memory.py` and `persistence/kernel_sqlite.py` both implement the port. SQLite: WAL, single writer, explicit BEGIN, Alembic initial revision, a new store instance on the same file sees committed data.
- Tests in `tests/controller/test_kernel_submit.py` run the same behavior suite on both adapters.
- Do not import `counter_spike`, `spike_controller`, `sqlite_spike`, or `_persistence_port`. Do not change `domain/pipeline.py` semantics. Do not add root runtime dependencies.

## Out

Projections and real `read` fields (01-03), Outbox, leases, LangGraph, new Schemas, new dependency families, copying PR #22 / `1f5d210`, importing the 00-04 spike.
