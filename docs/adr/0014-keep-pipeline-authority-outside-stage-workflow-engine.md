---
status: accepted
---

# Keep Pipeline authority outside the Stage workflow engine

The append-only Pipeline Event Log is the sole authoritative business history. The Pipeline Controller accepts immutable, authenticated Commands through Inbox deduplication, optimistic revision checks, and one transaction that appends Events, updates rebuildable projections, and creates Outbox Effects. Stage ownership uses leases and monotonically increasing fencing generations.

LangGraph or another workflow engine may implement the replaceable Stage Executor and persist internal checkpoints, interrupts, tasks, retries, and resumable execution state. It cannot write Pipeline state, authorize transitions, or become a second fact source. Stable Controller Command identities make Stage replay and at-least-once delivery safe without a distributed transaction between workflow checkpoints and Pipeline storage.
