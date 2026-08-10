"""Alembic migration spike tests (slice-00-04, AC-12).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Upgrade and rollback run on a temporary spike database; the selected
transaction semantics are recorded; a failure injected during a *real*
migration run (env.py hooks: mid-run and after-commit) leaves the database
in a partial state that recovers only through the verified backup and
restore path into a fresh staging file; the migration helper returns
bounded typed results and never exposes raw driver exceptions; the evidence
records that ``begin_transaction()`` is a logical migration transaction and
never claims whole-migration rollback atomicity for SQLite DDL.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from hermes_pipeline.persistence.backup import backup_database, restore_backup
from hermes_pipeline.persistence.migration_helpers import (
    MigrationResult,
    run_downgrade,
    run_upgrade,
)
from hermes_pipeline.persistence.migration_spike.env import (
    run_migrations_offline,
    run_migrations_online,
)


def _assert_empty_failure_detail(result: MigrationResult) -> None:
    """Ensure a failed helper never exposes driver-derived detail to pytest."""
    if result.detail != "":
        raise AssertionError("migration helper leaked failure detail")


def _assert_bounded_invalid_revision(result: MigrationResult, revision: str) -> None:
    """Check a caller-controlled revision without echoing it on regression."""
    rendered = repr(result) + result.detail
    if (
        result.ok
        or result.revision != ""
        or result.executed_revisions != ()
        or revision in rendered
        or chr(10) in rendered
        or chr(13) in rendered
        or chr(9) in rendered
        or chr(7) in rendered
    ):
        raise AssertionError(
            "migration helper returned an unsafe invalid-revision result"
        )


def _tables(database: Path) -> set[str]:
    conn = sqlite3.connect(database)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    return {str(row[0]) for row in rows}


def _revision(database: Path) -> str | None:
    conn = sqlite3.connect(database)
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        conn.close()
    return str(row[0]) if row is not None else None


def test_upgrade_and_rollback_on_temporary_spike_database(
    tmp_path: Path,
) -> None:
    """Positive: upgrade from the bootstrap schema and rollback to the prior
    revision succeed on the temporary spike database."""
    database = tmp_path / "migrate.db"
    upgrade = run_upgrade(database, "head")
    assert upgrade.ok
    assert upgrade.operation == "upgrade"
    assert upgrade.executed_revisions == ("0001", "0002")
    tables = _tables(database)
    assert "migration_spike_item" in tables
    assert "migration_spike_marker" in tables
    assert "alembic_version" in tables

    rollback = run_downgrade(database, "base")
    assert rollback.ok
    assert rollback.operation == "downgrade"
    assert rollback.executed_revisions == ("0002", "0001")
    assert "migration_spike_item" not in _tables(database)


def test_migration_helper_returns_bounded_typed_results(
    tmp_path: Path,
) -> None:
    """The helper returns bounded typed results; a failing migration
    surfaces as ok=False without any raw driver exception text."""
    database = tmp_path / "typed.db"
    result = run_upgrade(database, "head")
    assert isinstance(result, MigrationResult)
    assert result.ok
    # A nonexistent revision is a preflight-only failure: the helper bounds
    # it and never raises. (Recovery evidence comes from the real-run fault
    # injections in the P1-3 tests, not from this preflight case.)
    failed = run_upgrade(database, "does-not-exist")
    assert isinstance(failed, MigrationResult)
    assert not failed.ok
    if failed.revision != "":
        raise AssertionError("migration helper returned an unsafe revision")
    _assert_empty_failure_detail(failed)
    assert failed.executed_revisions == ()
    # The failure did not leave the database broken beyond recovery: the
    # previous head state is still reachable.
    again = run_upgrade(database, "head")
    assert again.ok
    # An unknown fault mode is a programming error, never a driver output.
    with pytest.raises(AssertionError):
        run_upgrade(database, "head", fault="does-not-exist")


@pytest.mark.parametrize(
    "revision",
    (
        pytest.param("migration-canary-token", id="token-canary"),
        pytest.param(
            "migration-canary-token" + chr(10) + "next-line",
            id="control-canary",
        ),
        pytest.param("migration-canary-token" * 100, id="oversized-canary"),
    ),
)
def test_invalid_migration_revision_is_bounded_and_never_echoes_input(
    tmp_path: Path, revision: str
) -> None:
    """The helper returns a fixed safe result for an unknown revision rather
    than copying a caller-controlled revision into a typed result."""
    result = run_upgrade(tmp_path / "invalid-revision.db", revision)
    _assert_bounded_invalid_revision(result, revision)


def test_subclassed_revision_and_fault_values_fail_closed(tmp_path: Path) -> None:
    """Pre-validation never invokes hostile string-subclass equality hooks."""

    class LeakyString(str):
        def __hash__(self) -> int:
            return hash(str(self))

        def __eq__(self, other: object) -> bool:
            del other
            raise RuntimeError("migration-canary" + chr(10) + "detail" + chr(7))

    revision = LeakyString("head")
    result = run_upgrade(tmp_path / "subclassed-revision.db", revision)
    _assert_bounded_invalid_revision(result, "migration-canary")

    fault = LeakyString("")
    with pytest.raises(AssertionError) as excinfo:
        run_upgrade(tmp_path / "subclassed-fault.db", "head", fault=fault)
    rendered = str(excinfo.value)
    if "migration-canary" in rendered or chr(10) in rendered or chr(7) in rendered:
        raise AssertionError("migration helper leaked a subclassed fault")


def test_injected_migration_failure_recovers_through_backup_and_restore(
    tmp_path: Path,
) -> None:
    """AC-12 (rework 2, P1-3): a failure injected during a *real* migration
    run leaves the database in a genuine partial state, and recovery goes
    through the verified backup and restore path into a fresh staging file
    with the data complete. The fault is not a preflight-only failure: the
    env.py hook raises after the migration transaction committed and first
    writes a stray partial artifact through a separate raw connection, so
    the database has advanced schema plus a partial artifact while the
    operation reports failure."""
    database = tmp_path / "recover.db"
    backup_path = tmp_path / "recover-backup.db"
    staging = tmp_path / "recover-staging.db"

    # Acknowledged pre-failure state at revision 0001 with one data row.  The
    # later faulted upgrade therefore has a real pending 0002 script to run.
    first = run_upgrade(database, "0001")
    assert first.ok
    assert first.executed_revisions == ("0001",)
    conn = sqlite3.connect(database)
    conn.execute("INSERT INTO migration_spike_item (id, name) VALUES (1, 'ack-0001')")
    conn.commit()
    conn.close()

    backup = backup_database(database, backup_path)
    assert backup.ok
    assert backup.integrity_ok
    assert backup.foreign_keys_ok

    # Injected failure during a real pending migration execution
    # ("after-commit" fault mode): 0002 actually enters and commits, then
    # the env.py hook writes the stray partial artifact and raises.
    failed = run_upgrade(database, "head", fault="after-commit")
    assert isinstance(failed, MigrationResult)
    assert not failed.ok
    _assert_empty_failure_detail(failed)
    assert failed.executed_revisions == ("0002",)
    tables = _tables(database)
    assert "migration_spike_item" in tables
    assert "migration_spike_marker" in tables  # 0002 script actually ran
    assert "migration_spike_partial" in tables  # stray partial artifact
    assert _revision(database) == "0002"  # the database advanced to 0002
    # The database is in a partial/unavailable state: no acknowledged
    # migration sequence produced a database with both the advanced schema
    # and the stray partial artifact, so the state cannot be trusted and
    # recovery is through the verified backup path only.

    # Recovery: verified backup restored into a fresh staging file, with
    # the pre-failure data complete.
    restore = restore_backup(backup_path, staging)
    assert restore.ok
    assert restore.integrity_ok
    assert restore.foreign_keys_ok
    staging_tables = _tables(staging)
    assert "migration_spike_item" in staging_tables
    assert "migration_spike_marker" not in staging_tables
    assert "migration_spike_partial" not in staging_tables
    assert _revision(staging) == "0001"
    conn = sqlite3.connect(staging)
    row = conn.execute(
        "SELECT id, name FROM migration_spike_item WHERE id = 1"
    ).fetchone()
    conn.close()
    assert row == (1, "ack-0001")  # data complete after restore


def test_in_transaction_migration_fault_fails_during_real_run(
    tmp_path: Path,
) -> None:
    """AC-12 (rework 2, P1-3): the "mid-run" fault raises inside the real
    migration transaction (immediately after the migration scripts ran);
    the operation reports failure through the typed result, and the
    verified backup/restore path recovers the acknowledged state. The
    evidence records that whole-migration rollback atomicity is never
    promised — whatever this platform's observed behavior is."""
    database = tmp_path / "midrun.db"
    backup_path = tmp_path / "midrun-backup.db"
    staging = tmp_path / "midrun-staging.db"

    first = run_upgrade(database, "0001")
    assert first.ok
    assert first.executed_revisions == ("0001",)
    conn = sqlite3.connect(database)
    conn.execute("INSERT INTO migration_spike_item (id, name) VALUES (1, 'ack-midrun')")
    conn.commit()
    conn.close()
    backup = backup_database(database, backup_path)
    assert backup.ok

    failed = run_upgrade(database, "head", fault="mid-run")
    assert isinstance(failed, MigrationResult)
    assert not failed.ok
    _assert_empty_failure_detail(failed)
    # This assertion is independent of SQLite DDL rollback semantics: the
    # helper-owned trace can only contain 0002 if Alembic actually entered
    # the pending migration script before the in-transaction fault.
    assert failed.executed_revisions == ("0002",)

    restore = restore_backup(backup_path, staging)
    assert restore.ok
    assert "migration_spike_item" in _tables(staging)
    assert "migration_spike_marker" not in _tables(staging)
    assert _revision(staging) == "0001"
    conn = sqlite3.connect(staging)
    row = conn.execute(
        "SELECT id, name FROM migration_spike_item WHERE id = 1"
    ).fetchone()
    conn.close()
    assert row == (1, "ack-midrun")


def test_transaction_semantics_are_recorded_and_atomicity_not_promised(
    tmp_path: Path,
) -> None:
    """The env module documents begin_transaction() as a logical migration
    transaction; whole-migration rollback atomicity is never promised."""
    source = Path(run_migrations_online.__code__.co_filename)
    text = source.read_text(encoding="utf-8")
    assert "logical" in text.lower() or "begin_transaction" in text
    # The spike module must never promise whole-migration atomicity.
    helper_text = (
        Path(__file__)
        .resolve()
        .parents[3]
        .joinpath("src", "hermes_pipeline", "persistence", "migration_helpers.py")
    )
    # Whitespace-insensitive: the docstring wraps the phrase across lines.
    normalized = " ".join(helper_text.read_text(encoding="utf-8").lower().split())
    assert "rollback atomicity is never promised" in normalized


def test_migration_env_modules_are_importable() -> None:
    """Both env functions are importable without a live migration run."""
    assert callable(run_migrations_offline)
    assert callable(run_migrations_online)
