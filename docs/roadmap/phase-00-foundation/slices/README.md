# Phase 00 Slice Design

These are planning-level Slice definitions. Codex expands only the next dependency-ready Slice into a machine-valid immutable Slice Contract using the exact current Base SHA.

Slice 00-04 was accepted and integrated at `46798d86a2e48551a3a634e93d1e4dfe5cbf8786` (PR #9), and Slice 00-05 was accepted and integrated at `102d08f814b6c0a939662e6c488870310a97c1ee` (PR #11). Slice 00-06 is READY at planning revision 14, bound to Base `9cf24b876cc7422386ed54c277900ff1e3c2c2bf` with a clean assigned execution worktree; its planning package has not yet integrated into `main`.

Every Slice integration triggers the post-merge downstream decision audit defined in `docs/development/phase-and-slice-operating-model.md`. The 00-05 → 00-06 transition predates that rule, so its first append-only audit record is backfilled in `00-06-agent-runtime-security-spikes/downstream-audit.md`. Append-only revision 10 records the r14 READY review and Git Custodian worktree assignment; revisions 11-12 bind the synchronized identities and final Codex Responses interface; revision 13 records the final projection synchronization; no `UPDATED` or `CCR_REQUIRED` item remains open.

## 00-01 Repository baseline

Must deliver:

- confirmed repository/distribution/import names and `main` default branch;
- README with product promise, trust limits, source-install outline, and status;
- license, contribution, security-reporting, support, code-of-conduct, and governance policy;
- documentation index identifying normative vs proposed documents;
- JSON Schema syntax/reference validation for the existing contract set;
- corrected portable text encoding and ASCII-safe tree examples;
- CI that checks documentation links and Schema parse/reference integrity.

Out: Python runtime behavior, dependency selection changes, production code.

Demonstration: a clean clone on Windows and Linux identifies every normative entry point and rejects an intentionally broken Schema fixture.

## 00-02 Python quality skeleton

Must deliver:

- `pyproject.toml`, fully frozen `uv.lock`, package skeleton, CLI entry point, and version source;
- centrally configured Ruff, Pyright, pytest, pytest-asyncio, and Hypothesis;
- canonical local commands and GitHub Actions matrix;
- deterministic time/identity/temp-root test fixtures;
- architecture import-boundary check.

Out: Controller rules, HTTP server, database tables, LangGraph workflow, real Agent invocation.

Demonstration: the documented frozen commands pass from a clean clone without credentials or internet after dependency installation.

## 00-03 Contract toolchain

Must deliver:

- versioned Pydantic v2 authoring models with deterministically generated committed JSON Schema and OpenAPI projections;
- Schema reference resolution and committed minimal/maximal/invalid fixtures;
- RFC 8785 canonical JSON and hashing golden vectors;
- compatibility-range registry and migration Interface;
- OpenAPI/schema drift check;
- redaction/leakage fixtures.

Out: business transitions and persistent Event storage.

Demonstration: valid fixtures round-trip identically; unknown fields, stale versions, malformed identities, and secret canaries fail deterministically.

## 00-04 Domain and persistence spikes

Must deliver disposable but tested feasibility code and a decision report for:

- pure aggregate command evaluation and typed results;
- one atomic SQLite transaction covering Inbox, Events, projection, and Outbox;
- duplicate command, expected-revision conflict, crash-point, WAL, backup, and projection rebuild;
- single-writer workload with declared queue depth and latency;
- Stage Attempt/Run lease plus fencing;
- LangGraph checkpoint namespace, interrupt, resume, and replay with Controller authority demonstrably external.

The final Slice Contract must name which spike code is retained and which is deleted. Unproven spike code cannot silently become production foundation.

Demonstration: a fault-injection scenario restarts at every durable boundary without duplicate transition or stale advancement.

## 00-05 Hermes Shim/runtime spike

Must deliver:

- minimal valid Hermes plugin manifest and `register(ctx)` Shim;
- managed-runtime bootstrap/locate/start/status/stop protocol;
- loopback descriptor ACL/mode, random port/token, protocol negotiation, body/rate limits, and stale cleanup;
- Feishu synthetic `/card` command interception probe without invoking Prod Main;
- packaged source-install and isolated-dependency feasibility evidence;
- failure behavior when runtime, token, version, or descriptor is invalid.

Out: production Feishu UI and any business approval.

Demonstration: a real local Hermes Gateway delivers one authenticated fake command exactly once; killing/restarting either process does not forge or lose an acknowledged result.

## 00-06 Agent/runtime security spikes

Status: READY (revision 14) — contract and manifest remain planning-branch artifacts and are not yet on `main`. ADR-0029 and ADR-0030 are accepted. Revision 14 pins real CLI probes, exact controlled E2E behavior, a closed authorization digest chain, and complete isolation evidence; fresh independent Standards/Spec review passed and the Git Custodian assigned the clean execution worktree at the exact Base.

Must deliver:

- typed Codex and OpenCode CLI Adapter probes with version/capability detection;
- structured result, timeout, cancellation, process-tree cleanup, bounded output, and redaction;
- Windows and Linux capability-enforcement evidence for filesystem, environment, executable, network, and secret boundaries;
- OpenCode plus Chrome DevTools MCP isolated E2E probe;
- hostile repository, argument-injection, path escape, and secret-canary tests;
- explicit gaps and fallback policy when an OS cannot enforce a capability.

Out: production role prompts, quality evaluation, or application-specific E2E.

Demonstration: a malicious fixture cannot mutate Git, escape authorized roots, inherit a canary secret, or leave a child process alive after fencing.

## 00-07 Foundation integration

Must deliver:

- final Module package skeleton and public Interfaces;
- deterministic fake Adapters and shared contract tests;
- lifecycle CLI with non-production `setup`, `doctor`, `start`, `status`, and `stop`;
- full offline Windows/Linux CI, dependency audit, SBOM preview, and artifact retention;
- install/upgrade/rollback compatibility manifest format;
- consolidated feasibility decision report, accepted/replaced ADRs, and Phase Closeout.

Out: Phase 1 business behavior.

Demonstration: a clean install runs a fake command from Hermes through Shim/runtime and back, survives restart, exposes health evidence, and passes all mandatory checks on the exact Candidate.
