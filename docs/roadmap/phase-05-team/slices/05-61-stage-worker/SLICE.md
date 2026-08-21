# Slice 05-61 / 05-62 — stage worker + CLI poll

Status: **READY**. Branch: `feat/slice-05-61-stage-worker`.

## Must

Live `approve`/`retry` spawn `python -m hermes_pipeline.transport.stage_worker` and return `running`. HTTP `read` still works. CLI waits on `read` until verify settles. Tests without `spawn_worker` stay in-process.

## Out

Temporal. Docker. Splitting `approve` into two verbs.
