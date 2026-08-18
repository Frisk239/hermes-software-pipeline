---
status: accepted
---

# Slice Owner is the default way this repository is developed

**Status: accepted.** Repository Governance Owner `Frisk239` accepted this decision on 2026-08-18; attestation `engadr_0031_20260818_01`. The human authorized Slice Owner mode and writes to any tracked path needed for the authorized cut.

This decision governs **how maintainers build this repository**. It does not change the production Pipeline: Controller authority, Stage isolation, user-project Git isolation, and ADRs 0001–0030 remain binding for product behavior.

## Decision

The default engineering mode is **Slice Owner**: one human-authorized session may plan, implement, self-check, and (when the human asks) commit or push a single cut.

The Codex planner / independent Executor / Git Custodian split, machine Slice Contracts, Context Manifests, Managed Worktrees, typed `PASS`/`REWORK`/`BLOCKED_CONTRACT` reviews, mandatory post-merge downstream audits, and formal Contract Change Request documents are an **optional formal track**. They are not start-work gates.

## What is relaxed

- A human-authorized Owner may combine planning and implementation in one session.
- The Owner may edit any tracked path needed for the authorized cut. `permitted_paths` does not jail Owner-mode work.
- Coding agents may commit and push `feat/*` when the human explicitly asks. They still must not invent Git mutations, push the default branch, or hold remote credentials unless the human grants that rare path.
- Work may proceed in the human's checkout or feature branch. A clean assigned Managed Worktree is not required to start.
- Concurrent cuts are allowed when the human accepts the collision risk.
- Informal review is enough for Owner-mode cuts. The three-state verdict remains available on the formal track.
- A human decision in session, recorded in an ADR or a short progress note, is enough to change repository process. A separate CCR file is optional.
- Owner-mode work does not need `content_hash`, RFC 8785 canonicalization, Context Manifest digests, Evidence Bundles, or other engineering-harness hash theater. A git commit SHA is enough when a result must be named. Product Artifact Manifest hashing is unchanged.

## What stays hard

- Only a human accepts hard-to-reverse architecture, security, dependency-family, licensing, or product-scope changes.
- Accepted ADRs and committed Schemas bind until a human supersedes them.
- Do not weaken, skip, delete, or mark tests to make a change pass.
- Do not commit secrets, credentials, raw private Project content, or sensitive evidence.
- Do not edit accepted planning, review, evidence, or closeout records retroactively; append a new note.
- Keep the product Controller deterministic. LangGraph stays inside Stage execution.
- Do not add ambient filesystem, network, secret, Git, provider, approval, or merge authority to the product.
- New dependency families or Interface-breaking product changes still need an ADR.

## Supersession

For this repository's development process, this ADR supersedes the dual-role, path-jail, Custodian-only commit, Context Manifest start-gate, WIP=1, mandatory three-state review, mandatory post-merge audit, and engineering-harness hash/evidence-bundle rules in `AGENTS.md`, `docs/development/phase-and-slice-operating-model.md`, `docs/agents/roles/`, `CONTRIBUTING.md`, and the engineering-language section of `CONTEXT.md`.

Those documents now describe Slice Owner as the default and the former flow as optional. Product ADRs 0001–0030 are not superseded.
