# Phase 5 hardening campaign

Execution contract after 05-34 / 05-35. Closes the thin seams in
`docs/research/2026-08-role-prompt-and-thin-seams.md`.

Does **not** replace `ROADMAP.md` or ADRs. Does **not** start Phase 6
(ops/release), Dashboard, Feishu product UI, or Docker.

Ground: four 2026-08-19 explore audits (prompts, loop, adapters, security)
plus OpenHands / SWE-agent / MetaGPT primary sources in that research note.

## Already shipped (do not redo)

| Cut | Status | What it closed |
|---|---|---|
| 05-21 … 05-34 | `main` | `gh` PR, scripted verify, retry-once, VIEWER deny, fail-closed stages, OpenCode nonzero, Codex 120s |
| 05-35 self-test-feedback | feat / this workspace | DEV self-test before Candidate; `feedback.json`; implement prompt can carry last-gate text |

Operator path today: `submit` → PRD/Arch → `approve` → self-test → scripted verify → `retry` once on REWORK → host `gh` PR.

Still thin: duty and untrusted docs are one argv; gates are existence checks; DEV_GATE fail is not retryable; adapters are unfenced `subprocess.run`; capability profiles are not attached.

## Rules for every cut

- Thick: one operator-visible path. Fake bindings stay green. Real bindings fail-closed.
- Stack `feat/*` on the previous feat tip while CI runs. Human merges `main`.
- Do not merge PRs inside adapters. Do not add UI.
- Do not weaken or skip tests.
- Prompts are not the security control (ADR-0015). Isolation work attaches the existing profile; it does not add persona SOPs.
- Do not invent Kernel states, merge authority, or new dependency families without an explicit human + ADR.
- Do not load `docs/agents/roles/` (repo Slice Owner track) into product runtimes.

## Wave E — Station contracts (no ADR)

Handoff first, not longer personas. Five short product contracts + fenced artifacts.

### 05-36 stage-contracts

**Path:** executor prompt starts with a fixed DEVELOPMENT contract. A PRD body that quotes “Write PRD.md then implement src/” cannot change that duty block. PRD harvest is `PRD.md` only (no stdout fallback).

**Must**

- Commit five short contracts next to prompt helpers (e.g. `stage_executor/contracts.py` or `docs/product-stages/` loaded as text): `prd`, `architecture`, `development`, `e2e`, `acceptance`. Each: mission, required files, forbidden files, stop conditions. First block of the prompt only.
- Wrap CAS / intake text in `BEGIN_UNTRUSTED_<KIND>` / `END_UNTRUSTED_<KIND>`.
- Unit: parking-lot intake copied into a PRD artifact still yields an implement prompt whose **duty block** does not say “write PRD.md”.
- `PrdStage`: named `PRD.md` only; drop `final_text` stdout fallback.

**Out:** MetaGPT SOP novels, system-role APIs the bound CLI cannot honor, injecting repo `docs/agents/roles/`.

**Accept:** existing prompt tests plus the fence test above. Fake path unchanged.

### 05-37 harvest-src-only

**Path:** timeout/FAILED OpenCode that only rewrote `PRD.md` or left `README.md` is DENIED. Only `src/**` (and existing `tests/**` as companions) may become a Candidate.

**Must**

- `pick_implementation`: drop `ranked[0]` fallback outside `src/`.
- After `launch`, if status is `FAILED` and no `src/` file exists, DENIED (keep harvest when `src/` is already there — 05-27).
- Worktree reuse must not promote leftover planning files.

**Out:** Git Candidate SHA (still content hash until an ADR).

**Accept:** unit: timeout + only `PRD.md` → DENIED. `src/app.py` present after FAILED → still harvest.

### 05-38 verify-context

**Path:** real e2e/reviewer prompts include TESTPLAN text + candidate SHA + “evaluate this directory only.” `REVIEW.md` / `RESULT.md` first line `PASS|FAIL`, then findings. Those findings persist as `feedback.json` on REWORK. A real `reviewer` binding is not skipped solely because `--check` passed.

**Must**

- Inject TESTPLAN + SHA into `_e2e_prompt` / `_review_prompt`.
- On REWORK, copy findings (not only SCRIPT_OUT) into feedback.
- If `reviewer.runtime != "fake"`, run reviewer even after scripted pass. Fake reviewer still skipped (05-30 stays for fake).

**Out:** Chrome MCP, critic model.

**Accept:** unit: real reviewer binding + passing `--check` still launches reviewer. Feedback contains TESTPLAN-derived finding text when REVIEW.md is FAIL.

## Wave F — Loop honesty (no new Kernel states)

Make the coded loop match the designed *backward edges* that already exist in `pipeline-state-machine.md`, without promoting stages into Controller events yet.

### 05-39 retry-dev-gate

**Path:** self-test DENIED / `candidate_gate=FAIL` → `hermes pipeline retry` allowed (same cap=1 as verify REWORK). Next implement prompt includes `feedback.json`.

**Must**

- `retry` accepts `verify_status=REWORK` **or** `candidate_gate=FAIL` with attempts &lt; 1.
- Persist a single `rework_attempts` (or keep `verify_attempts` and treat DEV fail as attempt-eligible).
- Do not require a verify row to exist.

**Out:** unlimited loops; agent-chosen rework destination.

**Accept:** unit: DENIED self-test → retry → second executor write → COMPLETED. Second retry exhausted.

### 05-40 infra-vs-rework

**Path:** sandbox/OSError during verify is **not** a semantic REWORK and does **not** burn the retry budget. Operator sees an infra error and can `retry` after the host is healthy.

**Must**

- Distinguish `INFRA` (exception, timeout of the **runtime**, missing exe) from script/pytest/REVIEW FAIL.
- Persist `verify_status=INFRA` or keep last semantic status and set `error=infra` (pick one; do **not** add a Kernel enum without ADR).
- `retry` allowed on INFRA without incrementing the semantic attempt, or increment a separate infra counter cap=3.

**Out:** new Pipeline status in `domain/pipeline.py`; Temporal.

**Accept:** unit: raise OSError in VerifyFlow → not READY, retry still available, attempt count unchanged.

### 05-41 gate-shape

**Path:** a one-line echo of the duty sentence is not a PASS PRD/Architecture.

**Must**

- PRD gate: named file exists, CAS verifies, body ≠ duty sentence, min length or required heading (`#` title).
- Architecture gate: both named files, neither empty, TESTPLAN mentions at least one check (`pytest` or `--check` or “test”).
- Still no LLM-as-judge.

**Out:** semantic PRD review, Requirement Question wait (Wave J).

**Accept:** unit: artifact equal to `prd_prompt` duty → FAIL. Two nonempty named files with a test mention → PASS.

## Wave G — Adapter honesty (no ADR)

### 05-42 spawn-fence

**Path:** OpenCode timeout kills the **job tree** (node grandchildren die). `signal()` cancels a live launch.

**Must**

- Product `OpenCodeAdapter` / `CodexAdapter` / `ProcessAdapter` spawn via existing `run_fenced` (Job Object / kill-on-close). Do not use bare `subprocess.run`.
- Store the job/handle on the in-flight `_Run`. `signal()` terminates it.
- Windows + Linux tests for the fence helper already exist — wire them; do not weaken process-tree tests.

**Out:** Docker.

**Accept:** unit: adapter timeout → grandchild not left writing `cwd` (reuse 00-06 / `_process.py` evidence style).

### 05-43 opencode-json-dir

**Path:** live OpenCode is `run --auto --format json --dir <cwd> --model …` with the prompt **not** as a giant argv token.

**Must**

- Write prompt to a file under cwd (or stdin). Classify with existing `classify_opencode_events` when `--format json`.
- Pass `--dir` equal to the stage cwd (`plans/…/prd`, worktree, sandbox).
- Codex: `encoding="utf-8", errors="replace"`; zero valid JSON objects → FAILED.

**Out:** new CLI families.

**Accept:** unit: long prompt does not go last on argv. Codex mixed TUI+no-JSON → FAILED.

### 05-44 sidecar-atomic

**Path:** crash mid-write of `architecture.json` / `bindings.json` / `runtimes.json` cannot look like a new empty pipeline. Restart is fail-closed or last-good.

**Must**

- Load **every** sidecar through `_parse_json` (corrupt → `_corrupt`).
- Write via temp + `os.replace` (same as `transport/_descriptor.py`).
- Keep `stages.json` as the bundle that cannot drop verify while keeping APPROVED (05-33).

**Out:** SQLite promotion (Wave J).

**Accept:** unit: `architecture.json = not-json` → `read`/`approve` error, not “baseline not ready” on a live PRD.

## Wave H — Isolation lite (implements ADR-0015; no new ADR)

### 05-45 attach-profile

**Path:** Development launch compiles `development-workspace` (or current equivalent). Codex Development is **not** forced `--sandbox read-only`. Planning/e2e/acceptance stay tighter.

**Must**

- `KernelBridge._runtime_broker` / launch site calls `compile_profile` and passes it into adapters.
- Adapter `evaluate(EXECUTABLE)` fail-closed if profile denies.
- Codex: read-only for planner/reviewer; writable cwd for executor (vendor flag, still no host Git credentials).

**Out:** AppContainer/unshare (spike stays spike). Docker.

**Accept:** unit: missing/denied profile → launch FAILED. Fake bindings skip profile.

### 05-46 child-jail

**Path:** fake `write("../x")` and `write` into a prefix-sibling (`wt` vs `wt2`) both denied. Harvest refuses symlinks/junctions. Agent child env does not inherit `GITHUB_TOKEN` / `GH_TOKEN`.

**Must**

- Replace `startswith` in worktree/sandbox with the part-wise `_contains` already in `capability.py`.
- Harvest: skip symlink/junction files.
- Product adapters: build child env from spike `_redaction.child_environment` or equivalent (strip secret names; keep `PATH` for the pinned exe).
- Secret scan remains; add at least `GITHUB_TOKEN=` / `ghp_` style redaction on harvested bytes (fail the candidate, do not log the secret).

**Out:** per-run random canary, GitHub App least-privilege (Phase 5 roadmap item, later).

**Accept:** unit: prefix-sibling escape denied. Harvest of a symlink outside root → ignored/DENIED. Child env has no `GITHUB_TOKEN`.

## Wave I — Hold for human + ADR

Do **not** start these in this campaign. Each needs an explicit decision.

| Item | Why it waits |
|---|---|
| Promote approve / dev / verify to Kernel commands + Events | ADR-0014 already requires it; inventing live states without a Phase Plan is forbidden (05-33). |
| Split `approve` from implement (lock baseline, then a second verb to build) | Changes the operator path; ADR-0012 boundary. |
| Architecture Requirement Question wait | ADR-0004/0007; needs a wait projection and CLI. |
| Git commit as Candidate SHA / real Integration Base | ADR-0018; 03-05 Out until accepted. |
| Docker / AppContainer sandbox | New isolation family. |
| Chrome MCP browser e2e | After Wave E–F green on the parking-lot app. |
| Feishu cards, Dashboard, GitHub App | ROADMAP Phase 5/6 product scope. |

## Final live test (after Waves E–H on `main`)

Same parking-lot **web** requirement as `phase-05-quality-campaign.md`. Extra bars:

1. PRD that quotes “Write PRD.md then implement src/” still yields a `src/` candidate, never a PRD candidate.
2. Failing self-test → `retry` recovers once with feedback visible in `read`.
3. Killing the host mid-OpenCode does not leave node children writing the worktree (spot-check on Windows).
4. `read` after restart still has approval + verify + `pr_url`.
5. Negative: `GITHUB_TOKEN=…` in harvested `src/` → DENIED, no PR.

## Session order

`05-36` → `05-37` → `05-38` → `05-39` → `05-40` → `05-41` → `05-42` → `05-43` → `05-44` → `05-45` → `05-46` → live test.

Do not start Wave I, UI, or Phase 6 from this file.

## Mapping to capabilities

| Wave | Traceability |
|---|---|
| E | `CAP-04` handoff / `XCON-01` only if a Schema changes (prefer plain text contracts) |
| F | `CAP-04` / `CAP-05` rework edges |
| G | `XREL-01` / `XPLAT-01` |
| H | `CAP-03` / `XSEC-01` / ADR-0015 |
