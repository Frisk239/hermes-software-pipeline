---
status: accepted
---

# Stage duties stay fixed; runtime and model are bindings

**Status: accepted.** Repository Governance Owner `Frisk239` accepted this on 2026-08-18; attestation `engadr_0032_20260818_01`.

PRD, Architecture, Development, E2E, and Acceptance remain independent Stages (ADR-0004's *separation* stands). This ADR supersedes ADR-0004 only insofar as those Stages were hard-wired to the Codex CLI.

A Stage is bound to an **Agent Binding**: a runtime family (`codex`, `opencode`, or `fake`) plus a model identifier. Examples: planner → OpenCode / grok-4.6, or Codex / gpt-5.6-sol; executor → OpenCode / deepseek, or Codex / gpt-5.6-luna.

Bindings are configuration resolved before an Execution Run. Changing a binding creates a new Run. An Agent cannot retarget its own runtime or model mid-run.

Unsupported runtime/model pairs fail closed. Codex and OpenCode remain Adapter implementations behind `RuntimeBrokerPort`, not Stage names.

Product Controller authority, Git isolation, and capability profiles are unchanged.
