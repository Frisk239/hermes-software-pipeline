# Slice 02-04 — LangGraph Stage graph

Status: **READY**. Branch: `feat/slice-02-04-langgraph-stage` from 02-03 tip.

## Must

`GraphStageExecutor` implements `StageExecutorPort` with LangGraph `StateGraph` + `SqliteSaver`. One Run is one `thread_id` (`run_id`). `start` interrupts before `submit`; `inspect` is `PENDING` and Controller has no ACCEPTED CONFIRM. `resume` submits one stable `CONFIRM_REQUIREMENT` (`cmd_stage_{run_id}`), `inspect` is `COMPLETED`, `read` is OPEN. Replay / second `resume` keeps one Event and the same receipt. Checkpoint SQLite ≠ Controller SQLite. `cancel` is CANCELLED and `resume` does not advance. Every `invoke` uses `durability="sync"`. Fake adapters still do not import langgraph.

## Out

Real Codex/OpenCode, Chrome MCP, Controller semantic changes, promoting the keep-marked spike.
