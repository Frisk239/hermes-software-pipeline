# Configuration and Lifecycle

## Configuration layers

Configuration is merged in this order, with later layers taking precedence:

1. immutable package defaults;
2. Workspace configuration;
3. Project configuration;
4. explicitly permitted environment overrides for local development;
5. command-line overrides for diagnostic commands only.

Pipeline, Stage, and Agent input cannot change administrative configuration. Every effective configuration is validated before runtime readiness and receives a redacted content hash recorded with relevant Events and Runs.

## Configuration domains

| Domain | Owner | Examples |
| --- | --- | --- |
| Runtime | Host Operator | data root, listen policy, process limits |
| Workspace policy | Workspace Administrator | membership defaults, retention ceilings, global concurrency |
| Project policy | Project Administrator | repository, target branch, approver rules, Agent profiles |
| Provider | Host Operator plus authorized Project admin | Feishu mapping, GitHub App installation |
| Stage profile | version-controlled administrator policy | executable, model, filesystem, network, browser |

Unknown keys are errors. Paths become normalized absolute paths during validation; configuration never relies on the runtime current directory.

## Data roots

The runtime owns a single configured data root containing:

```text
runtime/
  descriptor/
  controller/
  checkpoints/
  artifacts/
  worktrees/
  verification/
  logs/
  backups/
  updates/
```

Each child has an ownership marker with installation identity and schema version. Destructive operations validate both the resolved path and ownership marker.

## Lifecycle commands

The supported administrative CLI is the plugin-owned `hermes pipeline` command tree:

- `hermes pipeline setup`;
- `hermes pipeline doctor`;
- `hermes pipeline start`;
- `hermes pipeline status`;
- `hermes pipeline stop`;
- `hermes pipeline backup`;
- `hermes pipeline restore`;
- `hermes pipeline reconcile`;
- `hermes pipeline update check|stage|apply|rollback`;
- `hermes pipeline uninstall`.

The Python distribution is `hermes-pipeline`, its import package is `hermes_pipeline`, and the managed runtime exposes the internal `hermes-pipeline-runtime` entry point. A bare `pipeline` executable is not provided.

Commands are idempotent where meaningful and return structured JSON with stable exit codes. `uninstall` does not delete Project source, user working copies, backups, or audit data unless a separate explicit purge operation is confirmed.

## Startup sequence

1. acquire the installation singleton lock;
2. validate runtime identity, ownership, permissions, and configuration;
3. open Controller DB and verify migration compatibility;
4. open the checkpoint DB separately;
5. verify Artifact Store and managed Git roots;
6. run lightweight reconciliation for expired leases and incomplete effects;
7. bind loopback, create the protected descriptor, and report readiness;
8. enable dispatch only after all required dependencies are ready.

If a step fails, the runtime remains not-ready and performs no new Stage dispatch.

## Shutdown

Graceful shutdown:

1. marks the runtime draining;
2. rejects new dispatch while retaining read access and command durability;
3. requests worker cancellation or checkpoint;
4. waits within a fixed deadline;
5. fences unfinished leases;
6. flushes DB and artifact writes;
7. removes the loopback descriptor and releases the singleton lock.

Crash recovery relies on durable commands, Events, Outbox rows, Run records, checkpoints, and leases rather than in-memory state.

## Configuration changes

- non-sensitive presentation and polling intervals may reload after validation;
- capability, identity, repository, approval, retention, and provider changes require a new policy version;
- changes affecting an active Pipeline do not retroactively alter its approved baseline or active Run;
- restart-required fields are reported explicitly;
- rejected configuration leaves the last valid configuration active.

## Compatibility

The runtime reports:

- plugin version;
- runtime version;
- database schema version;
- supported Control Interface range;
- supported contract-schema ranges;
- Hermes compatibility range;
- Codex/OpenCode/Chrome Adapter capability probes.

`doctor` fails with actionable codes when a required version or feature is missing.
