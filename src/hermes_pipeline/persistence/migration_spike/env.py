"""Alembic migration environment for the slice-00-04 spike.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

This environment runs migrations against a temporary spike database only.
``context.begin_transaction()`` is a *logical* migration transaction: its
real atomicity for SQLite DDL depends on the dialect, online or offline
mode, transactional DDL support, and ``transaction_per_migration``. The
spike never promises whole-migration rollback atomicity (AC-12); an
injected migration failure recovers through the verified backup and
recovery path instead.

Fault injection (AC-12, rework 2 P1-3): the migration helper may request a
deterministic fault through ``context.config.attributes["spike_fault"]``,
raising during a *real* migration run — never a preflight-only failure:

- ``"mid-run"``: raised inside the migration transaction immediately after
  the migration scripts ran, i.e. mid-upgrade in-transaction;
- ``"after-commit"``: raised after the migration transaction committed; the
  hook first writes a stray partial artifact (``migration_spike_partial``)
  through a separate raw connection, so the database is left in a genuine
  partial state — schema advanced and a partial artifact present while the
  operation reports failure. Recovery goes through the verified backup and
  restore path into a fresh staging file.
"""

from __future__ import annotations

import sqlite3

from alembic import context
from sqlalchemy import engine_from_config, pool

# The spike migrations are plain DDL; no declarative metadata is used.
target_metadata = None


class InjectedMigrationFault(Exception):
    """Deterministic fault raised inside a real migration run (AC-12).

    Carries no driver text; the migration helper bounds it into a typed
    ``MigrationResult``.
    """


def _fault_mode() -> str:
    """The fault mode requested by the migration helper, or ""."""
    return str(context.config.attributes.get("spike_fault", ""))


def _inject_after_commit_partial_state() -> None:
    """Write a stray partial artifact through a separate raw connection.

    The migration transaction has committed and the engine connection is
    closed, so no write lock is held; the raw autocommit write is
    deterministic. This leaves the database with a partial artifact that no
    acknowledged migration produced (AC-12, P1-3 partial-state evidence).
    """
    path = context.config.attributes.get("spike_fault_db_path")
    if not path:
        return
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE migration_spike_partial (id INTEGER PRIMARY KEY)")
    finally:
        conn.close()


def run_migrations_offline() -> None:
    """Run migrations in offline mode (URL-only, no connection)."""
    url = context.config.get_main_option("sqlalchemy.url")
    assert url is not None
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode against the configured database."""
    configuration = context.config.get_section(context.config.config_ini_section, {})
    assert configuration is not None
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
            if _fault_mode() == "mid-run":
                raise InjectedMigrationFault("injected mid-run migration fault (AC-12)")
    if _fault_mode() == "after-commit":
        _inject_after_commit_partial_state()
        raise InjectedMigrationFault("injected after-commit migration fault (AC-12)")


def _dispatch_migrations() -> None:
    """Run migrations only when Alembic's EnvironmentContext proxy exists.

    Alembic establishes the proxy before executing this module as its
    migration script; a direct import (spike tests import these functions to
    assert the transaction-semantics record) has no proxy and must not run a
    migration at import time.
    """
    try:
        offline = context.is_offline_mode()
    except NameError:
        return
    if offline:
        run_migrations_offline()
    else:
        run_migrations_online()


_dispatch_migrations()
