# Slice 02-03 — Fake Stage on Executor / Broker / CAS

Status: **READY**. Branch: `feat/slice-02-03-fake-stage-runtime` from 02-02 tip.

## Must

`FakeStageRun(broker, artifacts, profile)` implements `StageExecutorPort`. A DEVELOPMENT profile that allows `SIDE_EFFECT=LOCAL_TEST` and `write_roots` at the CAS root lets `start(run_id="run_01")` call `broker.launch` once (handle stays `FAKE`), put one CAS artifact, and `inspect` as `COMPLETED`. A profile that does not allow that side effect is fail-closed: `DENIED`, no launch, no artifact. `cancel` always marks `CANCELLED`, including after `COMPLETED`.

## Out

Real LangGraph, real Codex/OpenCode adapter, Chrome MCP, changing 00-07 `FakeStageExecutor` / `FakeRuntimeBroker` defaults.
