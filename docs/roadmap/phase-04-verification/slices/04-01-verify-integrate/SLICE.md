# Slice 04-01 — Integration Candidate, sandbox, E2E, Acceptance

Status: **READY**. Branch: `feat/slice-04-01-verify-integrate`.

## Must

Build an Integration Candidate from Candidate SHA + Integration Base. Run E2E (Chrome MCP fake) and Acceptance (reviewer binding) in a Verification Sandbox that is always cleaned up. Both COMPLETED → READY + Delivery RECORDED. E2E/Acceptance fail → REWORK, no delivery. A new SHA after a pass is DRIFT.

## Out

Real GitHub PR, merge authority, live Chrome, real Codex Acceptance.
