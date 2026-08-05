# Slice 00-01 Closeout — Repository Baseline

Status: `ACCEPTED`

Contract revision: `5`

Base SHA: `7f2bcff881e7d16477f0bc1ae0d2a6aa1de3cab0`

Candidate SHA: `0d946abf73736d6a03c6b33433714c51b79dadaa`

Integrated SHA: `6c9623a3a8ad6a124d5d4a1bcddce94a5938e0b4`

Pull Request: [#1 — ci: establish repository baseline checks](https://github.com/Frisk239/hermes-software-pipeline/pull/1)

Closed: 2026-08-05

## Accepted capability

- repository text is normalized to LF across Windows and Linux;
- dependency-free bootstrap checkers validate governed documentation and the 14 committed bootstrap Schemas;
- positive and deliberately invalid fixtures prove deterministic acceptance and rejection paths;
- the documentation workflow runs the same offline checks on Windows and Linux with read-only permissions and no persisted checkout credentials;
- root documentation, contribution guidance, the documentation map, Schema guidance, and the readiness audit describe the executable baseline.

## Evidence

- Candidate push CI: [run 30981733800](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/30981733800), Windows and Ubuntu `success`;
- Pull Request CI: [run 30982206691](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/30982206691), Windows and Ubuntu `success`;
- integrated `main` CI: [run 30982258688](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/30982258688), Windows and Ubuntu `success`;
- Candidate changed exactly 64 permitted paths, passed staged-tree and line-ending checks, and introduced no symlink, cache, credential, runtime, or application behavior;
- final review passed Spec, Standards, Evidence, and Scope Safety after three implementation attempts.

## Residual debt

- full Draft 2020-12 meta-schema validation, Pydantic authoring, generated Schema/OpenAPI drift, compatibility fixtures, and canonical hashing remain owned by Slice 00-03;
- the workflow parser intentionally accepts only the committed workflow's strict YAML subset;
- repository-root documentation discovery currently scans ignored local directories such as `reference/`; Slice 00-02 must make governed-file discovery honor repository exclusions and add regression coverage;
- historical Executor and review evidence existed as reports and CI records rather than complete machine-valid committed Execution Report, Review Verdict, and Evidence Bundle artifacts. Slice 00-02 must not repeat this evidence gap.

## Next prerequisites

- Slice 00-02 uses integrated SHA `6c9623a3a8ad6a124d5d4a1bcddce94a5938e0b4` as its implementation Base;
- the local main worktree is synchronized and clean;
- the accepted Slice 00-01 worktree remains available until this Closeout and the Slice 00-02 planning artifacts are committed;
- Python `>=3.12,<3.13` and `uv 0.12.1` are the managed-runtime bootstrap targets;
- required checks must remain credential-free and run on Windows and Linux after the single dependency-install step.

## Planning adjustment

The repository uses one integration branch, `main`, rather than maintaining an unused `next` branch. Development reaches `main` only through reviewed Pull Requests. A merge is not a release: production installation and update discovery remain bound to a separately gated signed version tag and release manifest.
