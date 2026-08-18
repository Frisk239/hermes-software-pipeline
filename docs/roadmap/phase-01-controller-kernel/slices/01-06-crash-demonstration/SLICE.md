# Slice 01-06 — Crash Demonstration

Status: **READY**. Branch: `feat/slice-01-06-crash-demo` from `feat/slice-01-03-projection` `b6a5291`.

## Must

`pause` / `resume` / `cancel` / `cleanup` plus `trip_commit_failure` crash demo. Phase Closeout.

- Paused `submit` / `submit_with_lease` → `REJECTED` + `POLICY_REJECTED` / `controller paused`; no inbox/event/outbox write. `read` / `replay` stay up.
- `cancel(workspace_id, pipeline_id)` deletes that lease (empty workspace rejected). Pipeline state and Event Log unchanged.
- `cleanup(now)` deletes `expires_at < now` leases only.
- Store: `delete_lease`, `delete_expired_leases`. Empty workspace on `delete_lease` is a no-op.

## Out

Real process kill, real Stage Executor, submit idempotency changes, new dependency.
