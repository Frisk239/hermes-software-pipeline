# Mainstream Agent Pipeline Divergence Audit

- Snapshot date: 2026-08-05
- Scope: the current design documents in this repository, compared with primary-source implementations and documentation from coding-agent and durable-execution projects
- Status: research and recommendations only; this document does not supersede an ADR

## Executive conclusion

The design is directionally sound in four important ways: the LLM is not the state-machine authority, source baselines and Candidates are commit-addressed, write-capable Agents do not receive remote Git credentials, and independent verification consumes an exact Candidate SHA. Those choices are at least as strict as the projects reviewed.

The largest remaining divergences are not the number of named Agents. They are:

1. **The workflow is specified as a diagram, but not yet as a durable command/event protocol.** There is no accepted schema for commands, transition events, Stage leases, fencing generations, deduplication keys, transactional outbox records, or replay/reconciliation.
2. **`Base SHA` drift is currently treated too coarsely.** A protected branch and merge queue will normally move after development starts. Mainstream delivery revalidates the Candidate against the current integration head; it does not automatically invalidate PRD, design, and every downstream artifact whenever the target branch moves.
3. **Local Candidate creation and remote delivery are not yet joined.** The Controller correctly has no remote credential, but a separate least-privilege Delivery Adapter, idempotent branch update contract, and PR/MR ownership model are still missing.
4. **Worktree isolation is stronger than mainstream practice at the wrong layer.** Worktrees protect Git checkouts, but they do not isolate processes, browsers, network, secrets, databases, caches, or resource consumption. A Stage capability/sandbox profile is more important than one permanent worktree per read-only role.
5. **Artifacts and audit facts are named but not modeled.** A durable pipeline needs immutable artifact manifests, hashes, provenance, retention/redaction rules, and an append-only transition history separate from mutable projections.
6. **Approval identity is split across Feishu and source control without an authority rule.** Feishu is appropriate for solution feedback and notifications. Final merge approval should be attested and enforced by the Git host's protected-branch identity and rules.

The proposed reduction to two routine human boundaries—one combined solution-baseline review and one final PR/MR merge review—is consistent with the surveyed systems. Other human involvement should be policy- or exception-triggered.

## Method and repository snapshot

Star counts, licenses, repository activity, and release dates below were queried using the official GitHub API/CLI on the snapshot date. Stars are a discovery signal, not an architectural-quality ranking.

| Project | Stars | License reported by GitHub | Activity signal | Relevance |
| --- | ---: | --- | --- | --- |
| [openai/codex](https://github.com/openai/codex) | 103,935 | Apache-2.0 | pushed 2026-08-05; [v0.146.0 released 2026-07-29](https://github.com/openai/codex/releases/tag/rust-v0.146.0) | executable permission profiles, sandboxing, approvals, session rollout |
| [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | 83,118 | MIT | pushed 2026-08-05; [v1.9.0 released 2026-08-03](https://github.com/OpenHands/OpenHands/releases/tag/v1.9.0) | high-level agent control center; now primarily Agent Canvas |
| [microsoft/autogen](https://github.com/microsoft/autogen) | 60,222 | CC-BY-4.0 at repository root | pushed 2026-04-15; latest listed release was [python-v0.7.5, 2025-09-30](https://github.com/microsoft/autogen/releases/tag/python-v0.7.5) | multi-agent message/team abstractions; weak match for Git delivery |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | 56,622 | MIT | pushed 2026-08-04; [1.15.10 released 2026-07-31](https://github.com/crewAIInc/crewAI/releases/tag/1.15.10) | flow/checkpoint concepts; weak match for controlled coding delivery |
| [Aider-AI/aider](https://github.com/Aider-AI/aider) | 47,939 | Apache-2.0 | pushed 2026-05-22; latest listed release was [v0.86.0, 2025-08-09](https://github.com/Aider-AI/aider/releases/tag/v0.86.0) | local edit/commit UX and attribution, not durable orchestration |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 38,887 | MIT | pushed 2026-08-05; checkpoint package [released 2026-07-30](https://github.com/langchain-ai/langgraph/releases/tag/checkpointsqlite%3D%3D3.1.1) | checkpointing, interrupts, replay, retry policy |
| [temporalio/temporal](https://github.com/temporalio/temporal) | 22,099 | MIT | pushed 2026-08-05; [v1.31.2 released 2026-07-08](https://github.com/temporalio/temporal/releases/tag/v1.31.2) | durable execution, Activity retries, idempotency |
| [SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent) | 19,995 | MIT | pushed 2026-08-03; latest listed release was [v1.1.0, 2025-05-22](https://github.com/SWE-agent/SWE-agent/releases/tag/v1.1.0) | run/trajectory/patch/PR boundaries |
| [SWE-agent/SWE-ReX](https://github.com/SWE-agent/SWE-ReX) | 562 | MIT | pushed 2026-08-03; [v1.4.0 released 2025-08-14](https://github.com/SWE-agent/SWE-ReX/releases/tag/v1.4.0) | execution-runtime abstraction; low stars but unusually direct relevance |

OpenHands' high-star repository has changed scope: its current README calls it **Agent Canvas**, a control center able to drive OpenHands, Codex, Claude Code, Gemini, and ACP-compatible Agents across local, container, VM, and remote backends. The durable conversation/event/security implementation now lives mainly in the lower-star [OpenHands software-agent-sdk](https://github.com/OpenHands/software-agent-sdk). This is a concrete example of why cloning only by star count would select the wrong layer.

## Findings by design area

### 1. Orchestration and durable state

The current Hermes design correctly makes the deterministic Controller the only state-transition authority. This resembles durable-execution systems more than chat-based multi-agent frameworks.

What is missing is the protocol below the state diagram:

- OpenHands persists an append-oriented, lock-protected conversation [EventLog](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/event_store.py), maintains an explicit [ConversationExecutionStatus](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/state.py), and protects ownership using an expiring lease with a monotonically increasing `generation` used to detect lost ownership ([conversation_lease.py](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-agent-server/openhands/agent_server/conversation_lease.py)).
- LangGraph exposes synchronous/asynchronous/exit durability modes and explicit interrupt/resume types in [types.py](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/types.py); its checkpoint metadata records source, step, parents, and run identity in the [checkpoint base API](https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint/langgraph/checkpoint/base/__init__.py).
- Temporal's model records Workflow progress durably and treats external/non-deterministic operations as retryable Activities; its documentation explicitly requires Activity implementations to be idempotent because an Activity may execute more than once ([Activity definition](https://docs.temporal.io/activities), [Retry Policies](https://docs.temporal.io/encyclopedia/retry-policies)).

**Divergence:** `pipeline-state-machine.md` describes legal transitions and mentions a retryable outbox, but does not define the durable command/event contract needed to make duplicate completion, Controller failover, late Agent output, and partially delivered notifications safe.

**Recommended correction:** define, before implementation:

- immutable commands with `command_id`, actor, expected Pipeline revision, and authorization context;
- append-only domain events with `event_id`, Pipeline sequence, causal command, old/new state, policy version, and timestamp;
- one mutable projection rebuilt from events or transactionally updated with them;
- Stage Attempt lease with owner, expiry, heartbeat, and monotonically increasing fencing generation;
- an inbox/deduplication table for Hermes, Feishu, Agent, Git-host, and webhook deliveries;
- a transactional outbox for dispatch, notification, and Delivery Adapter requests;
- optimistic concurrency on every transition;
- explicit terminal, paused, cancelling, cancelled, timed-out, infrastructure-blocked, and manual-intervention states.

This does not require adopting Temporal in v1. SQLite/Postgres plus an event table, projection, inbox, outbox, and leases can implement the same invariants at smaller scale.

### 2. Retries and idempotency

LangGraph's default retry classifier retries connection and HTTP 5xx failures while excluding many programming and value/type errors ([`default_retry_on`](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/_internal/_retry.py)). SWE-agent records a run as a trajectory and separates model/run results from optional real-world effects such as applying a patch or opening a PR ([run_single.py](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/run/run_single.py)). Temporal similarly separates deterministic Workflow decisions from retryable, externally effectful Activities ([Activities](https://docs.temporal.io/activities)).

**Divergence:** the current documents test “retry and circuit-breaker policy” but do not yet specify it. Retrying all failures at the Stage level would repeat expensive Agent work and may duplicate external effects.

**Recommended correction:** classify failures into:

- `TRANSIENT_INFRA`: bounded exponential retry of the same attempt execution;
- `AGENT_OUTPUT_INVALID`: new attempt with feedback, never a transparent retry;
- `TEST_FAILURE`: Development rework using the same Pipeline branch;
- `POLICY_DENIED`: fail closed and wait for authorized policy change;
- `HUMAN_TIMEOUT`: remind/escalate/pause, never auto-approve;
- `NON_RETRYABLE`: terminal or manually routed.

Every effectful adapter call needs a stable idempotency key such as `pipeline_id/stage/attempt/effect_type/effect_version`. “At least once delivery + idempotent consumer” should be the assumed transport model.

### 3. Workspace, worktree, and runtime sandbox

SWE-agent starts a run in Docker by default ([run_single.py](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/run/run_single.py)); SWE-ReX deliberately separates a deployment lifecycle (`start`, `is_alive`, `stop`) from its runtime command API ([deployment abstraction](https://github.com/SWE-agent/SWE-ReX/blob/main/src/swerex/deployment/abstract.py), [runtime abstraction](https://github.com/SWE-agent/SWE-ReX/blob/main/src/swerex/runtime/abstract.py)). Codex models filesystem and network access as explicit permission profiles, including read-only, workspace-write, writable roots, and restricted network ([permissions.rs](https://github.com/openai/codex/blob/main/codex-rs/core/src/config/permissions.rs)).

**Divergence:** a managed worktree protects the user's checkout and gives Git isolation, but it is not a security sandbox. It does not prevent a subprocess from reading other host paths, using the network, finding ambient credentials, keeping ports/processes alive, or sharing a browser profile/database with a later test.

**Recommended correction:**

- retain one Controller-owned writable Development worktree per Pipeline;
- let PRD/Architecture read an immutable checkout or source service without permanent role worktrees;
- create clean, short-lived runtime sandboxes for E2E and Acceptance at the exact Candidate SHA;
- define Stage capability profiles for filesystem roots, network destinations, environment variables/secrets, executable families, resource/time limits, browser profiles, ports, and external side effects;
- make a worktree optional for read-only roles and mandatory only where checkout/write concurrency or evidence retention needs it.

ADR-0009's prohibition on using a member's working copy remains valuable. Its “every Stage gets a worktree” clause is stricter than the surveyed systems without delivering equivalent runtime isolation.

### 4. Permissions and tool policy

The Controller-only Git mutation rule is a strong separation of authority. Codex provides useful implementation detail: its permission profiles combine filesystem and network policy ([permissions.rs](https://github.com/openai/codex/blob/main/codex-rs/core/src/config/permissions.rs)); command policy parses and evaluates commands rather than relying only on a string prefix blocklist ([exec_policy.rs](https://github.com/openai/codex/blob/main/codex-rs/core/src/exec_policy.rs)); approval requests carry command, environment, working directory, sandbox permissions, additional permissions, and justification ([approvals.rs](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/approvals.rs)). OpenHands likewise separates risk analysis from a configurable confirmation policy (`AlwaysConfirm`, `NeverConfirm`, or risk threshold) in [confirmation_policy.py](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/security/confirmation_policy.py).

**Divergence:** denying selected `git` subcommands inside the Agent prompt or shell policy is insufficient. An Agent can invoke Git through another executable, library, script, IDE/MCP tool, or direct `.git` file access.

**Recommended correction:** enforcement must be layered:

1. do not mount remote credentials;
2. mount `.git` metadata read-only or expose Git through a narrow Controller-owned service;
3. apply OS/container filesystem and network policy;
4. allow only Stage-scoped tools;
5. parse commands and resolve executable paths;
6. validate the final filesystem diff, symlinks, submodules, special files, size limits, and secret findings;
7. log the effective policy version and every denied/escalated action.

### 5. Artifact, evidence, and audit model

SWE-agent preserves trajectories and patches separately from the optional apply/open-PR step ([run_single.py](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/run/run_single.py)). OpenHands' event store addresses events by stable event ID and persists them independently from the current conversation state ([event_store.py](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/event_store.py)). LangGraph checkpoints contain version, unique monotonic ID, parent/run metadata, and pending writes ([checkpoint base](https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint/langgraph/checkpoint/base/__init__.py)).

**Divergence:** PRD, design, reports, human feedback, logs, screenshots, and test results are currently described as artifacts, but their immutable identity and provenance are not specified. Storing a path such as `docs/PRD.md` is not enough because paths are mutable.

**Recommended correction:** introduce:

- an immutable `ArtifactManifest` with artifact ID, type, schema version, content hash, size, media type, producing Stage/Attempt, Base/Candidate SHA, tool/model/runtime versions, creation time, and sensitivity/retention class;
- content-addressed blob storage outside worktrees, with optional small text projections committed to Git;
- evidence bundles that reference artifacts by ID/hash rather than embedding mutable paths;
- append-only audit events separated from potentially sensitive Agent transcripts;
- redaction, encryption, retention, legal-hold, and Project-access rules;
- artifact compatibility/version validation at every Gate.

### 6. Human approvals and identity

The surveyed implementations favor risk-boundary approvals over approval after every Agent:

- OpenHands' confirmation policy is action-risk based rather than “one click per role” ([confirmation_policy.py](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/security/confirmation_policy.py)).
- Codex approval requests are tied to the exact executable action and its permissions ([approvals.rs](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/approvals.rs)).
- GitHub protected branches can require approving reviews, status checks, conversation resolution, and merge queues at the actual integration boundary ([protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), [merge queues](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)).

**Divergence:** separate mandatory PRD and technical approvals create more routine human interruption than necessary, while the eventual merge approval authority is not yet defined. A Feishu button authenticates a Hermes business decision; it should not silently substitute for a protected-branch review.

**Recommended correction:**

- routine Gate 1: one human solution-baseline decision over PRD + architecture + test plan;
- routine Gate 2: Git-host PR/MR approval and merge, enforced by branch protection and the Git-host reviewer identity;
- Feishu may notify, deep-link, and collect the first decision; final merge approval remains authoritative in GitHub/GitLab;
- persist an approval attestation containing decision type, actor's provider and immutable provider user ID, role at decision time, artifact/head SHA, policy version, timestamp, and source event/card/PR ID;
- reject stale card actions and approvals whose artifact or head SHA no longer matches;
- trigger extra human review only for requirement questions, privileged actions, material baseline conflicts, security/data migrations, retry exhaustion, or policy-defined regulated changes.

### 7. `Base SHA`, target drift, and merge queues

Freezing the source used to produce a Candidate is correct. Treating every later movement of the target branch as a reason to invalidate the full Pipeline is not.

GitHub's merge queue creates a temporary merge-group branch that combines the PR with the latest target and other queued changes, then runs required checks before integration ([merge queue documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)). Protected branches may also require the branch to be up to date before merging ([protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)).

**Divergence:** `REFRESH_BASELINE` currently invalidates all downstream baselines, attempts, Candidates, approvals, and tests “as required by the state machine,” but no impact test distinguishes harmless target movement from a material requirement/design conflict. In an active repository this can cause needless restart loops.

**Recommended correction:** model two different commits:

- `planning_base_sha`: immutable source context on which PRD/design/development began;
- `integration_base_sha`: latest target head used to build the merge/rebase candidate or merge-group.

When the target moves:

1. calculate changed paths and merge/conflict status;
2. produce an integration Candidate from the existing Candidate and new integration base without rewriting audit history;
3. rerun required build, tests, E2E/acceptance, and security checks on the exact integration Candidate or merge-group SHA;
4. request human semantic routing only if conflicts, protected/API/schema paths, acceptance behavior, threat model, or risk policy indicate the approved solution may no longer be valid;
5. preserve the original planning baseline and both SHAs in provenance.

`KEEP_BASELINE` remains appropriate while development continues. A full PRD/design refresh should be exceptional, not the default response to normal branch movement.

### 8. Git and PR/MR delivery

SWE-agent makes opening a PR an explicit optional post-run action rather than an implicit consequence of model completion ([run_single.py](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/run/run_single.py)). Its current implementation creates a branch, commits, pushes, and opens a PR from inside the execution environment ([open_pr.py](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/run/hooks/open_pr.py)); that implementation is useful as a boundary example but is too permissive for this design because the Agent environment receives Git-host credentials and performs Git mutations.

Aider is also intentionally developer-local: it auto-commits edits, may commit pre-existing dirty changes, exposes raw `/git`, and skips commit verification by default unless configured otherwise ([Aider Git integration](https://github.com/Aider-AI/aider/blob/main/aider/website/docs/git.md)). This should not be copied into a team Controller.

**Divergence:** the Hermes Controller is correctly denied remote credentials, but no actor can yet safely push the Controller-created Candidate and create/update the MR.

**Recommended correction:** create a separate **Remote Delivery Adapter**:

- authenticate as a GitHub App/GitLab bot installed only on approved Projects;
- grant repository-content write and pull/merge-request write only where required; no administration, secrets, workflow-edit, or bypass permission;
- accept only Controller-signed requests containing Pipeline, Candidate SHA, expected remote head SHA, target branch, and idempotency key;
- own namespaced branches such as `hermes/<project>/<pipeline>`;
- use compare-and-swap semantics: reject an unexpected remote branch head instead of force-pushing;
- create or update exactly one PR/MR per Pipeline and return immutable provider IDs;
- never merge or approve its own PR;
- verify that the PR head SHA and successful Gate evidence still match before marking “ready for human merge”;
- consume Git-host webhooks through an inbox/dedup layer and treat repository branch protection as the final merge authority.

## Recommended reference checkout set

Do not clone every high-star repository. Four shallow, pinned, ignored checkouts are enough:

| Priority | Repository to shallow-clone under `reference/` | Why it earns local source space | Read these paths first |
| --- | --- | --- | --- |
| 1 | [OpenHands/software-agent-sdk](https://github.com/OpenHands/software-agent-sdk) | Best compact reference for event log, conversation state, ownership lease, security policy, tool registry, and server boundary behind the high-star OpenHands product | `openhands-sdk/openhands/sdk/conversation/event_store.py`; `conversation/state.py`; `openhands-agent-server/openhands/agent_server/conversation_lease.py`; `openhands-sdk/openhands/sdk/security/`; `openhands-sdk/openhands/sdk/tool/` |
| 2 | [SWE-agent/SWE-ReX](https://github.com/SWE-agent/SWE-ReX) | Direct reference for separating execution deployment lifecycle from runtime command APIs; useful for local/Docker/remote OpenCode/Codex adapters | `src/swerex/deployment/abstract.py`; `deployment/docker.py`; `runtime/abstract.py`; `runtime/remote.py` |
| 3 | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | Concrete checkpoint, interrupt/resume, retry, pending-write, and replay implementation | `libs/langgraph/langgraph/types.py`; `libs/langgraph/langgraph/_internal/_retry.py`; `libs/langgraph/langgraph/pregel/`; `libs/checkpoint/langgraph/checkpoint/base/`; `libs/checkpoint-sqlite/` |
| 4 | [SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent) | Compact example of problem input → isolated run → trajectory/patch → optional PR delivery; helpful for evidence and adapter boundaries | `sweagent/run/run_single.py`; `sweagent/agent/agents.py`; `sweagent/environment/swe_env.py`; `sweagent/run/hooks/apply_patch.py`; `sweagent/run/hooks/open_pr.py`; `sweagent/types.py` |

Recommended operational rules for `reference/`:

- shallow clone and pin each repository to a recorded commit; do not track floating `main`;
- record source URL, commit, license, retrieval date, and purpose in a small tracked manifest outside the ignored clone directory;
- treat all reference code as read-only; copy no code until its file-level license and compatibility are reviewed;
- update references manually for a specific research question, not automatically with plugin updates;
- never import or execute code directly from `reference/` in production or tests.

### Project-specific checkout applied

The generic comparison set above prioritizes reusable harness internals. This project also has a direct integration requirement with Codex CLI and OpenCode CLI, so the local checkout set was deliberately adjusted to:

1. `openai/codex` for the exact execution, permission, sandbox, approval, session, and `AGENTS.md` contracts being integrated;
2. `anomalyco/opencode` for the exact session, permission, MCP, plugin, Git, and worktree contracts being integrated;
3. `OpenHands/software-agent-sdk` for durable event, state, lease, security, and tool-server patterns;
4. `langchain-ai/langgraph` for checkpoint, interrupt/resume, retry, pending-write, and replay semantics.

The ignored clones are pinned by the tracked `reference.lock.yaml`. SWE-ReX, SWE-agent, Temporal, the OpenHands parent repository, and Aider remain online, path-specific references unless a later implementation question justifies replacing or adding a checkout.

### Read online; do not clone by default

- **[openai/codex](https://github.com/openai/codex):** essential for permission/sandbox/approval ideas, but very large and already installed as an execution target. Prefer the specific paths `codex-rs/core/src/config/permissions.rs`, `codex-rs/core/src/exec_policy.rs`, `codex-rs/core/src/tools/approvals.rs`, and session/rollout code.
- **[temporalio/temporal](https://github.com/temporalio/temporal):** use the official durable-execution and retry documentation. The Go server is too large and too infrastructure-specific unless the project later chooses Temporal as a runtime.
- **[OpenHands/OpenHands](https://github.com/OpenHands/OpenHands):** read its Agent Canvas integration and self-hosting design online; clone `software-agent-sdk`, not the high-star frontend/control-center repository, for Controller internals.
- **[Aider-AI/aider](https://github.com/Aider-AI/aider):** read `aider/repo.py` and the Git integration documentation for commit attribution and UX. Its local auto-commit/raw-Git model conflicts with the Controller-only Git authority.

### Do not use as primary architectural references

- **CrewAI:** useful as a general Agent/Flow framework and has checkpointing documentation, but it does not primarily solve protected Git delivery, OS sandboxing, evidence-bound Gates, or source-control approval.
- **AutoGen:** useful for message-based teams, termination conditions, and save/load state, but its team-chat abstraction is not a durable software-delivery state machine; the root repository's CC-BY-4.0 license also warrants extra care before copying source.

They can be consulted for a narrow question, but their star counts do not justify permanent local clones for this project.

## Prioritized changes before implementation

1. **P0 — Durable protocol:** accept the command/event/inbox/outbox/lease/fencing/idempotency model.
2. **P0 — Runtime security:** accept Stage capability profiles and distinguish worktree isolation from runtime sandboxing.
3. **P0 — Delivery:** accept a separate Remote Delivery Adapter and Git-host protected branch as final merge authority.
4. **P0 — Artifact model:** accept immutable manifests, content hashes, provenance, and retention/access rules.
5. **P1 — Baseline drift:** split planning and integration baselines; add merge-queue/revalidation behavior and material-change routing.
6. **P1 — Human Gates:** consolidate PRD/design/test-plan review into one solution-baseline Gate; retain final Git-host MR approval; make other reviews conditional.
7. **P1 — Retry taxonomy:** define retryable infrastructure failures separately from semantic rework and human waits.
8. **P2 — Reference management:** add ignored shallow clones plus a tracked pin/license manifest, limited to the four repositories above.

## Overall verdict

The project is not fundamentally off the mainstream path. Its principal strengths—deterministic authority, immutable commit identities, independent verification, and reduced Agent Git privilege—are appropriate for a production harness.

The design currently over-specifies role-by-role workflow and under-specifies durable execution, runtime containment, effect idempotency, artifact provenance, and integration delivery. Correcting those seams will have more impact than adding more Agents or more routine human approvals.
