---
status: accepted
---

# Use LangGraph StateGraph only inside the Stage Executor

Version 1 implements resumable Agent Stage orchestration with LangGraph `StateGraph` and a separate SQLite checkpointer, one graph thread per Execution Run. Graph state holds execution data and Controller receipts but no authoritative Pipeline status; nodes reach business state only through idempotent Controller Commands. The Stage Executor Interface also has a deterministic fake Adapter so Controller tests and most CI never require LangGraph, a model, or an external CLI.
