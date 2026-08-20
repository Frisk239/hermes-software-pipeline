# Slice 05-50 — Chrome login e2e

Status: **READY**. Branch: `feat/slice-05-50-chrome-login-e2e`.

## Must

`--check` is preflight only when e2e is not `fake`. Verify starts `src/app.py` on loopback and launches `ChromeMcpRuntime`. Injected fake MCP records navigate then evaluate. Missing Node/MCP/CfT is REWORK. Closed ADR-0029 argv. Fake bindings stay READY.

## Out

Download/bootstrap of tools (05-51). Docker. Kernel events. Promoting KEEP_MARKED 00-06 Host modules.
