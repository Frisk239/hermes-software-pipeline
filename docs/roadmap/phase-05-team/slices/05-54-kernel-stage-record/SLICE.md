# Slice 05-54 — Kernel stage record

Status: **READY**. Branch: `feat/slice-05-53-kernel-sqlite-live`.

## Must

`RECORD_PRD` / `RECORD_ARCHITECTURE` / `RECORD_DEVELOPMENT` / `RECORD_VERIFY` / `RECORD_APPROVAL` append while OPEN. `read` overlays folded events over JSON. Deleting `prd.json` still shows `prd_status`.

## Out

Lease. Resume skip. Outbox publish.
