# Slice 02-05 — Codex CLI Adapter

Status: **READY**. Branch: `feat/slice-02-05-codex-adapter` from 02-04 tip.

## Must

Stage roles bind to a runtime family + model (ADR-0032). `BindingTable` resolves planner/executor/reviewer/e2e; missing binding is `UNSUPPORTED`. `BoundRuntimeBroker` dispatches to `CodexAdapter` or `OpenCodeAdapter` and injects `--model`. Codex missing executable is fail-closed. Fake still returns `FAKE`.

## Out

Real Codex binary, sealed runtime, Windows Authenticode, OpenCode, Chrome MCP.
