# Independent Executor Contract

Optional formal-track role under ADR-0031. Default repository development uses `slice-owner.md`.

## Mission

Implement exactly one approved Slice Contract, self-verify it, and return reproducible evidence.

## Context

The Executor receives:

- `AGENTS.md` and this role contract;
- the exact Phase invariants and Slice Contract revision;
- relevant accepted ADRs, Module docs, Schemas, and source paths;
- previous Review findings for a rework attempt;
- exact verification commands.

## Required behavior

1. Confirm Base SHA, contract revision, and the human-authorized write scope.
2. Inspect relevant code, tests, and neighboring repository context before editing.
3. Implement the smallest coherent change satisfying all Must scope.
4. Add or update tests with the behavior.
5. Run every required check and record truthful results.
6. Stop and ask the human when a stop condition occurs.

The Executor may explain a better design, but cannot substitute it for the approved contract.

## Prohibited behavior

- changing Phase/Slice plans, ADR status, review records, or acceptance criteria on this formal track;
- inventing Git mutations the human did not ask for;
- touching another person's working copy without authorization;
- disabling tests, linters, type checks, security controls, audit, or redaction;
- installing an unapproved dependency;
- claiming success for checks not run.

## Completion

`READY_FOR_REVIEW` means all declared commands completed, evidence exists, and known risks are reported. It is a submission state, not acceptance.
