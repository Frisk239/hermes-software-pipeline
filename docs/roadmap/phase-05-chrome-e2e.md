# Phase 5 Chrome e2e

Authorized 2026-08-20 after parking-lot scripted verify is on `main` (#84).
Does not start Docker, Kernel events, or Phase 6.

## Intake of previous cut

| Check | Result |
|---|---|
| Merge | #84 (`05-47` harvest + `05-48` auto-start + `05-49` last-exit) is on default remote |
| Evidence | Ubuntu/Windows quality + integration green |
| Spec vs claim | Live parking-lot still uses `python src/app.py --check`, not a browser |
| Safety | No secrets in those commits |

**Verdict: 有条件通过.** Debt: sidecar still dies mid-OpenCode; last-exit exists but unused in live; pytest absent in isolated runtime.

## Operator path today

`submit` → PRD/Arch → `approve` → self-test → **`--check` as e2e** → `gh` PR.

Chrome is never launched. `ChromeMcpRuntime` is fail-closed fake (02-06). 00-06 Host/bootstrap stays KEEP_MARKED.

## Phase cuts

### 05-50 chrome-login-e2e

**User path:** operator `approve`s the parking-lot app; verify starts `src/app.py` on loopback; headless Chrome opens the login page; DOM/login-ok is the e2e artifact. Fake bindings stay READY without Chrome.

**Must**

- `--check` is preflight only when e2e is not `fake`. Passed `--check` no longer skips the browser.
- `ChromeMcpRuntime` uses ADR-0029 closed argv (locked Node + `chrome-devtools-mcp.js` + CfT under a disposable verify state-root).
- Only `chrome-devtools_navigate_page` then `chrome-devtools_evaluate_script`. Other tools DENY.
- Missing Node / MCP / CfT → REWORK, no child, no system Chrome / PATH npm / host Node.
- Fake path and CI stay green without binaries.
- Do not import KEEP_MARKED `tools_bootstrap` / `controlled_e2e` / `_host`.

**Out**

- Downloading Node/MCP/CfT (05-51).
- Sealing CfT. Adding Node/MCP to root uv.
- Docker / AppContainer. Kernel events. Feishu / Dashboard.
- Promoting 00-06 Host, Custodian 7-input chain, mock-provider OpenCode e2e.

**Demo:** unit/fake still READY; one local run with pre-placed tools opens the login page and stores a browser-derived artifact. Without tools, verify is REWORK not silent READY.

### 05-51 chrome-tool-bootstrap

Materialize locked Node + `chrome-devtools-mcp@1.7.0` + pinned CfT into the disposable verify sandbox from committed lock identities. Fail closed. No PATH fallback.

### 05-52 chrome-live-parking-lot

Same parking-lot requirement as the quality campaign. Extra bar: `read` shows browser e2e (not only `SCRIPT_OUT`), PR still opens.

## Rules

- Existing ADR-0029 confinement. New ADR only if Chrome becomes a hard gate on every pipeline or lands in the root toolchain.
- Controller still does not import Chrome.
- Human merges `main`. Agent pushes `feat/*` only.
