# Slice 05-07 — runtime loads the kernel

Status: **READY**. Branch: `feat/slice-05-07-runtime-kernel`.

## Must

Isolated `runtime-env` can import `KernelBridge`. `pipeline submit` / `read` / `admin` / `deliver` hit the kernel, not the fake ReceiptStore. Root `[project].dependencies` stays empty. Shim stays stdlib.

## Out

SQLAlchemy in the runtime, real GitHub, chaining Stages.
