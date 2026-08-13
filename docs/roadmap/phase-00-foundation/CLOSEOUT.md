# Phase 00 Closeout — Engineering Foundation and Technology Lock

Status: `DRAFT` (Slice 00-07 execution; not yet Phase-Gate accepted)

Contract: Slice 00-07 revision 2 (`content_hash` `sha256:f2de1f88dc6b4e7089ec209953b5742a7637bc1355319ba5dbce4edbec8cbe40`)

Planning Base SHA: `078411b20283288ab2ec85f081d3ed463fba96e4`

Planning merge / worktree start HEAD: `d5672acd53df8630b2ac3be8d50c723ee60f9cc2`

Candidate SHA: assigned by the Git Custodian when this worktree is committed.

## Delivered capability

- eight External Interface Protocols with frozen dataclasses, deterministic fakes, and shared contract tests (`controller`, `stage_executor`, `runtime_broker`, `artifacts`, `repository`, `delivery`, `interaction`, `operations`);
- adopted Hermes Shim lifecycle in place: `hermes pipeline setup|doctor|start|status|stop` as a non-production skeleton;
- stdlib offline `scripts/sbom_preview.py` and `scripts/check_dependency_audit.py` required by `python-quality.yml`;
- committed install/upgrade/rollback preview `docs/development/compatibility-manifest.preview.json` (`update_apply` is `manual-only`);
- doctor/health uses `FakeOperations.health()`; the Hermes-loaded Shim remains stdlib-only and does not import `hermes_pipeline`.

## Accepted planning decisions D1–D6

| ID | Decision |
| --- | --- |
| D1 | Adopt `plugin.yaml`, root `__init__.py`, and `hermes_shim/` lifecycle in place. Do not move the five commands into `src/hermes_pipeline/cli/`. |
| D2 | `transport/` remains a keep-marked fake runtime for the EC-00-07 demo. It is not production Control Interface foundation. |
| D3 | Adopt `ControllerPort.submit` (existing `ControllerCommand` / `CommandReceipt` and 00-04 mapping on the spike Controller) and add fake-only `read`. Persistence SQLite/migration spikes stay keep-marked. `counter_spike` stays a non-public oracle. |
| D4 | Entire `runtime_broker/` Host/probe tree stays keep-marked evidence. Isolation, Chrome for Testing, and Windows sealed Codex are not sealed runtime. |
| D5 | SBOM preview and dependency audit are stdlib/offline over `uv.lock`. No CycloneDX, syft, pip-audit, or public CVE network. Artifact retention is committed preview files, not `actions/upload-artifact`. |
| D6 | Compatibility is a documentation-plus-fixture JSON preview. No new public Schema and no automatic apply. |

No new ADR was required.

## Retain / keep-marked / delete table

| Component | Paths | Disposition |
| --- | --- | --- |
| CounterSpike oracle | `src/hermes_pipeline/domain/counter_spike.py` | `RETAIN_NON_PUBLIC_CANDIDATE` |
| Shim lifecycle | `plugin.yaml`, `__init__.py`, `hermes_shim/` | `ADOPTED_BY_00-07` |
| Hermes integration workflow | `.github/workflows/hermes-integration.yml` | `ADOPTED_BY_00-07` |
| Eight Interface Protocols and fakes | `src/hermes_pipeline/<pkg>/ports.py`, `fake.py` | `ADOPTED_BY_00-07` |
| Fake loopback runtime | `src/hermes_pipeline/transport/` | `KEEP_MARKED_EVIDENCE` |
| Runtime-env topology | `runtime-env/` | keep-marked in meaning; file still `DELETE_UNLESS_ADOPTED_BY_00-07` because `runtime-env/` is outside this Slice's write authority |
| Persistence / migration spikes | `src/hermes_pipeline/persistence/` | `KEEP_MARKED_EVIDENCE` |
| Spike Controller / private persistence port | `controller/spike_controller.py`, `_persistence_port.py` | `KEEP_MARKED_EVIDENCE` |
| LangGraph checkpoint spike | `stage_executor/_graph_spike.py` | `KEEP_MARKED_EVIDENCE` |
| Runtime Broker Host/probes | `runtime_broker/_*.py`, `tools_bootstrap.py`, `controlled_e2e.py` | `KEEP_MARKED_EVIDENCE` |

## Evidence SHAs

- Slice 00-04 integrated: `46798d86a2e48551a3a634e93d1e4dfe5cbf8786`
- Slice 00-05 integrated: `102d08f814b6c0a939662e6c488870310a97c1ee`
- Slice 00-06 integrated / 00-07 Planning Base: `078411b20283288ab2ec85f081d3ed463fba96e4`
- 00-07 contract landed: `d5672acd53df8630b2ac3be8d50c723ee60f9cc2`

Windows and Linux CI on the Candidate is required after Git Custodian publication.

## Residual risks

- Isolation (AppContainer / namespaces) remains `UNSUPPORTED_RUNTIME` on this workstation and ordinary PR CI.
- Chrome for Testing remains experimental (`no_official_checksum`) and is not a sealed hard-gate.
- Windows sealed Codex remains `UNSUPPORTED_RUNTIME` until an independently sourced Authenticode signer identity is pinned.
- Hard network deny without OS-level enforcement remains `UNSUPPORTED_RUNTIME`.
- Keep-marked transport and runtime_broker probes must not be treated as production foundation.
- Compatibility preview does not apply updates.

## Phase 1 prerequisites

- A human-accepted Phase 00 Gate on the exact Candidate.
- Phase 1 must not promote keep-marked spikes, isolation, CfT, or Windows sealed Codex without a new ADR.
- Phase 1 business state machine, Project RBAC, live Feishu/GitHub, and automatic update apply remain out of scope until separately contracted.
- Compatibility changes outside the preview pins (Python 3.12.13, uv 0.12.1, `hermes-pipeline` 0.1.0) require a compatibility Slice.
