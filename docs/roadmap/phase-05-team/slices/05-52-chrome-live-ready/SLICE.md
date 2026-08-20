# Slice 05-52 — Chrome live-ready

Status: **READY**. Branch: `feat/slice-05-51-chrome-tool-bootstrap`.

## Must

Verify waits until `src/app.py` listens on the reserved loopback port (or the process exits). Direct MCP stdio calls `navigate_page` then `evaluate_script` and stores the tool text as the e2e artifact. Fake MCP names stay `chrome-devtools_*`.

## Out

Opening a new PR. Docker. Kernel events. Sealing CfT.
