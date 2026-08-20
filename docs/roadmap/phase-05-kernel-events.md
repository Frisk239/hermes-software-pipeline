# Phase 5 Kernel stage events (product)

Authorized 2026-08-20. Research: `docs/research/2026-08-kernel-events-fit.md`.
Completes ADR-0014 on the live path: Event Log is the only business
history for intake **and** later stations. Does not add Temporal, Docker,
Feishu, Dashboard, or a second `approve` verb (ADR-0012).

Operator CLI stays `submit` / `read` / `approve` / `retry`. Completeness
means crash, retry, concurrent approve, publish, and old pipelines all
answer from Kernel facts.

## Intake

Chrome 05-50–52 are on `main`. Kernel still only
`CONFIRM_REQUIREMENT` / `REJECT_REQUIREMENT`. Stations live in
`prd.json` / `architecture.json` / `development.json` / `verify.json` /
`stages.json`. `kernel.json` is MemoryKernelStore dump. SQLite adapter
exists (`SqliteKernelStore`) but is not on the live bridge. Leases and
Outbox exist on the Controller port and are unused by `approve`.

**Verdict: 有条件通过.** Product hole: authority for later stations is
sidecar JSON.

## Invariants

1. Append-only Event Log. Never delete or edit a recorded station.
   Retry appends a new attempt. Fold takes the **latest event per
   station**.
2. One Controller transaction per accepted command: Inbox + Event +
   projection + Outbox + receipt (ADR-0014). `expected_revision` must
   match. Conflict is non-retryable except lease-stale on a dead holder.
3. LangGraph / OpenCode / Chrome never write Kernel state.
4. Event payloads are outcomes only: ids, gates, SHA, status, attempt.
   No prompts, tokens, stdout, secrets.
5. Pipeline Kernel `status` stays `UNCONFIRMED|OPEN|REJECTED`. No
   `RUNNING_*`.
6. Git mutation and `gh` PR remain Controller/host effects (ADR-0010,
   0017). Adapters do not publish.
7. Version 1 writer is SQLite WAL, single Controller (ADR-0021).
   LangGraph checkpoints, if any, stay a separate DB.

## Identities

`command_id` is stable and not random:

```text
cmd_{pipeline_id}_{station}_{attempt}
```

| station | attempt | When |
|---|---|---|
| `prd` | `1` | first PRD record (PASS or FAIL) |
| `architecture` | `1` | first arch record |
| `development` | `N` | N = 1 + count of prior `DevelopmentRecorded` |
| `verify` | `N` | same N as the development attempt it verified |
| `approval` | `1` | human `approve` accepted |
| `import` | `1` | one-shot JSON → events migration |

Same `command_id` + same fingerprint → stored receipt. Same id +
different fingerprint → `CONFLICT`.

Actor for `RECORD_*`: the runtime holder (`lease.holder`), not the
LLM. Human `approve` remains the project member principal on
`RECORD_APPROVAL`.

## Domain fold

`fold_pipeline_events` (and a new `fold_stage_projection`) rebuild:

| Event | Projection |
|---|---|
| `REQUIREMENT_CONFIRMED` | `status=OPEN`, requirement text |
| `REQUIREMENT_REJECTED` | `status=REJECTED` |
| `ApprovalRecorded` | `approval_status`, `approver_id` |
| `PrdRecorded` | `prd_id`, `prd_status`, `prd_gate` |
| `ArchitectureRecorded` | `design_id`, `testplan_id`, `arch_status`, `arch_gate` |
| `DevelopmentRecorded` | `impl_id`, `candidate_sha`, `candidate_path`, `dev_status`, `candidate_gate`, `rework_attempts` |
| `VerifyRecorded` | `e2e_id`, `acceptance_id`, `verify_status`, `verify_attempts`, `infra_attempts`, `pr_url` |
| `PublishDelivered` | `pr_url`, `pr_number`, `head_sha` (from Outbox receipt) |

`read` uses this projection. Sidecar JSON may be a cache. If JSON and
log disagree, **log wins**.

## Station records (PASS / FAIL / REWORK / INFRA)

Every finished station appends, including failures.

| Status | Record? | Next |
|---|---|---|
| PRD/Arch/Dev gate `PASS` | yes | skip on later `approve` |
| PRD/Arch/Dev gate `FAIL` | yes | `approve`/`retry` may start a new development attempt only after policy below |
| Verify `READY` | yes + Outbox `PUBLISH_PR` | skip verify; drain Outbox |
| Verify `REWORK` | yes | `retry` once (existing cap) |
| Verify `INFRA` | yes | `retry` up to 3 (existing cap) |
| Verify `DENIED`/`DRIFT` | yes | no auto retry |

**Skip rule:** if latest event for that station is PASS/READY, do not
launch the stage runtime.

**Retry rule:** `retry` does not delete events. It records a new
`development`/`verify` attempt with incremented N. Caps: rework 1,
infra 3, counted from events not JSON.

PRD/Arch FAIL: do not auto-loop the planner in this phase. `read`
shows FAIL. A later human `approve` may re-record only if we add an
explicit recut; until then FAIL is terminal for that station (same as
today’s “already in `_prd`” skip, but honest).

## Lease and fencing

`approve` / `retry` **must** hold a Kernel lease for the pipeline.

- `acquire_lease(holder=start_identity, ttl=120s)` before the first
  station. Existing `LeaseRecord.generation` increments.
- Heartbeat while a stage runtime is running (at least every 60s).
- Every `RECORD_*` goes through `submit_with_lease`. Stale generation
  → `LEASE_STALE`, do not append, do not launch the next station.
- On clean finish, `cancel` the lease.
- A new `approve` after expiry may acquire generation+1. The old
  process’s later `RECORD_*` fail closed. OpenCode children of the
  dead holder stay under the existing process fence (05-43); this
  phase does not add Docker.
- Two overlapping `approve`s: second acquire fails or waits until
  expiry. Do not run two executors on one worktree.

## Outbox (publish)

`RECORD_VERIFY` with `verify_status=READY` creates Outbox effect
`PUBLISH_PR` (candidate SHA, pipeline_id, project_id). KernelBridge
drains pending Outbox **after** commit, using the existing host `gh`
path. `record_outbox_delivery` stores `pr_url` / `pr_number`.

If the process dies after the event and before `gh`: restart `read`
shows READY without URL; next `approve`/`read`/`retry` drains Outbox
again (`replay`). Never publish from an adapter. Never publish if
latest verify is not READY.

## Store

Live KernelBridge uses `SqliteKernelStore` under
`<state-root>/controller.sqlite` (WAL, one writer). Stop treating
`kernel.json` as the live log. Import `kernel.json` once if SQLite is
empty and JSON has intake.

## JSON migration

On first SQLite open for a pipeline:

1. If Event Log already has `PrdRecorded` (or any stage event), do
   nothing to JSON.
2. Else if `stages.json` / station files have rows, submit
   `cmd_{id}_import_1` that appends the current station facts as
   events (`source=json_import`). Then JSON is cache-only.
3. Corrupt or empty JSON → no import, fail closed on missing intake
   as today.

Do not rewrite historical JSON files.

## Commands

Internal only (Bridge → Controller). No new HTTP command family.

| Command | Event | Outbox |
|---|---|---|
| `RECORD_APPROVAL` | `ApprovalRecorded` | none |
| `RECORD_PRD` | `PrdRecorded` | none |
| `RECORD_ARCHITECTURE` | `ArchitectureRecorded` | none |
| `RECORD_DEVELOPMENT` | `DevelopmentRecorded` | none |
| `RECORD_VERIFY` | `VerifyRecorded` | `PUBLISH_PR` iff READY |

`CONFIRM_REQUIREMENT` / `REJECT_REQUIREMENT` unchanged.

## Cuts (one feat branch, one PR at the end)

### 05-53 kernel-sqlite-live

Live bridge opens `SqliteKernelStore`. Intake still round-trips after
restart without `kernel.json`. Fake path green. Memory dump import if
SQLite empty.

**Out:** stage events (next cut). Alembic to Postgres.

### 05-54 kernel-stage-record

Domain + Controller accept `RECORD_*`. Fold projection. Bridge records
each finished station (including FAIL/REWORK/INFRA). `read` prefers
fold over JSON. `command_id` as specified. `expected_revision` checked.

**Demo:** confirm → record PRD PASS → new process `read` has `prd_gate`
with station files deleted.

### 05-55 kernel-lease-approve

`approve`/`retry` acquire + heartbeat + `submit_with_lease`. Overlapping
approve is `LEASE_STALE` / busy. Heartbeat test uses fake clock.

### 05-56 kernel-resume-and-retry

Skip PASS/READY stations. Retry appends attempt N+1 within caps.
Crash after PRD+Arch events: next `approve` starts development only.
Attempt counts come from events.

### 05-57 kernel-outbox-publish

READY verify enqueues `PUBLISH_PR`. Drain is idempotent. Death between
event and `gh` recovers on next drain. Adapters still cannot `gh`.

### 05-58 kernel-import-json

Existing pipelines (e.g. `pl_lot3`) import once. Second boot does not
duplicate. Log wins over later JSON edits.

### 05-59 kernel-live-parking-lot

Parking-lot requirement. Bars:

1. Kill sidecar after PRD record; `start` + `approve` resumes; PRD
   artifact id unchanged; READY + `pr_url`.
2. Overlap: second `approve` while first holds lease does not spawn a
   second executor.
3. Kill after READY event before `gh`; restart drains Outbox; one PR.
4. Imported old pipeline `read` still shows prior stations.

## Explicitly later (not this phase)

- Split `approve` into lock-baseline + build (ADR-0012).
- Architecture Requirement Question wait (ADR-0007).
- GitHub check/merge observation beyond Outbox `pr_url`.
- Temporal / Hatchet.
- Docker / AppContainer.
- Streaming model tokens as events.
- Multi-replica Controller / Postgres.

## Done when

Restart reconstructs approval + all stations from SQLite events.
Mid-`approve` crash resumes without repeating PASS. Retry is
append-only and capped. Publish is an Outbox effect. Old JSON
pipelines import once. Operator CLI unchanged.

## Stop and ask

New public Command field, Postgres, Temporal, changing `approve` into
two verbs, or a destructive SQLite migration.
