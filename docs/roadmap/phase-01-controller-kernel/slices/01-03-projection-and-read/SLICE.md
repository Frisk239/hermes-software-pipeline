# Slice 01-03 — Projection and Read

Status: **READY**. Branch: `feat/slice-01-03-projection` from `feat/slice-01-02-durable-transaction` `d755080`.

## Must

Rebuildable fake-Pipeline projection so `ControllerPort.read(PipelineQuery) -> PipelineView` returns the three domain states.

- `PipelineView.status` is `UNCONFIRMED | OPEN | REJECTED`. Live path has no `UNKNOWN`. Fields stay `pipeline_id, revision, status`.
- `PipelineQuery.workspace_id` is optional (`""`). Unknown id → `UNCONFIRMED` revision 0. No actor/role on `read`.
- Events carry `pipeline_revision` (Alembic **0002**). Kernel writes `result.state.revision` on ACCEPTED.
- Store: `list_events` (by `pipeline_revision` asc), `rebuild_pipeline` (drop snapshot, fold Event Log, write back), `delete_pipeline` for tests.
- Fold is independent of `domain.apply`: no events → UNCONFIRMED/0/`""`; `REQUIREMENT_CONFIRMED` → OPEN + event revision + payload text; `REQUIREMENT_REJECTED` → REJECTED + event revision, text unchanged.

## Out

Outbox, lease, real RBAC, dashboard, Feishu, submit idempotency changes, new dependency family.
