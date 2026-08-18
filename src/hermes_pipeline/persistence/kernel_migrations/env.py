"""Alembic environment for the kernel transaction store.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_PHASE_01
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

target_metadata = None


def run_migrations_offline() -> None:
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


def _dispatch_migrations() -> None:
    try:
        offline = context.is_offline_mode()
    except NameError:
        return
    if offline:
        run_migrations_offline()
    else:
        run_migrations_online()


_dispatch_migrations()
