---
status: proposed
---

# Confine Node, npm, and Chrome DevTools MCP to a disposable Verification Sandbox

**Status: proposed - DRAFT only. This ADR is not accepted. Only a human may accept it, and Slice 00-06 cannot become READY until that acceptance is recorded together with ADR-0030.**

The Hermes Pipeline root remains Python 3.12 + uv only (ADR-0020). This decision authorizes a disposable Slice 00-06 browser-tool family for Verification Sandbox spikes. It does not change the development-toolchain Node used through `pyright[nodejs]`, and it does not introduce any browser dependency into the root project, the 00-05 Hermes managed-runtime root, `runtime-env/`, or a production service.

**What "sealed" covers.** The sealed supply-chain claim covers only Node `22.23.2` (exact SHA-256 plus pinned official release-key fingerprints), the committed `package.json` / `package-lock.json` / lock-owned `.npmrc` digests, and `chrome-devtools-mcp@1.7.0` npm SRI under registry-trust. It does **not** cover Chrome, Chrome for Testing, or any browser binary. Accepting this ADR must not be cited as sealing Chrome for Testing `151.0.7922.77`.

**Actors.** "Host" means the privileged Slice 00-06 sealed-tool test runner that invokes `tools_bootstrap.py` and `controlled_e2e.py`. It is not the CONTEXT.md **Host Operator**, not a new Pipeline role, and not the production Runtime Broker. "Sandbox Agent child" is the untrusted child under that runner. This decision does not add either name to CONTEXT.md.

1. **State-root separation.** The 00-06 state root is a fresh disposable directory owned by that Host runner. It never reuses, reads, or extends the 00-05 Hermes managed-runtime root. Browser tooling, npm cache and configuration, and temporary profiles remain below `<state-root>/tools/`. A future move of Node, npm, Chrome, or a browser MCP into the root project or a production service requires a separate accepted ADR and Slice Contract.

2. **Committed identities, with an honest browser limit.** The committed `tool-lock.json`, adjacent standard `package.json` and `package-lock.json`, and the committed lock-owned `.npmrc` are the complete pre-download planning inputs. The Host verifies and byte-copies the package files unchanged, verifies the exact `chrome-devtools-mcp@1.7.0` pin and recorded SRI, and uses Node `22.23.2` only after its exact SHA-256 and pinned release-key proof. The `npm` executable is the one shipped with that selected locked Node install; ambient PATH npm is not an authorized trust root. Chrome for Testing `151.0.7922.77` has no official SHA-256. It is a pinned experimental URL and version only. Path-selection proof and a first-download hash are not frozen identities, and "project-verified" must not be read as a completed independent checksum. CfT remains excluded from every sealed supply-chain hard-gate. Promoting it to a sealed browser requires a new ADR and Contract Change Request.

3. **Controlled npm materialization and cutoff.** The Host creates a new project containing only the verified byte-copied `package.json` and `package-lock.json`, copies the committed lock-owned `.npmrc` to `<state-root>/tools/browser-runtime/npmrc`, creates an empty `<state-root>/tools/browser-runtime/empty-global-npmrc`, and uses exactly this online bootstrap argv with the locked Node `npm`:

   ```text
   npm ci --ignore-scripts --audit=false --fund=false --update-notifier=false --cache <state-root>/tools/npm-cache --userconfig <state-root>/tools/browser-runtime/npmrc --globalconfig <state-root>/tools/browser-runtime/empty-global-npmrc
   ```

   The Host starts npm with a clean, explicit environment: HOME/XDG/Windows user-profile locations and cache/config paths are all under state root; it strips inherited `NPM_CONFIG_*`, credential, registry, proxy, certificate, and `HTTP(S)_PROXY` variables; and it permits no project or user `.npmrc` other than the locked copied configuration. The cutoff proof repeats that exact command in a fresh disposable project with the additional `--offline` flag. No rename/synthesis, `npm install`, `npx`, lifecycle script, cache miss, range/latest, inherited configuration, or post-cutoff network is allowed. npm integrity and provenance remain registry-trust evidence, not independent code signing.

4. **Closed Chrome DevTools MCP launch policy.** The Host selects exactly one traversal-safe extraction path from the locked platform mapping: Windows x64 `<state-root>/tools/browser-runtime/chrome-for-testing/win64/chrome-win64/chrome.exe`, or Linux x64 `<state-root>/tools/browser-runtime/chrome-for-testing/linux64/chrome-linux64/chrome`. It verifies that the selected path is beneath the state root and corresponds to the locked platform/version record; this path-selection proof does not convert Chrome for Testing into a checksum-sealed artifact.

   The Host also selects the matching locked Node executable from the platform mapping in `tool-lock.json`, constructs the MCP invocation itself, and admits no extra user, repository, environment, or configuration-supplied options. Its complete MCP argv is:

   ```text
   <selected-locked-node-executable>
   <state-root>/tools/browser-runtime/project/node_modules/chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js
     --headless
     --isolated
     --executable-path <selected-locked-cft-executable>
     --allowed-url-pattern http://127.0.0.1:<host-reserved-fixture-port>/*
     --no-usage-statistics
     --no-performance-crux
   ```

   Its only MCP update-control environment value is `CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1`. The Host rejects every option/configuration surface outside this canonical form, including `--browser-url`, `--ws-endpoint`, `--auto-connect`, `--channel`, `--user-data-dir`, `--allow-unrestricted-paths` (and legacy/case variants), and every arbitrary Chrome-argument override. The fixture origin is Host-owned and loopback-only; no personal profile, account, external DevTools endpoint, or business site is permitted. Here `--isolated` means an MCP-managed temporary browser profile that is cleaned on close; it is not an operating-system isolation claim. These MCP controls disable MCP usage statistics, CrUX, and update checks, but do not prove Chrome or the operating system denies egress. OS-level network denial still needs separate capability evidence.

5. **Authority is defined by ADR-0030.** This ADR does not independently expand Git Custodian or define authorization artifacts. Real browser-tool launch follows ADR-0030: the Git Custodian resolves, materializes, and verifies the no-`.git` Integration-Candidate snapshot and delivers a read-only validation handoff; the Host only reads, inspects, and validates that handoff plus the three Custodian artifacts and seven inputs; only then may it fetch locked assets or launch the closed MCP argv. `uv run --offline` concerns Python dependencies only and is not npm or OS-egress proof. A failed asset rule, closed-argv rule, host-isolation proof, authorization check, or runtime observation fails closed as `UNSUPPORTED_RUNTIME` or `DEPENDENCY_UNAVAILABLE`; it never falls back to a system Chrome, default browser channel, remote browser, ambient npm, or host-installed Node.

Any future change to this confinement, identity model, browser attachment model, or root/production dependency boundary requires a separate accepted ADR and Slice Contract.
