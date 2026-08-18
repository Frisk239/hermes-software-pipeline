# Slice 02-02 — Capability Profile compile + evaluate

Status: **READY**. Branch: `feat/slice-02-02-capability-profile` from 02-01 tip.

## Must

`compile_profile` returns a `CapabilityProfile` whose `content_hash` is `hermes_pipeline.contracts.jcs.content_hash` (no `sort_keys`). Same input twice yields the same hash. `evaluate(profile, request)` is fail-closed policy only: path must stay in the matching roots after normalize (Windows case-insensitive, POSIX case-sensitive; `..` escape and off-drive denied); `DENY_ALL` denies every host; `ALLOW_LIST` is exact host; unknown kind / missing executable / `browser=NONE` + `CHROME_DEVTOOLS_MCP` / secret or side-effect not listed → DENY; `NONE` is not a wildcard side-effect.

## Out

Real Runtime Broker process launch, LangGraph, CAS changes, OS AppContainer/namespace, isolation-probe promotion.
