# Slice 01-05 — Lease and Fencing

Status: **READY**. Branch: `feat/slice-01-03-projection` after 01-04.

## Must

Stage Attempt / Execution Run lease with fencing generation. Expired or superseded generation cannot change Pipeline state.

- `LeaseRecord`: workspace, pipeline, `att_…` / `run_…`, holder, generation ≥ 1, `expires_at`.
- Store: `load_lease`, `save_lease`. Empty workspace → `None`.
- `acquire_lease` / `heartbeat_lease` / `submit_with_lease` take injected `now`. Stale submit → `CONFLICT` + `LEASE_STALE`, no Event, inbox unused. Alembic **0004** only.

## Out

Real Stage Executor / LangGraph, real processes, Outbox dispatch changes, RBAC.
