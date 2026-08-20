# Kernel events: is it a good next cut?

- Snapshot: 2026-08-20
- Method: agent-reach (Exa + Jina + GitHub). Reddit/Twitter/小红书 backends off.
- Status: research only; does not supersede ADRs.

## Verdict

**Direction: yes. First implementation: thin stage-completion events, not Temporal.**

ADR-0014 already says the append-only Pipeline Event Log is the only business history. Live Kernel today only accepts `CONFIRM_REQUIREMENT` / `REJECT_REQUIREMENT`. Approve / dev / verify live in sidecar JSON. That split is why a dead sidecar loses mid-`approve` progress. Promoting those stations to Commands+Events completes the accepted design. It is not a new product fashion.

## What 2026 peers actually do

| Source | Claim | Lesson for Hermes |
|---|---|---|
| [Temporal LangGraph plugin (2026-07-16)](https://temporal.io/blog/temporal-langgraph-plugin-durable-execution) | LangGraph checkpoints are durable *data*, not durable *execution*. Recovery needs an orchestrator outside the graph. | Matches ADR-0014: LangGraph stays inside Stage Executor; Controller owns Pipeline facts. |
| [dreaming.press LangGraph vs Temporal](https://dreaming.press/posts/langgraph-checkpointing-vs-temporal-durable-execution.html) | Replay requires determinism; LLM/tool/HTTP live outside the replay path. | Do **not** put OpenCode stdout or model tokens in the Event Log. Record *outcomes* (PRD artifact id, Candidate SHA, verify READY). |
| [OpenHands software-agent-sdk EventLog](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/event_store.py) | Append-only conversation events + websocket state updates. | Conversation log ≠ Pipeline authority. Do not copy chat events into Kernel. |
| Prior note `2026-08-complete-pipeline-oss-gap.md` | “Live Controller must own approve/dev/verify events, not only intake OPEN.” | Still the gap after Chrome e2e shipped. |

## Good first cut

Operator-visible: after `approve`, `read` shows PRD done / impl done / verify READY as Kernel projections, and a restarted runtime can continue from the last accepted event instead of re-running the whole `approve`.

Must:

- New Controller commands for stage completion (or one `ADVANCE` with a typed station), inbox-deduped, revision-checked.
- Events append-only; sidecar JSON stops being the source of truth for those stations.
- LangGraph remains inside Stage Executor. Controller still does not import it.
- No Temporal / new orchestration family (would need a separate ADR).

Out of first cut:

- Splitting `approve` into two operator verbs (ADR-0012, separate decision).
- Streaming agent tokens as events.
- Docker.
- Full Temporal-style activity replay of OpenCode.

## Risk if done badly

Inventing live statuses without a Phase Plan was forbidden in 05-33. First events must map 1:1 onto stations already visible in `read` (prd / arch / dev / verify). Do not add `RUNNING_MODEL` chatter.

## Recommendation

Proceed, but grill a 1-page Phase Plan before code: command names, event names, what `read` shows, crash-restart demo. Then one thick cut: persist PRD+Arch+Dev+Verify outcomes through Kernel so sidecar death does not wipe an in-flight `approve`.
