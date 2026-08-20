# Slice 05-51 — Chrome tool bootstrap

Status: **READY**. Branch: `feat/slice-05-51-chrome-tool-bootstrap`.

## Must

Locked Node 22.23.2, `chrome-devtools-mcp@1.7.0`, and pinned Chrome for Testing materialize under disposable `verify-sandbox/tools`. Digest/SRI/SHA fail closed. No PATH Node/npm/Chrome. Fake path and pytest use an injected fetch (no network).

## Out

Sealing CfT. Root uv / runtime-env Node. Docker. Kernel events. KEEP_MARKED Host/Custodian. Live parking-lot (05-52).
