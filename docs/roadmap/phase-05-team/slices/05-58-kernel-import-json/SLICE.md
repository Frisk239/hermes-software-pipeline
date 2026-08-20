# Slice 05-58 — import JSON stations into Kernel events

Status: **READY**. Branch: `feat/slice-05-57-kernel-outbox`.

## Must

OPEN pipelines with `prd.json` (and other station files) and no stage events import once. A second KernelBridge does not duplicate.

## Out

Rewriting historical JSON. Postgres.
