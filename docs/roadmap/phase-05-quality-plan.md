# Phase 5 quality plan (post 05-28)

**Superseded for execution.** Remaining cuts and the final live test live in `docs/roadmap/phase-05-quality-campaign.md`. Keep this file only as the 05-28-era snapshot.

- After: `origin/main` `6f9f03f` (05-28 merged)
- Does not replace `ROADMAP.md` or ADRs. This is the next **execution order** for core pipeline quality. No Dashboard/UX.

## Where we are

Operator path works: `submit` → PRD/Arch → `approve` → bound executor writes `src/` → scripted `python src/app.py` → host `gh` PR.

Still thin: verify skip/timeout can READY; bound e2e/reviewer not launched live; approve `ok` even if verify is REWORK; kernel is intake-only; no GitHub check/merge observation.

## Rules

- One thick cut per session. Stack `feat/*` while CI runs. Human merges `main`.
- Fake bindings stay deterministic. Real bindings fail-closed without evidence.
- Do not merge/approve PRs inside adapters.
- Do not add UI until this plan’s Wave A–B are green on a live requirement.

## Wave A — Verify is real (next)

| Slug | Demo | Must | Out |
|---|---|---|---|
| **05-29 verify-evidence** | Fake still READY. Real e2e: missing `src/app.py` / timeout / no RESULT → **not** READY. `pytest` runs when `tests/` exists. | Launch bound e2e/reviewer (drop `_PassingRuntime` for non-fake). Read `RESULT.md` / `REVIEW.md`. Publish only if `verify_status=READY`. Approve receipt reflects REWORK. | Chrome MCP, critic model, iterate loop |
| **05-30 rework-once** | Script fail → `REWORK` → one bounded re-dev → verify again. | Persist attempt count. Cap = 1. Same pipeline id. | Unlimited agent loops |

**First session after this plan: 05-29.**

## Wave B — Delivery is honest

| Slug | Demo | Must | Out |
|---|---|---|---|
| **05-31 observe-github** | `read` shows host check/review/merged from `gh`, not operator-injected fields. | Poll `gh pr view` / checks. Still no merge API. | Webhooks, GitHub App |
| **05-32 approve-auth** | VIEWER cannot `approve`. Restart still knows who approved. | Persist `SolutionApproval`. Deny VIEWER. | Feishu cards |

## Wave C — Kernel owns the later stages

| Slug | Demo | Must | Out |
|---|---|---|---|
| **05-33 stage-events** | Restart after approve: Controller projection includes approval/dev/verify, not only `OPEN`. | Commands + events for approve/dev/verify. Live store = SQLite (or keep JSON but stop fail-open empty). | Multi-replica, Temporal |
| **05-34 adapter-honesty** | OpenCode nonzero exit is FAILED. Codex prompted timeout ≥ 120s. | Match ProcessAdapter fail-closed. | New CLI families |

## Wave D — Isolation (after A–C)

| Slug | Demo | Must | Out |
|---|---|---|---|
| **05-35 sandbox-profile** | Verify cannot write outside sandbox cwd. | Process + cwd jail. | Docker/K8s |
| **05-36 browser-e2e** | Parking-lot login page exercised via Chrome MCP in sandbox. | Only if 05-29 green. | Full OpenHands critic |

## Done when (core, still no UI)

A second live requirement (not the fixture `login-page`) shows: real PRD/Arch files, `src/` candidate, verify **ran tests or script** (not skip), PR opened **only after READY**, `read` shows GitHub check state, restart does not forget approval.

## Do not pull in

Dashboard, Feishu product UI, MetaGPT PM/CEO roles, Multica, training a critic model, merging from the pipeline.