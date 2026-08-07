# Slice 00-03 Closeout — Contract Toolchain

Status: `ACCEPTED`

Contract revision: `7`

Base SHA: `f36ba6a2930267e2d90682ff61930c82fd1237bb`

Candidate SHA: `e43840edb1bb2bd9ba0a8029085153f169ff93ba`

Integrated SHA: `32b4b7a5406bf4ee58b79e2602f77af78ba3a27f`

Pull Request: [#6 — feat: add contract toolchain (slice-00-03)](https://github.com/Frisk239/hermes-software-pipeline/pull/6)

Closed: 2026-08-06

## Accepted capability

- the 14 committed Draft 2020-12 Schemas are deterministic projections of
  Pydantic v2 authoring types; their `$id` identities remain locked at `/v1`;
- committed OpenAPI 3.1 and compatibility-registry projections are generated
  from that authoring source and protected by an offline byte-drift check;
- the contract toolchain validates immutable baseline snapshots, the committed
  corpus, `$ref` closure, JSON Schema meta-validity, migration identity rules,
  RFC 8785 golden vectors, and secret-canary redaction without network or
  credentials;
- `contracts` imports Pydantic, jsonschema, and RFC 8785 support only after
  its subcommand is parsed. The normal runtime path and `--version` remain
  standard-library-only, and missing development dependencies produce bounded
  safe errors;
- Schema instance validation uses a fresh local RFC 3339 `FormatChecker` per
  validator. A fresh-process regression proves imports never mutate
  `Draft202012Validator.FORMAT_CHECKER`;
- the frozen command set, artifact audit, and documentation/workflow policy
  checks pass on Windows and Linux.

## Evidence

- final Candidate `e43840edb1bb2bd9ba0a8029085153f169ff93ba` passed the full
  frozen local command set, including 149 pytest cases, contract check,
  offline drift check, architecture check, bootstrap/documentation checks,
  workflow policy, artifact audit, and `git diff --check`;
- Candidate CI bound to `e43840e` passed on both operating systems:
  [python-quality push](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/31086806870),
  [python-quality PR](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/31086810380),
  [documentation-contracts push](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/31086807005),
  and [documentation-contracts PR](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/31086811778);
- PR #6 merged as `32b4b7a5406bf4ee58b79e2602f77af78ba3a27f`; integrated
  `main` CI passed [python-quality](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/31088258476)
  and [documentation-contracts](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/31088258806)
  on Windows and Ubuntu;
- the final Candidate and integrated tree were reviewed across Spec, Standards,
  Evidence, and Scope Safety. The first candidate was returned through two
  Executor rework attempts; the final eight-path local-`FormatChecker` repair
  was a separately reviewed bounded Codex corrective attempt under the
  repository rework rule.

## Residual debt

- Pydantic, jsonschema, and `rfc8785` remain development/CI-only dependencies
  under ADR-0026. They are not installed or imported by the Hermes-loaded
  runtime path; runtime dependency installation and isolation remain a later
  design decision;
- `contracts check` and `architecture check` still require a source checkout
  for their repository-owned inputs. A standalone installed wheel supports
  `--version`, not those source-validation commands;
- no Controller aggregate, durable Inbox/Event/Projection/Outbox store,
  lease/fencing mechanism, migration implementation, or LangGraph execution
  behavior was introduced. Those feasibility boundaries remain owned by Slice
  00-04;
- the dependency-free bootstrap Schema checker remains intentionally separate
  from the full contract validator and continues to lock the same 14 Schema
  identities.

## Next prerequisites

- Slice 00-04 uses integrated SHA
  `32b4b7a5406bf4ee58b79e2602f77af78ba3a27f` as its planning and
  implementation Base;
- the Slice 00-04 Contract must declare its SQLAlchemy/Alembic/LangGraph
  dependency isolation, SQLite workload envelope, fault-injection evidence,
  and explicit retain-or-delete disposition for every spike component before
  an Executor is assigned;
- the Slice 00-03 Candidate, planning Candidate, PR, CI, and Closeout evidence
  are durable. Its managed worktrees may be removed only after the 00-04
  planning artifacts containing this Closeout are integrated.
