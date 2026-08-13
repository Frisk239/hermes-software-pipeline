# Slice 00-06 Research - Agent and Runtime Security Spikes (READY, revision 14)

## Status and scope

This is governing planning research for READY Slice Contract revision 14; the machine contract, not this report, is implementation authority. Its Planning Base is `9cf24b876cc7422386ed54c277900ff1e3c2c2bf` (origin/main after PR #12, 2026-08-12). Slice 00-05 was integrated at `102d08f814b6c0a939662e6c488870310a97c1ee` (PR #11). On 2026-08-13 the Repository Governance Owner accepted ADR-0029 and ADR-0030 together (attestation `engadr_0029-0030_20260813_01`). The authoritative texts are `docs/adr/0029-confine-browser-tool-runtime.md` and `docs/adr/0030-confine-agent-cli-tool-runtime.md`. Revision 14 closes the rejected r13 real-probe, controlled-E2E, digest-chain, and isolation-evidence findings; fresh independent READY review passed and the Git Custodian-assigned clean execution worktree remains at the exact Planning Base.

D1, D4, and D6 remain planning directions. D2 and D3, plus the D5 fail-closed facts recorded in the accepted ADRs, are now binding. This research authorizes neither production execution, root runtime dependencies, credentials, public-network CI, nor a new CI workflow.

## Evidence model

The project records three non-interchangeable things:

1. Vendor documentation or release metadata.
2. Immutable artifact identity and verification data in the committed `tool-lock.json`.
3. Project probe results for an exact version, operating system, runner, and date.

A wrapper package, release page, installer metadata, or vendor support statement is not a sealed runnable identity or a project capability proof.

## Frozen tool inputs

`tool-lock.json` is the versioned identity and closed-execution-policy source. It records immutable URL, asset name, expected digest or honest `no_official_checksum` status, verification order, platform selection, npm materialization policy, browser launch policy, and run-binding model before download.

| Component | Planned identity | Verification boundary |
| --- | --- | --- |
| Node | `22.23.2`, Windows x64 and Linux x64 official archives | Exact SHA-256 plus pinned official Node release-key fingerprints. |
| Chrome DevTools MCP | `chrome-devtools-mcp@1.7.0` | Exact npm SRI in committed standard `package-lock.json`; the lock preserves published optional-peer semantics. |
| Chrome for Testing | `151.0.7922.77`, win64 and linux64 | No official SHA-256 is available. It is an experimental, non-sealed target and cannot satisfy a sealed hard gate. |
| Codex | `0.146.0`, checked package archives | Exact official archive SHA-256. Linux sigstore is supplemental. Windows sealed real probes remain unsupported without an independently sourced exact Authenticode signer identity. |
| OpenCode | `1.18.12`, `opencode-windows-x64` and `opencode-linux-x64` npm tarballs | Locked OS/CPU selection, exact SRI SHA-512, and traversal-safe extraction. The `opencode-ai` wrapper is not runnable evidence. |

OpenCode release CLI archives and `latest.yml` are research-only metadata. Missing required identity fails closed; no first-download hash, `latest`, `npx`, system tool, wrapper, or automatic update is allowed.

## Standard browser-runtime npm materialization

The adjacent committed `package.json` and `package-lock.json` are a standard npm project. The committed slice-owned `.npmrc` contains `audit=false`, `fund=false`, `update-notifier=false`, and `ignore-scripts=true`; its exact digest is locked in `tool-lock.json`. The Host repeats `--ignore-scripts` in its controlled argv rather than relying solely on configuration, and admits no unverified ambient or renamed configuration file. The Host must:

1. Verify raw package file and npmrc digests, project name, exact `1.7.0` pin, and SRI against `tool-lock.json`.
2. Byte-copy only the two package files into a fresh state-root project, copy the verified `.npmrc` to `<state-root>/tools/browser-runtime/npmrc`, and create an empty state-root global npmrc.
3. Run only this online bootstrap argv:

   ```text
   npm ci --ignore-scripts --audit=false --fund=false --update-notifier=false --cache <state-root>/tools/npm-cache --userconfig <state-root>/tools/browser-runtime/npmrc --globalconfig <state-root>/tools/browser-runtime/empty-global-npmrc
   ```

4. Prove the same fresh disposable-project reconstruction after cutoff with the added `--offline` flag.

The Host begins with an explicit allow-listed environment: HOME/XDG and Windows user-profile/config/cache locations are below state root; inherited `NPM_CONFIG_*`, credential, registry, proxy, certificate, and `HTTP(S)_PROXY` variables are stripped; no user/project npmrc is admitted. No filename rename, synthesis, `npm install`, lifecycle script, cache miss, registry access after cutoff, range, or latest tag is permitted. `uv run --offline` governs Python dependencies only; it does not prove npm reconstruction or operating-system egress denial.

## Closed browser launch policy

After traversal-safe extraction, the Host selects only the locked platform path:

- Windows x64: `<state-root>/tools/browser-runtime/chrome-for-testing/win64/chrome-win64/chrome.exe`
- Linux x64: `<state-root>/tools/browser-runtime/chrome-for-testing/linux64/chrome-linux64/chrome`

The Host verifies that the selected path stays below state root and is the locked platform/version location. This proves selection and extraction containment, not a missing official Chrome-for-Testing checksum.

The Host selects the matching locked Node executable from `tool-lock.json` and creates the complete Chrome DevTools MCP argv itself:

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

Its only MCP update-control environment value is `CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1`. No repository, Agent, user, config file, or inherited environment can append or replace arguments. The Host rejects `--browser-url`, `--ws-endpoint`, `--auto-connect`, `--channel`, `--user-data-dir`, `--allow-unrestricted-paths` (including legacy/case variants), and any arbitrary Chrome-argument or unlisted MCP override. The fixture is a Host-reserved `127.0.0.1` origin only.

`--isolated` is an MCP-managed temporary browser profile that is cleaned on close. It is not an operating-system sandbox claim. The policy disables MCP usage statistics, CrUX, and update checks and limits MCP navigation to the local fixture; it does not establish Chrome- or OS-level egress denial.

## Execution lines and exact Integration Candidate binding

There are exactly three non-overlapping lines:

1. **PR line.** Ordinary CI continues to run the existing full offline pytest suite on Windows and Linux; 00-06 adds no workflow. The 00-06 real-tool runners are standalone Host-runner CLIs that are never pytest-collected and reject before process creation if the pre-execution record, gate, or run binding is absent or invalid.
2. **Host-only bootstrap line.** The privileged 00-06 sealed-tool test runner (not the CONTEXT.md Host Operator) invokes `src/hermes_pipeline/runtime_broker/tools_bootstrap.py`.
3. **Host-only controlled E2E line.** The same runner invokes `src/hermes_pipeline/runtime_broker/controlled_e2e.py` for the loopback mock-provider path.

Each Host-only entry requires exactly seven inputs: `--state-root`, `--candidate-sha`, `--source-tree-digest`, `--tool-lock`, `--tool-record`, `--host-gate`, and `--run-binding`. Before any real binary, provisioning, `--version`, or capability probe, the Git Custodian resolves the exact Candidate, exact Integration Candidate, and tree identities; alone materializes a controlled no-`.git` snapshot from the exact Integration Candidate; verifies that snapshot source-tree digest exactly equals the Integration-Candidate tree digest; and delivers it as a Custodian-owned read-only validation handoff to Host while exposing it only as the source tree usable by the Sandbox Agent child. The Custodian then issues immutable `pre-execution-tool-record.json` outside the child snapshot from only static tool-lock, selected-platform, Candidate, Integration Candidate, verified source-tree digest, and locked identity data. Its RFC 8785 canonical identity includes Planning Base, Candidate SHA/tree, Integration Base, exact Integration Candidate SHA/tree, that source-tree digest, tool-lock digest, selected platform/tool entries, and Custodian origin; it excludes `version_output`, `capability_probe_result`, observed dates/timestamps, `asset_verification_result`, `run_binding_digest`, and every runtime/post-execution result. The identity digest is `tool_record_digest`.

The Custodian then creates immutable `run-binding.json` outside the child snapshot, binding Planning Base, Candidate SHA/tree, Integration Base, exact Integration Candidate SHA/tree, that verified source-tree digest, tool-lock digest, `tool_record_digest`, Custodian origin, run id, issue/expiry, and a one-time nonce, and then issues a single-use host gate carrying the canonical binding digest. The Host may only read, inspect, and validate the delivered snapshot handoff, pre-execution record, binding, gate, and seven inputs before it starts a real process; it has no Git, snapshot materialization, copy, transformation, mutation, or separate-source execution authority. Only after that validation may it provision/verify assets and run version/capability probes. It writes those post-execution results only to `<state-root>/tools/tool-observations.json`, which references both digests and includes asset verification, version output, probe result, and observed timestamp; it is never passed as `--tool-record` and never rewrites authorization. A static identity, binding, or Integration Candidate change requires a new snapshot/record/binding/gate and full rerun; a runtime observation mismatch or failed result fails closed. This is the executable ADR-0018 model, not vague Integration Candidate prose.

## Git, authority, and capability isolation

The Git Custodian delivers a read-only validation handoff of the child snapshot containing no `.git` file or directory to Host and exposes it only as source tree usable by the untrusted Sandbox Agent child. That source-tree restriction applies only to that child, not to repository CI or the Git Custodian. The Host may only read, inspect, and validate the delivered handoff and its source-tree digest exactly equal to the Integration-Candidate tree digest before launch; it has no Git, snapshot materialization, copy, transformation, mutation, or separate-source execution authority. Child HOME/XDG/Git state is under state root and its executable allowlist has neither Git nor a shell-string bypass.

Each `CapabilityProfile` field is measured per platform as `ENFORCED`, `OBSERVED_ONLY`, `UNSUPPORTED_RUNTIME`, or `NOT_APPLICABLE`. A hard network-deny profile is unsupported unless OS-level enforcement is demonstrated. Same-user ACLs are normally observed only; a lower-privilege identity or OS sandbox is required for enforced filesystem claims. Process fencing uses Windows Job Objects or Linux process groups plus a zero-survivor scan. Hermes, rather than vendor output sanitizers, bounds and redacts all captured output.

## Vendor and project-support registers

Official OpenAI documentation currently describes a native Windows sandbox workflow and WSL2 as an alternative Linux route: <https://learn.chatgpt.com/docs/windows/windows-sandbox> and <https://learn.chatgpt.com/docs/windows/wsl>. That vendor fact is not sealed-runtime acceptance. The project classifies Windows Codex as `UNSUPPORTED_RUNTIME` solely because the locked evidence lacks an independently sourced exact Authenticode signer identity. Vendor documentation, artifact evidence, and dated project probe results remain separate registers.

## E2E shape and READY disposition

The required controlled E2E is:

`local loopback mock provider -> OpenCode -> Chrome DevTools MCP -> headless MCP temporary-profile Chrome -> local fixture -> cleanup`

It must demonstrate a real browser operation, temporary-profile cleanup, process-tree cleanup, bounded/redacted evidence, and the capability verdict. `tools/list` is not E2E evidence.

READY review and Git Custodian worktree assignment are complete in revision 14. ADR-0029 and ADR-0030 are accepted, the contract is bound to exact Base `9cf24b876cc7422386ed54c277900ff1e3c2c2bf`, and execution is limited to the assigned Managed Worktree and machine-contract permitted paths. A later human-approved revision is still required if Chrome for Testing must become sealed or Windows Codex needs a real sealed probe without an independently sourced exact signer identity. D2 and D3 are those ADRs. D4 is the two-line E2E. D5 is the three-register model. D6 is the four-state matrix. There is no open D1.

## Primary references consulted

- Node.js release signing keys: <https://github.com/nodejs/release-keys>
- Node.js release distribution: <https://nodejs.org/dist/>
- Chrome for Testing availability: <https://googlechromelabs.github.io/chrome-for-testing/>
- Chrome DevTools MCP project: <https://github.com/ChromeDevTools/chrome-devtools-mcp>
- Codex Windows sandbox documentation: <https://learn.chatgpt.com/docs/windows/windows-sandbox>
- Codex WSL documentation: <https://learn.chatgpt.com/docs/windows/wsl>
- Codex project and releases: <https://github.com/openai/codex>
- OpenCode project and npm registry metadata: <https://github.com/anomalyco/opencode>
