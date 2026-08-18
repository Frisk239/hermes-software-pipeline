# Phase and Slice Engineering Operating Model

This document governs development of Hermes Software Pipeline itself. It is separate from the production Pipeline that the plugin will eventually provide to its users.

Engineering **Phase**, **Slice**, **Execution Attempt**, and **Review Attempt** must never be stored or displayed as runtime Pipeline **Stage**, **Stage Attempt**, or **Execution Run**. They are two different state systems.

**Default mode is Slice Owner (ADR-0031).** A human-authorized session may plan, implement, and self-check one cut. The former Codex / Executor / Git Custodian split is an optional formal track, not a start-work gate. If this file conflicts with `AGENTS.md` or ADR-0031, those win.

The intended default collaboration is:

```text
Human Product / Governance Owner
        ↓ authorizes one cut
Slice Owner session
        ↓ plans, implements, self-checks; may push feat/* when asked
Human
        ↓ reviews and merges
```

Chat is useful for authorization. Durable facts still belong in the repository: ADRs, code, tests, and a short progress note when the next session will need them.

## Planning horizons

The project still uses three planning horizons. They are maps, not jail cells.

| Horizon | Purpose | Detail level |
| --- | --- | --- |
| Roadmap | Order major product capabilities and dependencies | Outcomes and Phase exit conditions |
| Phase Plan | One coherent engineering capability | Slice names, dependencies, demonstrations, Phase Gate |
| Slice / cut | One demoable path or decisive feasibility result | Must / Out, tests, and how to prove the path |

A Phase is a coherent capability boundary, not a calendar period. A Slice is a thick vertical cut, not a layer-shaped task such as “create database models” with no exercised consumer.

Work-in-progress is limited by real collision risk, not by a WIP=1 rule. Concurrent cuts are allowed when the human accepts overlapping paths.

## Default: Slice Owner

Before changing files, the Owner:

1. knows which cut the human authorized and what is out of scope;
2. reads `CONTEXT.md`, `AGENTS.md`, and the accepted ADRs that bind the change;
3. works on a feature branch from the current default line unless the human says otherwise.

The Owner may edit any tracked path needed for the cut. A machine Slice Contract, Context Manifest, Evidence Bundle, `content_hash`, assigned Managed Worktree, and typed review verdict are optional.

Git: do not commit or push unless the human asks. When asked, push `feat/*`. Do not push the default branch unless the human explicitly authorizes that path.

## Optional formal track

When the human wants a split review, the older flow remains available:

```text
Human
        ↓ approves Phase intent and material changes
Planner-Designer-Reviewer
        ↓ plans and reviews; does not silently become the implementer
Independent Executor
        ↓ edits the assigned worktree and returns evidence
Git Custodian / protected repository workflow
        ↓ records the Candidate and controls merge
```

On that track only:

- Markdown plans may be paired with the versioned engineering schemas under `schemas/engineering/`.
- The Executor edits the contract's permitted paths inside the assigned Managed Worktree.
- Review returns exactly `PASS`, `REWORK`, or `BLOCKED_CONTRACT`.
- A sound `REWORK` stays with the Executor for up to two recorded attempts under the same contract revision.
- A post-merge downstream decision audit may be used when the integration actually invalidates later plans.

Role contracts live in `docs/agents/roles/` and are selected explicitly. The project does not depend on `AGENTS.<role>.md` discovery.

## Change control

- A clarification that preserves approved semantics may proceed in the same cut.
- New product behavior, a new dependency family, a new external authority, or an Interface-breaking decision needs an explicit human decision and usually an ADR.
- A formal Contract Change Request file is optional under ADR-0031.
- Findings outside the authorized cut become later work; they do not silently expand the current change.
- An accepted historical record is never edited retroactively. Corrections are a new note, a new cut, or a recorded rework.

## Readiness

A cut is done when the authorized path works, required checks for that path are green or the residual debt is explicit, and secrets stayed out of git.

A Phase is complete when its required cuts are in the default branch, cross-cut integration holds, and normative docs match the code.

## Anti-patterns

- planning every implementation task for the whole product before the first cut;
- one Slice per architectural layer rather than per observable path;
- weakening tests to make a change pass;
- treating chat as the only record of a hard decision;
- using this operating model to re-impose path jails, dual-role bans, or mandatory audits on an Owner-mode cut;
- changing product Git isolation, Controller authority, or Stage trust boundaries under the guise of repository-process lightening.
