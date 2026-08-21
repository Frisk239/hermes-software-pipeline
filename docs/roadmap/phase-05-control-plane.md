# Phase 5 control plane isolation

Live `pl_lot4`: `approve` recorded APPROVED, then the sidecar died
inside OpenCode. Kernel events can resume; they cannot keep HTTP alive
if OpenCode shares the Control Interface process.

This plan separates **control plane** from **stage worker**. No Temporal,
no Docker, no second `approve` verb (ADR-0012). CLI stays
`submit` / `read` / `approve` / `retry`.

## Problem

Today KernelBridge handles loopback commands **and** runs OpenCode/Chrome
in the same Python process as Uvicorn. A child fence, OOM, or hard kill
takes down `/v1/commands` and `/livez`. `read` then hangs on auto-start.

ADR-0014 already requires leases and fencing for Stage ownership. The
HTTP process should be the Controller; the worker should be the leased
Stage runner.

## Target shape

```text
CLI approve
  → HTTP process: RECORD_APPROVAL, acquire lease, spawn worker, return
     (or CLI waits by polling read)
  → Worker process: hydrate → skip PASS stations → run next Stage
     → RECORD_* → drain Outbox → exit
  → OpenCode/Chrome: children of the worker only (existing fence)
```

HTTP process never calls OpenCode. Worker never serves HTTP.
Job Object / process group applies only to the worker's agent children.

If the worker dies: lease expires; last RECORD_* is the resume point;
`read` still works; next `approve`/`retry` spawns a new worker.

## Operator path (unchanged verbs)

`approve` may **block in the CLI** by polling `read` until verify
READY/REWORK/FAIL or lease gone. The sidecar HTTP stays up the whole
time. Users still type one `approve`.

Optional later: CLI prints `running` and exits; not required here.

## Cuts

### 05-60 http-off-stage-thread

Stop running Stage work on the Uvicorn thread. `process()` for
`approve`/`retry`/`submit` stages goes to a worker thread **or**
returns 202 and a thread. `livez`/`read` stay responsive.

This is a thin precursor if a subprocess is too big for one session.
Out: still one process (crash still kills all). Only do this if 05-61
cannot land in the same PR.

Prefer skipping straight to 05-61.

### 05-61 stage-worker-process

**Must**

- HTTP KernelBridge on `approve`/`retry`: hydrate, RECORD_APPROVAL if
  needed, `acquire_lease(holder=worker-start-identity)`, spawn
  `python -m hermes_pipeline.worker --state-root --pipeline-id --lease-generation`
  with cleaned env (no extra GitHub token beyond what the host already
  injects for Outbox drain on the HTTP side).
- Worker runs only Stage Executor + RECORD_* via Controller commands
  (`submit_with_lease`). Missing/stale lease → exit, no record.
- OpenCode fence is created in the worker, not the HTTP process.
- HTTP `read`/`doctor`/`livez` succeed while the worker is in OpenCode.
- Worker crash: HTTP still up; `read` shows last Kernel stations;
  lease expires; next `approve` continues from fold (existing 05-56).

**Out:** Temporal. Docker. Splitting `approve` into two CLI verbs.
Moving `gh` into the worker (Outbox drain stays on HTTP after
RECORD_VERIFY, or worker calls RECORD only and HTTP drains on read —
keep drain on HTTP `read` as 05-57).

**Demo:** unit: fake worker script sleeps; `read` returns OPEN during
sleep. Fake OpenCode `_exit` in worker does not kill a fake HTTP
parent. Live: `approve` pl_lot4-style; kill worker PID; `read` still
answers; second `approve` does not re-run PRD.

### 05-62 approve-cli-poll

CLI `approve` waits on `read` (bounded, existing 1200s) instead of one
long `/v1/commands`. Command itself returns after spawn (seconds).
Timeout no longer kills the worker.

### 05-63 live-parking-lot

Same parking-lot app. Bars:

1. `read` during implement returns (not hung).
2. Kill worker mid-OpenCode; HTTP stays; `read` has PRD/Arch; re-approve
   skips them.
3. Overlapping `approve` is `busy` (lease).
4. READY + `pr_url` once.

## Rules

- Controller still does not import LangGraph or Chrome.
- Worker may import Stage Executor and runtime adapters.
- One feat branch, one PR at the end.
- Stop and ask if we need a new public command family or Temporal.

## Done when

The Control Interface process can be killed only by `hermes pipeline
stop` (or machine death), not by OpenCode. Stage death is a worker
exit + lease expiry + resume.
