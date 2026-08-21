# Slice 05-66 — one live worker lease

Status: **READY**. Branch: `feat/slice-05-66-single-worker-lease`.

## Must

`acquire_lease(..., replace=False)` refuses an unexpired lease. Approve/retry spawn uses that, so a second `approve` is `busy` and does not start another OpenCode worker. Fencing takeover (`replace=True`) stays for Kernel tests.

## Out

Killing the live worker from HTTP. Docker.
