# Phase 5 quality campaign

Execution contract for the next session: **do every remaining cut below, then one live test.**  
Does not replace `ROADMAP.md` or ADRs. No Dashboard / Feishu UI.

Grounded in `docs/research/2026-08-complete-pipeline-oss-gap.md` (OpenHands verification stack, SWE-agent harness, MetaGPT artifact SOP).

## Already shipped (do not redo)

| Cut | On `main` | What it closed |
|---|---|---|
| 05-21 … 05-27 | yes | `gh` PATH, OpenCode `-p`/exe, stage duties, harvest, timeout harvest, `src/`-only publish |
| 05-28 / 05-29 | yes | Run `src/app.py` / `pytest`; no evidence → REWORK; publish only if READY |
| 05-30 verify-stable | CI / merging | Script pass skips reviewer spawn; verify exceptions → REWORK |

Operator path today: `submit` → real PRD/Arch → `approve` → `src/` → scripted verify → GitHub PR.

## Rules for every cut

- Thick: one operator-visible path, fake bindings stay green, real bindings fail-closed.
- Stack `feat/*` on the previous feat tip while CI runs. Human merges `main`.
- Do not merge PRs inside adapters. Do not add UI.
- Do not weaken or skip tests.

## Remaining cuts (do all four, then test)

### 05-31 Rework once

**Path:** real `src/app.py` exits 1 → `verify_status=REWORK` → same `pipeline_id` automatically runs Development once more → verify again → READY or stay REWORK.

**Must**

- Persist `verify_attempts` (cap = 1) under the pipeline descriptor.
- Scripted verify tries `python src/app.py --check` first (exit 0 = pass); if that flag is unsupported, fall back to bare `src/app.py` (20s). Web apps must implement `--check`.
- On first REWORK, clear `_dev` for that pipeline and `_advance_development` + `_advance_verify` again in the same `approve` (or a `hermes pipeline retry` if approve already returned).
- Prefer `retry` command if same `approve` would exceed the 600s client budget: `hermes pipeline retry --pipeline-id …` allowed only when status is REWORK and attempts < 1.
- Fake bindings never enter rework (still READY first pass).

**Out:** unlimited loops, critic model, Chrome.

**Accept:** unit: failing script then a second executor write that passes → READY, attempts=1. Live later.

### 05-32 Honest delivery and approval

**Path:** `read` after READY PR shows `check_status` / `merged` from `gh`, not operator `--check` injection. `VIEWER` `approve` is denied. Restart still shows `approver_id`.

**Must**

- Host `gh pr view --json state,mergeStateStatus,statusCheckRollup,reviews` overlay into `read` (no token in kernel).
- Ignore or stop treating `op=deliver --check/--review/--queue` as source of truth when `github.json` is set.
- `SolutionApproval`: deny if role is `VIEWER`. Dump/load designated+approved with `approvals.json` (already have status; persist the artifact triple so `is_fresh` survives restart).
- Still no `gh pr merge`.

**Out:** webhooks, GitHub App, Feishu.

**Accept:** unit with fake `gh` runner. Restart KernelBridge: `is_fresh` true. VIEWER approve → `ok=False`.

### 05-33 Kernel owns later stages

**Path:** after approve+READY, `stop`/`start`, `read` still has approval/dev/verify. Corrupt `prd.json` does not silently look like a new pipeline.

**Must**

- JSON loads that are corrupt return error to `read`/`approve` (fail-closed), not `{}`.
- Record approve / dev / verify facts in the same persist set used today **and** a single `stages.json` (or kernel projection fields) so one file cannot drop verify while keeping APPROVED.
- Optional if small: submit `APPROVE_BASELINE` as a kernel command type. If that needs a domain ADR/state enum, stop at fail-closed persist + projection fields; do not invent states without ADR.

**Out:** Temporal, multi-replica, full event-sourcing rewrite.

**Accept:** overwrite `verify.json` with `not-json` → `read` errors or reports `UNCONFIRMED`/`error`, not fake READY. Restart keeps the triple.

### 05-34 Runtime honesty and sandbox jail

**Path:** OpenCode `returncode != 0` is FAILED (PRD/dev DENIED unless harvest still finds `src/`). Verify subprocess cannot write `../escape`. Codex prompted timeout ≥ 120s.

**Must**

- `OpenCodeAdapter`: nonzero exit → `FAILED` (keep harvest-on-timeout for `src/`).
- `CodexAdapter` prompted timeout 120s (or share `_PROMPT_TIMEOUT_S`).
- Verify `run` / pytest / OpenCode `cwd` is sandbox root; reject writes whose resolve escapes sandbox (reuse worktree escape).
- `stage_tree` only `src/` and `tests/`.

**Out:** Docker, new CLI families, browser.

**Accept:** unit: OpenCode fake script `raise SystemExit(1)` → FAILED. Verify write `../x` denied.

## Final live test (after all four are on `main`)

**Requirement (real small web app, not a one-line CLI):**

> Build a parking-lot staff login web app. Write PRD.md. After approval, implement it under `src/`.  
> Must include: a login page (username + password), submit, success page, error on bad credentials.  
> Serve on `127.0.0.1` (stdlib `http.server` is enough; no extra deps).  
> Also support `python src/app.py --check`: start briefly or validate handlers, print `login-ok`, exit 0.  
> Default `python src/app.py` may serve until killed.

`--check` exists so today's scripted verify can READY without hanging on a long-lived server. Browser-click e2e is **after** this campaign (05-35).

**Operator path**

1. `submit` that text → PENDING; `plans/…/prd/PRD.md` and architecture named files exist.
2. `approve` → candidate under `src/` (page + server, not only `print`), `verify_status=READY` via `--check` or `pytest`, `pr_url` set.
3. Hand-check: `python src/app.py --check` prints `login-ok`; optionally open `http://127.0.0.1:8000` and log in.
4. `stop`/`start` → same approval + verify + `pr_url`.
5. `read` shows GitHub-derived check/merged fields (empty is ok if the test repo has no CI).
6. Negative: a pipeline whose check/`src/app.py` exits 1 → REWORK, no new PR; `retry` once can recover.

**Implement prompt hint (05-31+):** if the requirement describes a server, tell the executor to implement `--check` that exits 0 on success so verify can run without a 20s timeout.

## After this campaign (not in the four cuts)

Browser e2e (Chrome MCP), Feishu cards, Dashboard, Docker sandbox, training a critic.

## Session order

`05-31` → `05-32` → `05-33` → `05-34` → live test above. Stack while CI runs. Do not start UI.
