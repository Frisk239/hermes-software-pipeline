# Role prompts and other thin seams (2026-08)

- Snapshot: 2026-08-19
- Method: agent-reach (Exa, GitHub `gh`, Jina). Reddit/Twitter/小红书 backends were off.
- Also: four read-only explore sub-agents on this repo (prompts, loop, adapters, security).
- Status: research only; does not supersede ADRs.

## Executive conclusion

Yes, the live Stage prompts are too thin **as a contract**, but the bigger miss is the same thinness elsewhere: gates, handoffs, isolation, and retry. Peers do **not** win by writing a 200-line “you are a senior PM” SOP. They win by (1) a stable duty/system block separate from untrusted artifacts, (2) structured station output, (3) tests/sandbox as the real control.

Do **not** copy MetaGPT role chat or OpenHands’ conversation-as-pipeline. Keep BindingTable + named artifacts + Controller. Thicken **handoff contracts and enforcement**, not persona text.

## Are one-line prompts too simplistic?

**Compared with peers**

| System | What they actually inject | Lesson for Hermes |
|---|---|---|
| [OpenHands `system_prompt.j2`](https://github.com/OpenHands/OpenHands/blob/main/openhands/agenthub/codeact_agent/prompts/system_prompt.j2) | Long **system** ROLE / workflow / security; user task is separate. Skills can suffix the system message ([SDK issue #1965](https://github.com/OpenHands/software-agent-sdk/issues/1965)). | Duty must not be concatenated with PRD body as one argv token. |
| [SWE-agent TemplateConfig](https://swe-agent.com/latest/reference/template_config/) | `system_template` + `instance_template` + per-step observation templates. | Split “who you are / what to write” from “this instance’s documents.” |
| [MetaGPT ProductManager](https://github.com/geekan/MetaGPT/blob/main/metagpt/roles/product_manager.py) + [ICLR 2024 paper](https://proceedings.iclr.cc/paper_files/paper/2024/file/6507b115562bb0a305f1958ccc87355a-Paper-Conference.pdf) | Role + **action** (`WritePRD`) + SOP documents. Agents talk via artifacts, not chat. | We already stole the good part (named files). We did not steal the action contract. |
| [CAID / OpenHands async agents](https://www.openhands.dev/blog/asynchronous-software-engineering-agents) | Manager assigns **structured JSON** + isolated worktrees; verify is tests/merge. | Isolation + structured assignment beat longer prose. |
| [Engineering Squad](https://techcommunity.microsoft.com/blog/azuredevcommunityblog/from-requirement-to-production-code-how-engineering-squad-automates-the-full-dev/4522698) | Per-agent `*.prompt.md` + LangGraph routes reviewer output to a **named** previous station. | Reviewer must return a routing-capable finding, not only `PASS`/`FAIL`. |
| [Sequenced pipelines](https://www.agent-engineering.ch/articles/assembly-line-agent/) | “Design the **handoff**, not just the agent.” 3–5 stations, not 30. | Our design already says this. Live code still dumps prose. |

**What we inject today** (`kernel_bridge.py` `prd_prompt` / `architecture_prompt` / `implement_prompt`; `verify.py` `_e2e_prompt` / `_review_prompt`):

- One duty sentence + unlabeled CAS text (or no product context at all for e2e/reviewer).
- No system/user split. OpenCode/Codex get the whole string as the last argv.
- `docs/agents/roles/` is this **repo’s** Slice Owner track, not product Stage contracts.

That already failed live: `pl_live4` PR #3 harvested `PRD.md` because the implement prompt still contained “write a PRD” as peer instructions.

**Smallest prompt upgrade (not a rewrite)**

1. Five short product contracts (prd / architecture / development / e2e / acceptance): mission, required files, forbidden files, stop conditions. First block only.
2. Fence untrusted CAS with `BEGIN_UNTRUSTED_*` / `END`. Unit-test: a PRD that quotes “Write PRD.md” must not change the duty block.
3. PRD harvest named file only (drop stdout fallback).
4. E2E/reviewer get TESTPLAN + candidate SHA; first line `PASS|FAIL`, then findings.
5. Attach existing `CapabilityProfile` at launch (ADR-0015). Prompts stay non-enforcement.

## Other seams that are the same thinness

Four sub-agents, same pattern: **design is a contract; live path is a sentence + a folder**.

### 1. Loop / gates (high)

Designed: `docs/design/pipeline-state-machine.md` full attempt graph.  
Coded: `submit` → PRD+Arch; `approve` → Dev+Verify; `retry` only if `verify_status=REWORK` and attempts &lt; 1.

- Kernel stays `OPEN` forever (`domain/pipeline.py`). Stages live in sidecar JSON.
- Gates check “bytes exist + hash + OPEN”, not artifact shape (`prd.py`, `architecture.py`, `development.py`).
- Architecture `question=` is a test hook; Kernel never waits (ADR-0004/0007 gap).
- `approve` designates the caller **and** builds the product (`kernel_bridge._approve_baseline`).
- DEV_GATE `DENIED` is not retryable (`retry` → `not rework`).
- Exceptions become `REWORK` and burn the only retry (designed `INFRA_BLOCKED`).
- Scripted `--check` can skip reviewer and still `READY` (`verify.py`).

### 2. Runtime adapters (high)

- Development harvests after timeout/FAILED (`development.py`; tested as intended).
- `subprocess.run` + no Job Object on product adapters; `signal()` cannot cancel.
- OpenCode: no `--format json` / `--dir`; long prompt on argv (Windows ~32k).
- Codex: missing `encoding=utf-8`; JSONL fail-open.
- `architecture.json` / `bindings.json` / `runtimes.json` load fail-open to `{}`.
- Shim `submit` can 600s-timeout while two 300s stages still write.

### 3. Security / isolation (high vs ADR-0013/0015)

- Worktree/sandbox are directories. Real agent is same-user `--auto` with inherited env.
- `CapabilityProfile` exists and is not attached to launch.
- Path escape is `startswith` and only wraps **fake** `write()`.
- Secret check is the literal `"SECRET_CANARY"`.
- Host `gh` uses operator session (no merge API — good; not least-privilege — incomplete).

## What not to do

- Do not add MetaGPT PM/CEO chat or 30 specialist personas.
- Do not load `docs/agents/roles/slice-owner.md` into product OpenCode.
- Do not treat thicker prompts as a substitute for sandbox, named harvest, or Controller events.
- Dashboard / Feishu / Docker remain deferred.

## Suggested next cuts

Authorized execution order: `docs/roadmap/phase-05-hardening-campaign.md` (05-36…05-46).

Out of that campaign (needs human + ADR): Kernel events for approve/dev/verify, Docker sandbox, merge observation, Requirement Question wait.
