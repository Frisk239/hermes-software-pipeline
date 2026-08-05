# CI, Testing, and Release Standard

This document defines the minimum engineering standard for changes to the plugin. The Pipeline controls high-privilege Agent execution and therefore treats state-machine, authorization, recovery, installation, and update behavior as release-critical.

## Branch and review policy

```text
feature/* → Pull Request → main
main      → release gate → signed tag → stable release
```

- Direct pushes to `main` are prohibited.
- Every change is reviewed through a Pull Request.
- `main` is the integrated, review-gated source branch; a merge does not by itself publish a release.
- Production installation and update discovery use only signed, versioned releases that pass the Release Gate.
- At least one maintainer review is required, with additional approval for security, state-machine, migration, and release-workflow changes.

## Runtime dependency rule

Hermes Git plugin installation clones source but does not provide a general runtime dependency installation contract for this plugin. The Hermes-loaded plugin entry therefore depends only on the Python standard library and dependencies already guaranteed by the supported Hermes version.

Development-only dependencies belong in `pyproject.toml`. Any future runtime dependency requires an explicit installation and isolation design before adoption. Pre-built Dashboard assets are included in stable source releases.

## Pull Request checks

Every Pull Request runs:

1. plugin manifest and version validation;
2. JSON Schema validation;
3. formatting and linting;
4. static type checking;
5. domain and application unit tests;
6. state-machine invariant tests;
7. authorization and identity tests;
8. migration tests;
9. Adapter contract tests;
10. isolated Hermes installation tests;
11. Dashboard lint, unit, and build checks when Dashboard code changes;
12. secret scanning and dependency security checks;
13. documentation link and Mermaid syntax checks.

The Hermes-loaded shim matrix follows Hermes:

```text
Operating systems: Windows, Linux
Hermes host Python: 3.11, 3.12, 3.13
```

The managed Pipeline Runtime uses its own locked Python 3.12 environment and is tested independently on Windows and Linux under ADR-0019 and ADR-0020.

## Test layers

### Domain tests

Domain tests have no Hermes, filesystem, network, subprocess, wall-clock, or model dependency. They cover:

- allowed and forbidden transitions;
- human approval requirements;
- approved-baseline challenge routing;
- attempt creation;
- retry and circuit-breaker policy;
- permission decisions;
- update eligibility;
- invariants across generated transition sequences.
- duplicate Controller Commands with identical and conflicting payloads;
- stale expected revisions and concurrent decisions;
- expired leases, fencing takeover, and late results;
- projection rebuild from the authoritative Event Log.

Time, IDs, and policy inputs are injected. Property-based tests may generate event sequences to prove that forbidden states are unreachable.

### Gate tests

Gate tests verify only machine-verifiable facts:

- artifact presence and hashes;
- Schema versions;
- Stage, Pipeline, and attempt identity;
- candidate commit identity;
- command exit evidence;
- acceptance-criteria coverage mappings;
- stale or conflicting submissions.

Gate tests must prove that a Gate cannot decide product or design semantics.

### Adapter contract tests

Each external Adapter is tested against its Interface using deterministic fakes:

- Hermes Kanban;
- Hermes session identity;
- Codex executor;
- OpenCode executor;
- Feishu notification;
- persistence;
- update source and checkout switching.
- Stage Executor and Runtime Broker;
- Artifact Store;
- Remote Delivery Adapter and Git-host webhook.

Adapter tests cover timeout, malformed output, duplicate delivery, permission denial, partial failure, and restart behavior.
They also cover Outbox replay, stable idempotency keys, compare-and-swap remote heads, duplicate webhooks, unsupported capability enforcement, and attempted privilege expansion.

### Integration tests

Integration tests use an isolated temporary `HERMES_HOME` and verify:

- installation from a Git source checkout;
- plugin enabling and discovery;
- CLI, tool, and skill registration;
- repeatable `setup`;
- database initialization and migration;
- Controller startup and single-instance lease;
- event consumption and reconciliation;
- Inbox/Outbox recovery and projection rebuild;
- Stage Lease takeover with fencing;
- workflow-checkpoint loss followed by replay using the same Controller Command identity;
- Project registration;
- role runtime generation;
- clean uninstall with durable-state preservation.

Paid models and external production services are not used.

### Pipeline scenario tests

Deterministic fake executors exercise complete flows:

- automatic PRD Gate failure and retry;
- Architecture Requirement Question with `AMEND_REQUIREMENT`;
- Architecture Requirement Question with `CLARIFY_UNDER_BASELINE`;
- unresolved human discussion;
- Solution Baseline Approval with requirement rework;
- Solution Baseline Approval with design or test-plan rework;
- development self-test failure;
- E2E failure and development return;
- Acceptance code rejection;
- Acceptance challenge to the Approved Solution Baseline;
- target drift followed by a new Integration Candidate and automatic revalidation;
- material integration conflict routed for human baseline-impact review;
- Merge Approval rejection and development return;
- stale Git-host approval after the MR or merge-group head changes;
- successful external MR or PR merge completion;
- pause, graceful resume, cancellation, reassignment, timeout, and idempotent cleanup;
- infrastructure block and recovery;
- maximum-attempt escalation.

Every backward transition must create a preserved new attempt with the exact triggering evidence or human decision.

### Authorization and adversarial tests

Required cases include:

- Prod Main supplies a forged actor identity;
- an unassigned user clicks an approval card;
- an old card targets a newer artifact attempt;
- a Project Member crosses a Project boundary;
- a Workspace Administrator attempts to read Project content without membership;
- an Agent asks to skip a mandatory Stage;
- a path escapes registered Project roots;
- a candidate SHA is forged or changes between E2E and Acceptance;
- an Artifact Manifest hash, producer, or source identity is forged;
- a runtime cannot enforce one required capability;
- a Remote Delivery Adapter tries to force-push, approve, merge, or alter branch protection;
- the same result or card action is delivered repeatedly;
- content attempts to invoke an internal transition operation.

Authorization is enforced by trusted Hermes request context and server-side policy, not by tool visibility or prompts.

### Crash-consistency tests

Tests terminate and restart the Controller at critical boundaries:

- after creating a Kanban task but before saving its receipt;
- after saving state but before enqueueing a notification;
- after notification delivery but before recording the remote message ID;
- after an external effect succeeds but before its Outbox receipt is recorded;
- after a Stage workflow checkpoint side effect but before the result command is acknowledged;
- after a Stage Lease expires while the original worker is still alive;
- during reconciliation;
- before and after a migration commit;
- after code checkout switching but before Gateway health succeeds.

Recovery must not duplicate Stage creation, process a human decision twice, skip a Gate, or lose the reason for a blocked Pipeline.

### Dashboard tests

Dashboard code is covered by unit tests and browser tests for:

- Pipeline list and detail;
- attempt timeline;
- waiting approvals and questions;
- permission-based visibility;
- evidence links;
- Controller health and offline states;
- responsive layout and keyboard interaction.

### Real Agent smoke tests

Real Codex, OpenCode, and Chrome DevTools MCP runs are isolated from normal Pull Request CI. They run on manual dispatch, a controlled schedule, and release candidates using a purpose-built fixture Project, strict cost and timeout limits, test credentials, and no push permission.

The smoke flow covers:

```text
PRD
→ Architecture
→ simulated human Solution Baseline Approval
→ OpenCode Development and self-test
→ Remote Delivery and exact Integration Candidate
→ fresh OpenCode E2E with Chrome MCP
→ fresh Codex Acceptance on the same integration head
→ simulated human Merge Approval
```

## Release checks

A Release PR and tag require all normal checks plus:

1. clean Git source installation;
2. installation on Windows and Linux;
3. upgrade from every supported previous stable version;
4. state-schema migration and idempotent rerun;
5. in-flight Pipeline recovery across the update;
6. staged update failure and rollback;
7. version consistency across manifest, package metadata, Dashboard, and release manifest;
8. committed Dashboard distribution assets;
9. generated checksums and software bill of materials;
10. signed release tag;
11. final real-Agent smoke result or an explicit approved waiver.

Only after these checks succeed may the stable release manifest expose the version to installed update checkers.

## Regression policy

Every defect fix begins with or includes a test that fails for the reported behavior. The test targets the lowest stable Interface that reproduces the defect and is complemented by a higher-level recovery or scenario test when the defect crossed process or persistence seams.

## Definition of Done

A change is complete only when:

- implementation and failure paths are covered;
- state-machine and permission invariants remain green;
- Schemas and migrations are versioned when affected;
- installation and update behavior remain valid;
- documentation is updated;
- an ADR records any hard-to-reverse trust, state, compatibility, or integration decision;
- no secret or sensitive fixture enters source control;
- all required CI checks and reviews pass.

## Prohibited release shortcuts

- No release from an arbitrary `main` commit without the complete Release Gate and signed tag.
- No auto-update exposure from a passing development build.
- No production CI dependence on real user Projects.
- No mandatory PR check that requires paid model credentials.
- No migration release without upgrade and restart tests.
- No bypass of failed security, state-machine, authorization, or rollback checks.
