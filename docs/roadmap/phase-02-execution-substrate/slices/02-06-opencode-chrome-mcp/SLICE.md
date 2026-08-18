# Slice 02-06 — OpenCode E2E + Chrome MCP test runtime

Status: **READY**. Branch: `feat/slice-02-06-opencode-chrome-mcp` from 02-05 tip.

## Must

`BindingTable` binds `e2e` → `opencode` + model. `ChromeMcpRuntime` implements `RuntimeBrokerPort`. `browser=NONE` or `CHROME_DEVTOOLS_MCP` without an injected fake MCP is `UNSUPPORTED` and does not spawn. Injected fake MCP records `chrome-devtools_navigate_page` then `chrome-devtools_evaluate_script` and completes. Other tool names are DENY. Planner/executor bindings stay unchanged.

## Out

Real Chrome for Testing, sealed checksum, real MCP server, changing ADR-0029 seal scope, promoting 00-06 keep-marked probes.
