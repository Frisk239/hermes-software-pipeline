# Observability, Recovery, and Runbooks

## Signals

Structured logs, metrics, traces, audit records, and user notifications serve different purposes:

- logs diagnose implementation behavior;
- metrics describe health, capacity, latency, and error rates;
- traces correlate one command through Controller, Effects, Runs, and Adapters;
- audit records explain authenticated decisions and state changes;
- notifications prompt a human action and are never the authoritative record.

Every signal carries correlation ID and, when authorized, Workspace, Project, Pipeline, Attempt, Run, and effect identities. Sensitive values and raw Project content are excluded by default.

## Required health views

The unversioned `/livez` endpoint means the process event loop is responsive. The unversioned `/readyz` endpoint means storage, migrations, singleton ownership, descriptor protection, and required configuration are valid. `/v1/version` reports protocol and compatibility metadata. Provider or Agent degradation appears in detailed status but does not necessarily make read-only Controller operations unavailable.

Required metrics include:

- command acceptance, rejection, conflict, and deduplication counts;
- Pipeline and Stage state ages;
- Outbox depth and oldest pending age;
- active, expired, fenced, retried, and failed Runs;
- Agent duration, token/cost estimate, and outcome by versioned profile;
- artifact bytes and verification failures;
- worktree/sandbox count and cleanup backlog;
- Feishu/GitHub reconciliation lag and provider errors;
- backup age, update state, and recovery-test freshness.

Cardinality is bounded; artifact paths, user text, commit messages, and raw error bodies are not metric labels.

## Service objectives

Initial local-install objectives are design targets to be measured in Phase 6:

- accepted Controller Commands become durable within 2 seconds at p95 under the supported workload;
- no acknowledged command, approval, Event, or Candidate identity is lost after a single-process crash;
- duplicate provider delivery never produces duplicate business transitions;
- a stuck Run is detected and fenced within its lease plus reconciliation interval;
- the operator is notified of an action-required state within 60 seconds when Feishu is healthy;
- recovery from Last Known Good does not mutate Project source or user working copies.

## Backup boundary

A consistent backup contains:

- Controller DB snapshot and migration metadata;
- Artifact Manifests and content-addressed blobs;
- configuration without plaintext secrets;
- installation identity and compatibility manifest;
- checkpoint DB when active Stage resumption is desired;
- Git ownership metadata and Candidate references, not duplicate user repositories.

Backup creation uses SQLite's supported online backup mechanism or a stopped runtime. Copying live database files directly is prohibited. Every backup has checksums and a restore-test status.

## Restore

Restore always targets an empty staging data root first:

1. verify checksums, format, installation compatibility, and available disk;
2. restore and migrate in staging;
3. rebuild projections and verify Event hash chains;
4. verify Artifact Store manifests and sampled/full blobs according to policy;
5. reconcile Git objects, provider state, leases, and effects without dispatch;
6. run `doctor`;
7. atomically select restored data or abort without changing active data.

Secrets are rebound by identifier after restore.

## Reconciliation loops

Reconciliation is convergent and idempotent:

- Inbox vs Event receipt;
- projection vs Event Log;
- pending/leased Outbox Effects;
- Stage lease vs worker process;
- Run record vs checkpoint;
- Candidate/Integration Candidate vs Git objects;
- remote branch/PR/checks vs Delivery records;
- Feishu notification/card status vs durable decision requests;
- artifact manifest vs content blob;
- Controller-owned directory vs active ownership records.

Automatic repair is allowed only when a deterministic desired state exists. Ambiguity produces an operator incident and no destructive action.

## Incident classes

| Class | Automatic response | Operator action |
| --- | --- | --- |
| transient provider failure | retry with backoff and idempotency | inspect if budget exhausted |
| Agent process failure | record Run failure; retry within policy | choose retry, rework, or pause |
| stale worker/result | fence and reject | none unless repeated |
| corrupted artifact | block Gate and quarantine | restore or rerun producer |
| DB integrity failure | stop writes and readiness | restore from verified backup |
| Git ownership/path anomaly | stop Git operations | inspect roots and ownership |
| suspected secret leak | stop affected Adapters/Runs | rotate, audit, redact/quarantine |
| update health failure | rollback to Last Known Good | inspect staged version |

## Mandatory runbooks

Before public preview, executable runbooks must cover:

- runtime will not start;
- SQLite integrity or migration failure;
- Outbox backlog;
- expired/stuck Stage lease;
- Agent repeatedly fails or exceeds budget;
- worktree or sandbox cleanup failure;
- Git target drift and integration revalidation;
- Feishu unavailable or callback duplicated;
- GitHub rate limit or reconciliation drift;
- artifact corruption;
- secret exposure;
- backup, restore, update rollback, and full uninstall.

Every runbook states detection, safety checks, exact commands, expected output, rollback, escalation, and evidence to preserve.
