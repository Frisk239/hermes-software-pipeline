# Slice 00-04: Domain and persistence spike dependency research

- Status: evidence for planning; not an architecture or dependency decision
- Snapshot date: 2026-08-07
- Scope: SQLite Controller persistence, SQLAlchemy Core and Alembic seams,
  LangGraph persistence/replay, and Python 3.12 package facts
- Source policy: primary documentation, upstream source, and PyPI metadata only

## Evidence

### SQLite WAL, backup, and recovery

SQLite WAL allows readers and a writer to proceed concurrently, but there can
only be one writer at a time. WAL requires all processes accessing one database
to run on the same host; it is not supported over a network filesystem.
Applications must still handle `SQLITE_BUSY`. [SQLite WAL concurrency and
limits](https://www.sqlite.org/wal.html#concurrency)

The WAL file is part of durable database state. Copying or moving a live
WAL-mode database without its `-wal` file can lose committed transactions or
corrupt the database. The supported snapshot primitive is the SQLite online
backup API: it can copy incrementally while readers/writers continue, and a
completed backup is a snapshot of the source when copying began.
[SQLite WAL-file handling](https://www.sqlite.org/wal.html#the_wal_file)
[SQLite online backup API](https://www.sqlite.org/backup.html)

CPython 3.12 exposes the online backup primitive as
`sqlite3.Connection.backup(target, pages=..., progress=...)`; the Python
documentation states it works while other clients access the database. Python
3.12 also exposes `Connection.autocommit`, although the documented default is
still legacy transaction control. [Python 3.12 sqlite3 backup
API](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup)
[Python 3.12 transaction control](https://docs.python.org/3.12/library/sqlite3.html#transaction-control)

As of this snapshot, SQLite documents a rare WAL-reset corruption race fixed in
SQLite 3.51.3 and later, with backports 3.50.7 and 3.44.6. The risk applies when
two or more connections use one WAL database and write/checkpoint at the same
instant. Python exposes the linked SQLite library through
`sqlite3.sqlite_version`; the actual Windows and Linux runtime versions must
therefore be measured rather than inferred from the Python version.
[SQLite WAL-reset bug and fixed versions](https://www.sqlite.org/wal.html#walreset)
[Python sqlite3 runtime-version attribute](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.sqlite_version)

### SQLAlchemy Core and Alembic seams

SQLAlchemy Core's `Engine.begin()` provides one connection and transaction
context: successful exit commits and an exception rolls back. This is an
appropriate persistence-adapter seam for the one atomic Controller write that
inserts Inbox, Event, projection, Outbox, and receipt records together.
[SQLAlchemy 2.0 Engine.begin documentation](https://docs.sqlalchemy.org/en/20/core/connections.html#sqlalchemy.engine.Engine.begin)

Alembic's `begin_transaction()` is explicitly a *logical* migration
transaction. Whether it becomes a real transaction depends on the dialect,
online/offline mode, transactional DDL, and `transaction_per_migration`.
Migration execution must therefore remain separate from a Controller command
transaction and carry its own backup/rollback evidence.
[Alembic migration transaction semantics](https://alembic.sqlalchemy.org/en/latest/api/runtime.html#alembic.runtime.migration.MigrationContext.begin_transaction)

The Python 3.12 `sqlite3` driver defaults to legacy transaction control. In
that mode it does not automatically begin transactions for `SELECT`, DDL, or
`SAVEPOINT`; SQLAlchemy documents `connect_args={"autocommit": False}` or an
explicit `BEGIN` event-hook alternative. The spike must choose and test one
mode instead of relying on the default. Alembic 1.19's SQLite implementation
also declares `transactional_ddl = False`, despite SQLite's underlying DDL
capability, because of the pysqlite driver boundary. Do not promise that an
entire SQLite migration sequence is rollback-atomic.
[SQLAlchemy SQLite transaction modes](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#transactions-with-sqlite-and-the-sqlite3-driver)
[Alembic SQLite implementation source](https://github.com/sqlalchemy/alembic/blob/rel_1_19_0/alembic/ddl/sqlite.py#L34-L40)

### LangGraph persistence, interruption, and replay

LangGraph checkpointers persist graph-state snapshots per `thread_id`; this
state is thread-scoped execution state, not a cross-thread application store.
The official documentation positions `SqliteSaver` as local file storage for
development and tells production users to choose a persistent checkpointer.
[LangGraph persistence model](https://docs.langchain.com/oss/python/langgraph/persistence)

An interrupt is resumed with the same `thread_id`, but the containing node
starts again from its beginning. Consequently, code before an interrupt may run
again and must be idempotent. [LangGraph interrupt replay
rules](https://docs.langchain.com/oss/python/langgraph/interrupts)

LangGraph exposes `exit`, `async`, and `sync` durability modes. `async` can
lose a pending checkpoint on a process crash; `sync` persists the checkpoint
before the next step begins. This changes graph-recovery evidence, but cannot
make the checkpoint authoritative for a Controller business transition.
[LangGraph durability modes](https://docs.langchain.com/oss/python/langgraph/checkpointers#durability-modes)

The current upstream SQLite checkpointer source uses a SQLite implementation
and declares `langgraph-checkpoint`, `aiosqlite`, and `sqlite-vec` as direct
dependencies. It is therefore not a zero-dependency extension of Python's
stdlib `sqlite3`. [Upstream checkpoint-sqlite package
metadata](https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-sqlite/pyproject.toml)

## Python 3.12 and package facts

The following are package metadata observations on 2026-08-07, not selected
constraints. Every listed `Requires-Python` range admits Python 3.12.

| Package | Current version | Requires-Python | Direct dependency implication |
| --- | ---: | --- | --- |
| SQLAlchemy | 2.0.51 | `>=3.7` | Core adds its own dependency set; do not treat it as stdlib. |
| Alembic | 1.19.0 | `>=3.10` | Requires SQLAlchemy, Mako, and typing extensions. |
| LangGraph | 1.2.10 | `>=3.10` | Requires LangChain Core, checkpoint, prebuilt, SDK, Pydantic, and xxhash. |
| langgraph-checkpoint-sqlite | 3.1.1 | `>=3.10` | Requires langgraph-checkpoint, aiosqlite, and sqlite-vec. |

The authoritative version, Python-requirement, and dependency data are the
respective [SQLAlchemy](https://pypi.org/pypi/SQLAlchemy/json),
[Alembic](https://pypi.org/pypi/alembic/json),
[LangGraph](https://pypi.org/pypi/langgraph/json), and
[SQLite checkpointer](https://pypi.org/pypi/langgraph-checkpoint-sqlite/json)
PyPI metadata documents.

`sqlite-vec` 0.1.9 currently publishes Windows x64 and manylinux x64/aarch64
wheels, but wheel presence is only installation evidence. It is not a
cross-platform behavioral guarantee; the frozen Windows and Linux CI matrix
must resolve and execute the selected dependency graph.
[sqlite-vec release file metadata](https://pypi.org/pypi/sqlite-vec/json)

## Risks and unknowns

1. The repository currently has no SQLAlchemy, Alembic, LangGraph, or
   checkpointer dependency family. Adding any of them is a new dependency
   decision; the existing empty runtime dependency set cannot silently become
   a runtime installation contract.
2. The exact SQLite library version embedded in the selected Python 3.12
   distributions is unknown. A snapshot that exercises concurrent WAL writes
   and checkpoints must record it on both required platforms and stop if it
   does not meet the chosen recovery-safety policy.
3. A long reader can prevent WAL checkpoint completion and cause WAL growth.
   The workload proof must measure WAL size, checkpoint outcome/latency, busy
   errors, and writer latency instead of asserting that WAL alone provides an
   unlimited concurrency guarantee. [SQLite checkpoint
   behavior](https://www.sqlite.org/wal.html#checkpointing)
4. LangGraph replay is intentionally capable of rerunning a node. Treating a
   checkpoint as authoritative business state, or letting a node directly
   mutate Controller tables, would create an unbounded duplicate-transition
   path.
5. The package graph includes a native-wheel-adjacent `sqlite-vec` dependency;
   its licensing, security posture, transitive resolution, and Windows/Linux
   reproducibility need explicit admission evidence before it is locked.
6. `PRAGMA integrity_check` verifies low-level structure but not foreign-key
   violations, which require `PRAGMA foreign_key_check`. SQLite's `.recover`
   path is salvage only: it can lose, resurrect, alter, or constraint-break
   content. Recovery acceptance must use a verified online backup plus explicit
   integrity/foreign-key checks, not a claim that salvage reconstructs an
   authoritative Event Log. [SQLite integrity and foreign-key
   checks](https://www.sqlite.org/pragma.html#pragma_integrity_check)
   [SQLite recovery limitations](https://www.sqlite.org/recovery.html)

## Planning implications (recommendations, not decisions)

1. Keep `domain` and Controller policy free of SQLAlchemy, Alembic, LangGraph,
   and concrete SQLite imports. Put SQLAlchemy Core behind a private
   persistence port; put Alembic in migration tooling; put LangGraph only in
   the Stage Executor. This is consistent with the repository's accepted
   dependency direction and avoids turning a feasibility spike into an ambient
   runtime dependency.
2. Use two physical databases in the spike: a Controller database for the
   atomic Inbox/Event/projection/Outbox/receipt transaction, and a separate
   LangGraph checkpoint database. Do not attempt a cross-database transaction.
   Replay should resubmit a stable Controller command identity and obtain the
   original receipt, proving that a replay cannot append a second business
   event.
3. Make the persistence spike evidence explicit: inject failure before and
   after each durable Controller write; restart from the database/WAL; show
   all four Controller records committed together or none; verify duplicate,
   revision-conflict, and stale-fencing paths; create and restore a backup via
   the SQLite backup API rather than raw file copying; validate the restored
   copy with `integrity_check` and `foreign_key_check`.
4. Add a workload report with declared workload, hardware/runner identity,
   `sqlite3.sqlite_version`, selected PRAGMAs, queue/writer latency, busy
   count, WAL high-water mark, checkpoint results, backup duration, and
   recovery result. The declared limits should be the acceptance boundary; a
   failed limit must trigger the already-planned replacement-ADR path rather
   than a claim that SQLite will scale indefinitely.
5. For the LangGraph proof, use a deterministic graph node that calls the
   Controller port with a fixed command ID, interrupt/restart/replay it, and
   assert one accepted Event and one stable receipt. The test should also prove
   that the checkpoint database has no authority to advance the Controller.
   Use `sync` durability for the checkpoint-loss/replay test, and separately
   prove that even an absent or stale checkpoint cannot duplicate the
   Controller command.

## Decisions requiring human approval before an Executor is dispatched

1. Admit a new, explicitly versioned dependency family (SQLAlchemy Core,
   Alembic, LangGraph, and the SQLite checkpointer with its full transitive
   shape), and record whether Slice 00-04 uses it only for development/CI
   spikes or establishes an isolated managed-runtime installation path.
2. Choose the exact frozen version constraints after a clean Windows/Linux
   resolution, including the acceptance or rejection of `sqlite-vec`.
3. Choose the SQLite runtime safety floor and response if the selected Python
   distribution exposes an older SQLite library than the accepted WAL recovery
   policy permits.
4. Choose the v1 workload/concurrency envelope and measurable stop thresholds
   for writer latency, busy failures, WAL growth, checkpoint completion, backup
   time, and restart recovery.
5. Confirm that `SqliteSaver` remains a feasibility/local-execution
   checkpointer for this Slice, rather than a production authority or a shared
   business database. The recommended answer is yes.
6. Choose the SQLite driver transaction mode and the migration recovery policy;
   neither legacy transaction control nor rollback-atomic Alembic migration
   batches should be assumed by default.

No source above authorizes a production migration, a public service, a shared
database transaction with LangGraph, or a change to Hermes plugin dependency
rules. Those are deliberately outside this research note and need their own
approved contract/ADR if proposed.
