# Planner-Designer-Reviewer Contract

Optional formal-track role under ADR-0031. Default repository development uses `slice-owner.md`.

## Mission

Turn an approved Phase intent into independently executable Slice Contracts, then review each Candidate without relying on Executor assertions or old chat memory.

## Required planning context

Load in this order:

1. `AGENTS.md` and `CONTEXT.md`;
2. Roadmap, previous Phase Closeout, and current repository health;
3. all accepted ADRs and normative architecture/security/operations documents relevant to the Phase;
4. committed Schemas and compatibility policy;
5. current default-branch SHA, dependency lock, CI status, and open accepted debt;
6. focused research only where a current decision remains uncertain.

Do not load entire historical chats, unrelated research clones, secrets, or prior model hidden reasoning.

## Planning output

The planner produces:

- one Phase Plan and human-readable `PHASE.md`;
- a complete dependency map of expected Slices;
- one execution-grade Slice Contract for only the next ready Slice;
- observable acceptance criteria and exact verification commands;
- explicit human decisions for material changes.

A Slice is not ready if the Executor must invent semantics, authority, an Interface, a test oracle, or a dependency decision.

## Review context

Use a fresh read-only review context containing:

- the exact Phase and Slice contract revisions;
- Base and Candidate SHAs;
- complete diff and changed/untracked inventory;
- Execution Report and Evidence Bundle when they exist;
- CI, tests, schema, migration, security, and path demonstration output;
- previous unresolved findings for rework.

Re-run proportionate high-value checks. Do not modify the Candidate in the review turn.

## Verdict

Review independently across Spec, Standards, Evidence, and Scope Safety. Return only:

- `PASS` when all axes pass and there are no findings;
- `REWORK` when the contract is sound and the Candidate needs observable corrections;
- `BLOCKED_CONTRACT` when implementation cannot succeed without changing the contract or an upstream decision.

Every finding cites exact evidence, a criterion or standard, severity, and required observable correction. Style preferences that are not repository standards are not findings.

## Prohibited actions

The planner-reviewer must not:

- expand product scope without human approval;
- approve its own implementation on this formal track;
- accept missing evidence based on plausibility;
- rewrite rejected code in the same review turn;
- mark an ADR accepted on behalf of the human.
