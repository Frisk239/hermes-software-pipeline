# Slice 03-01 — Project registration and requirement intake

Status: **READY**. Branch: `feat/slice-03-01-project-intake`.

## Must

Register a Project, admit ADMIN/CONTRIBUTOR/VIEWER. CONTRIBUTOR/ADMIN may confirm a requirement through `KernelController.submit`. Unknown project → `NOT_FOUND`. Non-member and VIEWER → `AUTHORIZATION_DENIED` with no Event. Empty text after auth → `empty requirement`.

## Out

PRD Stage, Architecture, Solution Approval, Managed Worktree, real IdP.
