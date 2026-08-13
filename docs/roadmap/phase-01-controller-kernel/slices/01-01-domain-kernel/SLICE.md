# Slice 01-01 — Domain Kernel (DRAFT, revision 1)

Status: **READY** (revision 2). Assigned worktree: `C:\Users\a2691\AppData\Local\hermes\managed-worktrees\hermes-software-pipeline\slice-01-01`. Machine contract is authoritative.

## Must

Pure fake-Pipeline aggregate in `src/hermes_pipeline/domain/`:

- States: `UNCONFIRMED`, `OPEN`, `REJECTED`
- Commands: `ConfirmRequirement(text: str)`, `RejectRequirement(reason: str)`
- Events: `RequirementConfirmed(text)`, `RequirementRejected(reason)`
- Initial state: `UNCONFIRMED` revision `0`
- `ConfirmRequirement` from `UNCONFIRMED` with nonempty text → `OPEN`, revision+1, event `RequirementConfirmed`
- `RejectRequirement` from `UNCONFIRMED` with nonempty reason → `REJECTED`, revision+1, event `RequirementRejected`
- Empty text/reason → `EMPTY_REQUIREMENT`, state unchanged, no event
- Any other transition → `INVALID_TRANSITION`, state unchanged, no event
- `Clock` Protocol with `now() -> datetime` lives in `domain/clock.py`; the evaluator must not call it or import `datetime.now`
- No SQL, filesystem, LangGraph, or Adapter imports
- Do not edit `counter_spike.py`

Tests: `tests/domain/test_pipeline_aggregate.py` plus a property test that forbidden states stay unreachable.

## Out

Persistence, Controller wiring, projections, Outbox, leases, RBAC.
