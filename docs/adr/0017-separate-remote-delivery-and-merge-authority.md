---
status: accepted
---

# Separate remote delivery from approval and merge authority

Agents and the Pipeline Controller receive no remote Git credentials. A separately deployed Remote Delivery Adapter accepts signed, idempotent Delivery Requests, verifies the exact Candidate, pushes only a Pipeline-namespaced branch, and creates or updates exactly one MR or PR.

The Adapter has no administration, approval, merge, force-push, workflow-edit, secret-read, or branch-protection bypass authority. The Git host remains authoritative for reviewer identity, protected-branch status, merge queue outcome, and final merged commit.
