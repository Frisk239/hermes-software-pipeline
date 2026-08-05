---
status: accepted
---

# Isolate by write and verification boundary instead of role

Each Pipeline owns one persistent writable Managed Worktree for Development, while read-only PRD and Architecture sessions consume controlled immutable source views and each E2E or Acceptance execution receives a clean short-lived Verification Sandbox at the exact source identity required by the delivery model. ADR-0018 defines that final verification identity as the Integration Candidate SHA. Additional worktrees are created only for concurrent writers, competing Candidates, or explicit forensic retention, avoiding the cost and false coupling of one long-lived worktree per logical role or attempt.
