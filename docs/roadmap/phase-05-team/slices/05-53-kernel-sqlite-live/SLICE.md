# Slice 05-53 — Kernel SQLite live

Status: **READY**. Branch: `feat/slice-05-53-kernel-sqlite-live`.

## Must

Live KernelBridge opens `SqliteKernelStore` at `<state-root>/controller.sqlite`. Intake survives restart without `kernel.json`. Empty SQLite imports a legacy `descriptor/kernel.json` dump once.

## Out

Stage RECORD_* events. Alembic to Postgres. Changing `approve`.
