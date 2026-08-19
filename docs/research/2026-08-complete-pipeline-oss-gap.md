# Complete software-engineering pipeline: OSS survey vs Hermes HEAD

- Snapshot: 2026-08-19
- Method: agent-reach (Exa, GitHub `gh`, Jina, Bilibili search). Reddit/Twitter/小红书 backends were off.
- Status: research only; does not supersede ADRs.

## Executive conclusion

The **design** (deterministic Controller, Stage isolation, bindable runtimes, human baseline + GitHub-native merge, no Agent Git credentials) is closer to durable-execution systems than to MetaGPT/ChatDev “LLM company chat.” That direction is still right.

The **live implementation** is not yet as tight as the design or as OpenHands’ 2026 verification stack. Intake + CAS + host `gh` PR are real. After confirm, most later stages are sidecar JSON, content-blind gates, or fail-open. There is no merge observation and no multi-layer verify.

Do **not** pivot to MetaGPT-style free-form multi-agent chat. Close the existing pipeline: make verify actually exercise the Candidate, then observe GitHub checks/merge.

## What peers actually do (2026)

| Project | Role | Pipeline lesson |
|---|---|---|
| [OpenHands verification stack](https://www.openhands.dev/blog/20260506-the-verification-stack) | Production OSS | Layer 1 critic on the agent trajectory *before* push; Layer 2 PR **review skill** (diff) + **QA agent that runs the software** (CLI/HTTP/browser); `/iterate` until green. Evidence: 1000+ reviews, MTTM −58%. |
| [OpenHands software-agent-sdk](https://github.com/OpenHands/software-agent-sdk) | Agent runtime | Event-sourced conversation, Docker/remote workspace, mid-loop confirm, skills. Not a product SE pipeline. |
| [SWE-agent](https://github.com/SWE-agent/SWE-agent) / mini-swe-agent | Issue → patch | Isolated env (SWE-ReX). Verify is a **separate harness**, not “READY because a role is bound.” |
| [CAID / async SE agents](https://www.openhands.dev/blog/asynchronous-software-engineering-agents) | Research on OpenHands | Coordinate via **git worktrees, merges, tests**, not chat. |
| Factory Droids (closed) | Enterprise SDLC | Coordinator + specialized Code/Review/Docs/Test. Model-switchable. Logic is proprietary. |
| MetaGPT / AgileCoder / ChatDev | Role SOP research | Structured artifacts beat chat. Hallucinations still cascade. Weak on repo-scale + Git delivery. |
| Claude Code / Codex / Aider | Harnesses | Great executors. Not a durable multi-stage pipeline. Hermes should **bind** them, not become them. |

Bilibili discussion (agent-reach `bili-cli`) is tutorial-level (“15 分钟搭 OpenHands”); no new architecture signal.

## Design: reasonable?

**Keep**

- BindingTable (planner/executor/e2e/reviewer × runtime × model) matches Factory/OpenHands ACP: harness is swappable.
- Human Solution Baseline + GitHub-native merge matches the 2026 consensus (two human boundaries).
- Artifact handoff (PRD.md / ARCHITECTURE.md / TESTPLAN.md / `src/`) is MetaGPT’s good idea without the chat company.
- Controller must not import LangGraph; Agents untrusted.

**Tighten (design, not UI)**

- Verify is a **stack**, not one `python src/app.py`. Need: run declared tests / TESTPLAN, optional browser QA, review the **diff**, iterate on REWORK.
- Live Controller must own approve/dev/verify events, not only intake `OPEN`.
- Sandbox must isolate process/network, not only `copytree(src)`.
- Observe GitHub checks/merge; never merge inside adapters.

## Implementation vs design (HEAD)

Already rigorous: loopback auth, intake membership, CAS, worktree escape/canary, `gh` blob/PR, named harvest after 05-26, `src/`-only publish after 05-27, scripted `src/app.py` after 05-28 (unmerged/merging).

Not rigorous enough for a complete pipeline:

1. Kernel is intake-only (`UNCONFIRMED|OPEN|REJECTED`). Stages live in sidecar JSON; loads fail-open to `{}`.
2. `SolutionApproval` is process memory; VIEWER can approve; approve `ok` even if verify is REWORK.
3. Live verify still injects `_PassingRuntime`; RESULT.md/REVIEW.md unread; skip/timeout → READY; scripted pass skips reviewer.
4. Integration base SHA is `"0"*64`. No pytest / TESTPLAN / browser.
5. Kernel `FakeDelivery` always succeeds; shim publish not gated on verify READY.
6. No merge observation.
7. OpenCode ignores exit code; Codex prompted timeout is 10s.

## Recommended next cuts (core, no UI)

1. **Verify stack v1** — launch bound e2e/reviewer (not `_PassingRuntime`); read RESULT.md/REVIEW.md; fail-closed on skip/timeout without evidence; run `pytest` when present; do not publish if not READY.
2. **Observe GitHub** — poll checks/review/merged SHA into read; still no merge API.
3. **Promote approve/dev/verify to Controller events** + SQLite on the live path (stop silent empty JSON).
4. **Sandbox profile** — at least process + cwd jail; Docker later.
5. **REWORK iterate** — one bounded re-dev loop from verify failure (OpenHands `/iterate` lite).

Out of v1: Dashboard, critic model training, org-wide automations, MetaGPT PM/CEO roles.
