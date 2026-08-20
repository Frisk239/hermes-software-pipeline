# Slice 05-55 — Kernel lease on approve

Status: **READY**. Branch: `feat/slice-05-53-kernel-sqlite-live`.

## Must

`approve` acquires a Kernel lease. A second `approve` while the lease is live returns `busy`. Lease is released when `approve` finishes.

## Out

Heartbeat during OpenCode. Outbox publish.
