---
status: accepted
---

# Separate planning and integration source identities

Each Pipeline records an immutable Planning Base SHA for PRD, Architecture, and initial Development, a Controller-created Candidate SHA, the current Integration Base SHA, and the exact Integration Candidate SHA evaluated by final checks.

Ordinary target movement creates a new Integration Candidate and automatically reruns required integration verification; it does not reopen the approved solution or require human approval. Only a material semantic conflict may raise a human Baseline Refresh Request. Final MR or PR approval binds to the exact verified integration head.

This decision supersedes ADR-0011's single-baseline delivery model while preserving its immutable planning-baseline guarantee.
