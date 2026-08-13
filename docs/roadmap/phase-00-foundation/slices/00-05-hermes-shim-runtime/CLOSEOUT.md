# Slice 00-05 Closeout — Hermes Shim and Runtime Spike

Status: `ACCEPTED`

Contract revision: `5`

Base SHA: `46798d86a2e48551a3a634e93d1e4dfe5cbf8786`

Candidate SHA: `b000731b0fe49c9231af6216838951d451550faf`

Integrated SHA: `102d08f814b6c0a939662e6c488870310a97c1ee`

Pull Request: [#11 — feat: implement slice 00-05 hermes shim and managed runtime](https://github.com/Frisk239/hermes-software-pipeline/pull/11)

Closed: 2026-08-13 (backfilled after integration)

## Accepted capability

- thin Hermes plugin manifest and `register(ctx)` Shim with no Pipeline authority;
- managed-runtime bootstrap/locate/start/status/stop and protected loopback transport;
- descriptor ACL/mode, random port/token, protocol negotiation, and stale cleanup;
- Feishu synthetic `/card` interception probe without Prod Main;
- lifecycle survives kill/restart without forging or losing an acknowledged fake result;
- ADR-0028 authorizes FastAPI/Uvicorn only inside the managed runtime, not the Hermes-loaded Shim.

## Evidence

- implementation Candidate `b000731b0fe49c9231af6216838951d451550faf` on Base `46798d86a2e48551a3a634e93d1e4dfe5cbf8786`; merge commit `102d08f814b6c0a939662e6c488870310a97c1ee` (PR #11);
- planning landed via PR #10; independence vs 00-04 was serial (`tests/` and `compatibility-targets.md` shared);
- this Closeout is appended after the fact so 00-07 intake has a durable predecessor record. It does not rewrite the accepted Candidate or review.

## Residual debt

- no committed slice-directory Execution Report or Review Verdict;
- Shim/runtime spike remains `SPIKE-EXPERIMENTAL` until 00-07 adopts, rewrites, or deletes it;
- EC-00-07/11 path demonstration must be revalidated on the 00-07 integrated Candidate.

## Next prerequisites

- Slice 00-06 used planning Base `9cf24b876cc7422386ed54c277900ff1e3c2c2bf` (after PR #12) with 00-05 already merged beneath it;
- Slice 00-07 must not edit `hermes_shim/`, `transport/`, or `runtime-env/` except under an approved 00-07 contract.
