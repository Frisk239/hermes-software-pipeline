# Slice 05-64 — MCP newline JSON + timeout

Status: **READY**. Branch: `feat/slice-05-64-mcp-timeout`.

## Must

Chrome DevTools MCP stdio uses newline JSON (SDK 1.7.0), not Content-Length. Drive times out instead of hanging. Silent server is TimeoutError → launch FAILED/REWORK.

## Out

Changing ADR-0029 argv. Docker.
