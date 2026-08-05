---
status: superseded by ADR-0013
---

# Isolate all Agent work in Managed Worktrees

Every Pipeline Stage executes in a Controller-managed Git worktree and never in a Project Member's working copy. The additional disk and lifecycle management cost is accepted to protect user changes, permit concurrent Pipelines, bind verification to explicit commits, preserve failure evidence, and make filesystem permissions and cleanup enforceable.
