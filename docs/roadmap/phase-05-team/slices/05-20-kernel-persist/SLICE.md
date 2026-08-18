# Slice 05-20 — persist kernel snapshots

Status: **READY**. Branch: `feat/slice-05-20-kernel-persist`.

## Must

Accepted intake writes `descriptor/kernel.json`. A new KernelBridge on the same state root still reads OPEN. No SQLite in this cut.

## Out

Alembic, multi-writer, lease recovery UI.
