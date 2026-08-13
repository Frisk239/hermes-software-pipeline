# Slice 00-06 Closeout — Agent and Runtime Security Spikes

Status: `ACCEPTED`

Contract revision: `14`

Base SHA: `9cf24b876cc7422386ed54c277900ff1e3c2c2bf`

Candidate SHA: `9ca0670c8527bdfc21696f1f87b397a507221ef4`

Integrated SHA: `078411b20283288ab2ec85f081d3ed463fba96e4`

Pull Request: [#14 — feat: implement slice 00-06 agent runtime security spikes](https://github.com/Frisk239/hermes-software-pipeline/pull/14)

Closed: 2026-08-13

## Accepted capability

- typed Codex and OpenCode adapter probes classify structured output, timeout, cancellation, and process-tree fencing; Windows sealed Codex remains `UNSUPPORTED_RUNTIME`;
- Host runners `tools_bootstrap.py` and `controlled_e2e.py` require the seven Custodian inputs and reject before process creation when authorization is missing (`DEPENDENCY_UNAVAILABLE`);
- isolation proof attempts the lock-specified AppContainer / namespace child probe and fail-closes as `UNSUPPORTED_RUNTIME` when any assertion is absent;
- controlled E2E wiring (fixture page, three-call mock provider, closed MCP argv, OpenCode config, success oracle) is implemented and unit-tested; `tools/list` is never the oracle;
- hostile path, symlink, 8.3, Git metadata, secret-canary, and egress-canary negatives are recorded; Windows drive paths are rejected on Linux as well as Windows;
- spike components are marked `SPIKE-EXPERIMENTAL` with `DELETE_UNLESS_ADOPTED_BY_00-07`;
- ordinary PR CI gained no 00-06 workflow and continues to run the existing full offline pytest suite.

## Evidence

- review verdict `PASS` on the implementation tree, then rebound to Candidate `26fc778` and CI-fix heads `ac4c1c8`, `82ddb56`, and `9ca0670`;
- two Executor rework attempts plus a bounded Codex corrective (isolation child probe and E2E oracle) under the repository rework rule; later CI-only fixes were format, Linux pyright narrowing, and cross-platform drive-path rejection;
- final Candidate `9ca0670` CI passed on Windows and Ubuntu: [python-quality push](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/31674866522), [python-quality PR](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/31674868943), [hermes-integration push](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/31674866391), [hermes-integration PR](https://github.com/Frisk239/hermes-software-pipeline/actions/runs/31674869009);
- PR #14 merged as `078411b20283288ab2ec85f081d3ed463fba96e4`.

## Residual debt

- this workstation and hosted CI do not demonstrate a passing AppContainer / namespace child probe; real Host success lines remain unrun and fail-closed;
- Chrome for Testing stays `no_official_checksum` and is excluded from sealed hard-gates;
- Windows sealed Codex stays `UNSUPPORTED_RUNTIME` until an independently sourced Authenticode signer identity is pinned;
- hard network deny without OS-level enforcement stays `UNSUPPORTED_RUNTIME`;
- 00-04 and 00-05 Closeouts are backfilled in the same documentation Candidate as this file;
- nothing in `runtime_broker/` is production foundation until Slice 00-07 adopts, rewrites, or deletes it.

## Next prerequisites

- Slice 00-07 uses integrated SHA `078411b20283288ab2ec85f081d3ed463fba96e4` as its planning Base;
- 00-07 must decide retain/delete for every 00-04 / 00-05 / 00-06 spike component and must not treat unproven isolation or CfT as sealed runtime.
