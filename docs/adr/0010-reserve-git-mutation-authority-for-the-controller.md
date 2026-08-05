---
status: accepted
---

# Reserve Git mutation authority for the Controller

Pipeline Agents may inspect Git and modify ordinary files inside their assigned Managed Worktree, but only the Pipeline Controller may mutate Git structure or create commits. The Controller withholds remote credentials, validates the resulting file set and Development evidence, and creates the Candidate SHA itself; version 1 grants neither Agents nor the Controller push, merge, rebase, tag, reset, clean, branch-management, or worktree-management authority outside the Controller's narrowly defined local operations.
