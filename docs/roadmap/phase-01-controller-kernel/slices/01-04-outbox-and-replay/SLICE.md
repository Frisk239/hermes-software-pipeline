# Slice 01-04 — Outbox and Replay

Status: **READY**. Branch: `feat/slice-01-03-projection` after 01-03.

## Must

CONFIRM ACCEPTED writes one Outbox in the same transaction as inbox + event + pipelines. `replay` records a delivery receipt without appending a business Event; a second replay returns the same receipt.

- Outbox PK `(workspace_id, command_id)`; pending `delivery_receipt_json` is None.
- Store: `list_pending_outbox` (empty workspace → `[]`), `record_outbox_delivery`, `find_outbox`.
- Missing outbox → typed `OutboxNotFound`. Alembic **0003** only.

## Out

Real Delivery/Interaction, lease, LangGraph, new dependency, submit idempotency changes.
