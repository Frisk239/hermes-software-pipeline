---
status: accepted
---

# Use SQLite with one Controller writer in version 1

Version 1 stores the Controller Event Log, Inbox, projections, Outbox, approvals, leases, and artifact metadata in a local SQLite database using WAL mode, but only the active Pipeline Controller may write it; workers and Adapters submit Controller Commands. SQLAlchemy Core and Alembic isolate persistence details and preserve a PostgreSQL migration path when multiple Controller replicas, high availability, or tested write-volume thresholds require it. LangGraph checkpoints use a separate database and never share the business transaction.
