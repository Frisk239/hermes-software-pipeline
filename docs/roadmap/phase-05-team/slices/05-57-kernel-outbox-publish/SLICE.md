# Slice 05-57 — Kernel outbox publish

Status: **READY**. Branch: `feat/slice-05-57-kernel-outbox`.

## Must

`RECORD_VERIFY` with READY enqueues `PUBLISH_PR`. `read` drains pending Outbox. Already-delivered effects are skipped. Confirm/other stations are not pending publish.

## Out

GitHub check observation. Temporal.
