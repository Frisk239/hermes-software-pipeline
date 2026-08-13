# Slice 00-04 Closeout — Domain and Persistence Spikes

Status: `ACCEPTED`

Contract revision: `7`

Base SHA: `32b4b7a5406bf4ee58b79e2602f77af78ba3a27f`

Candidate SHA: `1e1b7ad95bf79ebbcf9b14e7b470e445d4637105`

Integrated SHA: `46798d86a2e48551a3a634e93d1e4dfe5cbf8786`

Pull Request: [#9 — feat: implement slice 00-04 domain and persistence spikes](https://github.com/Frisk239/hermes-software-pipeline/pull/9)

Closed: 2026-08-13 (backfilled after integration; implementation merged 2026-08-10)

## Accepted capability

- CounterSpike domain evaluator is pure and deterministic; Controller talks only through `ControllerCommandPort.submit`;
- one atomic SQLite transaction covers Inbox, Events, projection, and Outbox, with duplicate-command, revision-conflict, crash, WAL, backup, and fencing evidence;
- declared single-writer workload envelope and SQLite version gate (uv-managed CPython 3.12.13 / WAL-reset predicate) are recorded;
- LangGraph checkpoint/replay cannot independently advance Controller state;
- spike code is disposable except where later Slices explicitly adopt it; runtime `[project].dependencies` stay empty.

## Evidence

- implementation Candidate `1e1b7ad95bf79ebbcf9b14e7b470e445d4637105` on Base `32b4b7a5406bf4ee58b79e2602f77af78ba3a27f`; merge commit `46798d86a2e48551a3a634e93d1e4dfe5cbf8786` (PR #9);
- planning CCR revision 7 pinned uv-managed CPython 3.12.13 after revision 6 `BLOCKED_CONTRACT` on Windows SQLite 3.49.1;
- this Closeout is appended after the fact so 00-07 intake has a durable predecessor record. It does not rewrite the accepted Candidate or review.

## Residual debt

- unproven spike paths must not become production foundation without Slice 00-07 adoption;
- Linux `sqlite3.sqlite_version` remains bound to CI logs rather than a second hardcoded number in compatibility-targets;
- no Execution Report / Review Verdict files were committed in the slice directory.

## Next prerequisites

- Slice 00-05 used `46798d86` as its execution Base;
- Slice 00-07 revalidates EC-00-04/05/06 on the integrated tree and decides retain/delete for domain, controller, persistence, and stage_executor spikes.
