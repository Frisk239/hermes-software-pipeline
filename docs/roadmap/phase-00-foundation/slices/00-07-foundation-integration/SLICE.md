# Slice 00-07 — Foundation Integration (DRAFT, revision 1)

Status: **DRAFT**. Human decisions D1–D6 below are accepted in planning chat on 2026-08-13. This package is not READY until an independent review passes and the Git Custodian assigns a clean worktree at Base `078411b20283288ab2ec85f081d3ed463fba96e4`.

- Planning Base: `078411b20283288ab2ec85f081d3ed463fba96e4` (origin/main after PR #14).
- Predecessors: `slice-00-04`, `slice-00-05`, `slice-00-06`.
- Owns: revalidation of `EC-00-01`–`EC-00-11` and `EC-00-12` Phase Closeout.

## Accepted planning decisions

| ID | Decision |
| --- | --- |
| D1 | Adopt `plugin.yaml`, root `__init__.py`, and `hermes_shim/` lifecycle CLI in place. Do not move `setup/doctor/start/status/stop` into `src/hermes_pipeline/cli/`. |
| D2 | `transport/` remains a keep-marked fake runtime for the EC-00-07 demo. It is not production Control Interface foundation. |
| D3 | Adopt `ControllerCommandPort.submit` as the public Controller mutation Interface and add `read`. Persistence SQLite/migration spikes stay keep-marked. `counter_spike` stays a non-public oracle. |
| D4 | Entire `runtime_broker/` and 00-06 probes stay keep-marked evidence. Isolation/CfT/Windows sealed Codex must not be claimed as sealed runtime. |
| D5 | SBOM preview and dependency audit are stdlib/offline over `uv.lock`. No CycloneDX, syft, pip-audit, or public CVE network. Artifact retention is committed preview files, not `actions/upload-artifact`. |
| D6 | Install/upgrade/rollback compatibility is a documentation-plus-fixture JSON preview. No new public Schema and no automatic apply. |

No new ADR is required under these decisions.

## Must

- Export typed Protocols for the eight architecture External Interfaces, each with a deterministic fake Adapter and shared contract tests. Types are module dataclasses/Protocols, not new committed JSON Schemas.
- Adopt the 00-05 Shim lifecycle; re-run PluginManager, source-install, lifecycle idempotency, doctor, and restart exactly-once evidence on this Slice's Candidate.
- Add `scripts/sbom_preview.py` and `scripts/check_dependency_audit.py` (stdlib, offline) and wire them into `python-quality.yml` by updating the exact command multiset and fixtures.
- Commit `docs/development/compatibility-manifest.preview.json` describing install identity and upgrade/rollback policy without applying updates.
- Flip DISPOSITION markers to match D1–D4. Update README so the five pipeline commands are documented as a non-production skeleton.
- Write `docs/roadmap/phase-00-foundation/CLOSEOUT.md` satisfying EC-00-12.

## Out

Phase 1 business behavior; production RBAC/approvals; live Feishu/GitHub; moving lifecycle into `hermes_pipeline.cli`; formal CycloneDX/signed SBOM; online vulnerability databases; CI artifact uploads; automatic update application.

## Demonstration

A clean install on the exact Candidate runs a fake command from Hermes through Shim and the keep-marked fake runtime and back, survives restart, exposes doctor/status health, and passes every mandatory Windows/Linux check.
