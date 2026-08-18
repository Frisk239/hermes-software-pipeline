# Data and API Contracts

This document defines the version 1 contract rules shared by the engineering harness, Pipeline Controller, Stage Executor, Adapters, and operator surfaces. Under ADR-0024, versioned Pydantic 2 models are the sole authoring source; the committed JSON Schemas under `schemas/` are their normative cross-language boundary projection. Markdown examples are explanatory.

## Contract principles

1. Every durable input and output has a stable `schema_id` and integer `schema_version`.
2. JSON is the canonical interchange representation. YAML may be accepted for human-authored configuration only after conversion and validation.
3. Unknown fields are rejected at trust boundaries. Extensions require a new schema version.
4. Times are UTC RFC 3339 strings. Durations are integer milliseconds.
5. Identities are opaque strings with a type prefix; consumers never parse business meaning from them.
6. Git identities are lowercase 40- or 64-character hexadecimal object IDs and always name an exact object, never a branch.
7. Content hashes use `sha256:<lowercase hex>`.
8. Ordered collections use arrays. Maps are used only when key order is irrelevant.
9. Optional and nullable are different. A missing optional field means “not supplied”; `null` is allowed only where the schema explicitly defines a cleared value.
10. Secrets, raw model transcripts, and credentials never appear in Controller Commands, Pipeline Events, or engineering manifests.

## Identity prefixes

| Entity | Prefix | Example |
| --- | --- | --- |
| Workspace | `ws_` | `ws_01J...` |
| Project | `prj_` | `prj_01J...` |
| Pipeline | `pl_` | `pl_01J...` |
| Controller Command | `cmd_` | `cmd_01J...` |
| Pipeline Event | `evt_` | `evt_01J...` |
| Stage Attempt | `att_` | `att_01J...` |
| Execution Run | `run_` | `run_01J...` |
| Artifact | `art_` | `art_01J...` |
| Approval | `apr_` | `apr_01J...` |
| Engineering Phase | `phase-` | `phase-00` |
| Engineering Slice | `slice-` | `slice-00-01` |

Version 1 uses UUIDv7-compatible sortable values after runtime prefixes. The exact generator is an implementation detail; uniqueness, opacity, and stable serialization are contractual.

## Envelope separation

The system has four distinct envelope families:

- a **Controller Command** asks the Controller to evaluate a requested operation;
- a **Command Receipt** reports acceptance, rejection, conflict, or deduplication;
- a **Pipeline Event** records an accepted business fact;
- an **Effect Request** asks an Adapter or worker to perform a side effect.

No envelope may be reused as another family. In particular, receiving a command or card callback is not proof that a state transition occurred.

## Controller Command

The command envelope binds:

- globally unique command identity and idempotency key;
- Workspace, Project, Pipeline, authenticated actor, and ingress channel;
- exact expected Pipeline revision;
- command kind and versioned payload;
- correlation and causation identities;
- submission time.

Authentication context is created by the trusted ingress Adapter. Prod Main may select a permitted operation and provide its business fields, but cannot self-assert actor roles or approval authority.

The Controller processes a command exactly once by `workspace_id + command_id`. Reuse with a different canonical content hash is a security error. A revision mismatch returns `CONFLICT` without appending an Event.

## Pipeline Event

Every Event contains:

- a globally unique Event identity;
- the Pipeline revision assigned by the Controller;
- an event type and event-schema version;
- aggregate identities;
- actor and authorization-decision reference;
- correlation, causation, and accepted command identity;
- canonical payload;
- occurrence and recording time;
- previous-event hash and current-event hash.

Event order is defined by `(pipeline_id, pipeline_revision)`, not wall-clock time. Event hashes make accidental alteration detectable; they are not a replacement for database and backup controls.

## Artifacts and evidence

An Artifact Manifest binds immutable bytes to:

- media type, byte size, digest, schema identity, and logical role;
- producing Stage Attempt and Execution Run;
- Planning, Candidate, Integration Base, and Integration Candidate SHAs where applicable;
- sensitivity and retention class;
- tool, model, workflow, runtime, and capability-profile provenance.

An Evidence Bundle is accepted only if:

- every referenced Artifact Manifest exists and verifies;
- its Attempt, Run, lease generation, source identity, and contract revision match the expected Gate input;
- all evidence roles required by policy are present;
- no referenced artifact exceeds the receiver's sensitivity authorization.

## Engineering harness contracts

Engineering schemas under `schemas/engineering/` describe the optional formal track for developing this repository and are not runtime Pipeline records. Owner-mode cuts (ADR-0031) are not required to emit them, and they do not need `content_hash`, RFC 8785, Context Manifest digests, or Evidence Bundles. Those hash rules still apply to product Artifact Manifests and to formal-track engineering documents that choose to use these schemas.

### Phase Plan

A Phase Plan fixes the outcome, Base SHA, accepted ADR prerequisites, Slice dependency graph, invariants, exit tests, exclusions, and human approval state.

### Slice Contract

A Slice Contract fixes the exact Base SHA, permitted paths, prohibited actions, affected Interfaces, Must and Out scope, observable acceptance criteria, verification commands, required evidence, retry budget, and stop conditions.

Any semantic change produces a new `document_revision` and content hash. An Executor cannot edit its assigned contract.

### Context Manifest

A Context Manifest is the ordered inventory of governing files and immutable facts supplied to one role. It records file digests and purpose, allowing review to prove which authority was used without persisting hidden prompts or secrets. It is not an exhaustive inventory of every file the role may read: supplementary tracked repository content may be inspected for discovery and verification, but cannot override the manifested authority or expand write scope.

### Execution Report

The Executor reports changed paths, commands, test observations, generated artifacts, risks, and a self-assessment. It cannot issue a Review Verdict.

### Review Verdict

The reviewer returns exactly `PASS`, `REWORK`, or `BLOCKED_CONTRACT`, bound to one contract revision, Base SHA, Candidate SHA, Context Manifest, and Evidence Bundle. Findings are structured and independently actionable.

### Contract Change Request and Closeout

A Contract Change Request identifies the exact stop condition and proposed decision without silently widening scope. A Closeout records accepted deliverables, evidence, residual debt, and next prerequisites.

## Schema compatibility

Schema compatibility is explicit:

- patch releases may clarify descriptions or add examples without changing validation;
- adding an optional field requires a new schema version when strict consumers would otherwise reject it;
- removing, renaming, narrowing, changing semantics, or adding a required field is breaking;
- producers declare exactly one version;
- consumers support a documented finite version range;
- migration happens at ingress and records original schema identity and migrated digest;
- historical Events and Artifacts are never rewritten in place.

Schema files use stable `$id` values under `https://schemas.hermes-pipeline.dev/`. Publication at that domain is not required for local validation.

## Canonicalization and hashing

Before hashing, JSON uses RFC 8785 JSON Canonicalization Scheme semantics and UTF-8 encoding. A document's `content_hash` is computed with its `content_hash` field absent. Implementations must expose one shared canonicalization function and golden test vectors.

Files use raw-byte SHA-256. Directory evidence is represented by a sorted manifest of relative POSIX paths, file modes, and file digests; directories are never hashed by archiving them with platform-dependent metadata.

## Redaction and sensitivity

Sensitivity is one of:

- `PUBLIC`;
- `PROJECT`;
- `RESTRICTED`;
- `SECRET_DERIVED`.

`SECRET_DERIVED` means an artifact may contain values derived from secret-backed execution and requires explicit retention policy. Raw secrets are always prohibited. Logs and reports store redaction markers and secret identifiers, never secret values.

## Error contract

Boundary errors use a stable code, safe message, retryability, correlation identity, and optional field violations. Stack traces and provider response bodies remain in protected diagnostic storage.

Top-level error classes are:

- `VALIDATION_ERROR`;
- `AUTHENTICATION_FAILED`;
- `AUTHORIZATION_DENIED`;
- `NOT_FOUND`;
- `CONFLICT`;
- `POLICY_REJECTED`;
- `LEASE_STALE`;
- `DEPENDENCY_UNAVAILABLE`;
- `RATE_LIMITED`;
- `INTERNAL_ERROR`.

Callers branch on codes, never localized messages.

## Control Interface rules

The loopback HTTP Interface:

- accepts JSON only and enforces body-size limits;
- requires bearer authentication plus protocol-version headers;
- never accepts role or authorization claims from request bodies;
- returns `202` plus a Command Receipt for asynchronous operations;
- supports idempotency through command identity, not HTTP connection identity;
- exposes read projections with ETags bound to Pipeline revision;
- provides unversioned `/livez` and `/readyz` probes plus `/v1/version` metadata without Project content;
- does not expose arbitrary file paths, shell commands, prompts, SQL, Git arguments, or Agent tool calls.

The OpenAPI document and committed JSON Schemas are generated deterministically from the same versioned Pydantic models. CI fails when generated contracts differ from committed files. Generated Schema/OpenAPI files are never edited independently.

## Required contract tests

Every Schema and Interface must have:

- one minimal valid golden example;
- one maximal valid example;
- rejection tests for unknown fields, wrong identity type, malformed SHA/hash, invalid enum, and missing required fields;
- canonicalization and hash golden vectors;
- previous-supported-version compatibility fixtures;
- producer/consumer contract tests across each Adapter Seam;
- property tests for round-trip serialization and deterministic rejection;
- redaction tests ensuring secret canaries never appear in returned errors, logs, Events, or reports.
