---
status: superseded by ADR-0018
---

# Freeze each Pipeline to an immutable Base SHA

The Pipeline Controller resolves the selected target reference to one immutable Base SHA when a Pipeline is created, so every Stage works from a reproducible source baseline rather than a moving branch. Later target-reference movement never silently rebases or updates an active Pipeline: only an authorized human Baseline Refresh decision may keep the current baseline, replace it and invalidate all affected downstream work and approvals, or cancel the Pipeline.

ADR-0018 preserves this decision as the immutable Planning Base SHA while replacing the single-baseline delivery model with separate integration identities and automatic target-drift revalidation.
