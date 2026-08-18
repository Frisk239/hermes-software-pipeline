# Slice 03-05 — Development and Candidate

Status: **READY**. Branch: `feat/slice-03-05-development-candidate`.

## Must

After a fresh Solution Baseline, an executor binding writes implementation into a Managed Worktree (not the user copy), stores the payload in CAS, and records a Candidate SHA. Secret canary or path escape is denied. Candidate Gate requires fresh baseline, verifying artifact, and a 64-hex SHA.

## Out

Real Git commit, remote PR, E2E/Acceptance Stages, user-working-copy writes.
