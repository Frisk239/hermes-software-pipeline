# Slice 05-18 — list runtimes and pass an implement prompt

Status: **READY**. Branch: `feat/slice-05-18-runtimes-and-prompt`.

## Must

`admin --runtimes` lists detected agent families by name only. Bound non-fake executors receive a prompt (stdin or Codex argv). Timeout is longer when a prompt is present.

## Out

Full Claude/Cursor protocol, Dashboard.
