"""Alembic migration helper for the slice-00-04 spike (AC-12).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Upgrade and rollback run on a temporary spike database. The helper returns
bounded typed results (``MigrationResult``) and never exposes raw driver
exceptions, SQL, paths, or database content.

Transaction semantics (recorded evidence): Alembic's
``context.begin_transaction()`` (see ``migration_spike/env.py``) is a
*logical* migration transaction. The spike records that its real atomicity
for SQLite DDL depends on the dialect, online or offline mode, transactional
DDL, and ``transaction_per_migration``; whole-migration rollback atomicity
is never promised. An injected migration failure recovers through the
verified backup and recovery path (AC-07).

Fault injection (AC-12, rework 2 P1-3): ``run_upgrade(..., fault=...)``
requests a deterministic fault raised during a *real* migration run through
the env.py hooks — ``"mid-run"`` inside the migration transaction and
``"after-commit"`` after the transaction committed (leaving a genuine
partial database state). The fault is test-only, bounded, and never carries
driver text into results.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from alembic import command
from alembic.config import Config


@dataclass(frozen=True)
class MigrationResult:
    """Bounded typed result of one migration command."""

    ok: bool
    operation: str
    revision: str
    detail: str = ""
    #: Fixed revision identifiers whose migration script actually entered.
    #: This is test-only, bounded evidence; arbitrary caller input is never
    #: copied into the result.
    executed_revisions: tuple[str, ...] = ()


#: Test-only fault modes plumbed into the env.py hooks (AC-12, P1-3).
SPIKE_FAULT_MODES: frozenset[str] = frozenset({"", "mid-run", "after-commit"})

#: The spike's complete, finite revision vocabulary.  The helper accepts
#: only these values so its typed results can never reflect an arbitrary
#: caller-provided revision string.
SPIKE_REVISIONS: frozenset[str] = frozenset({"base", "head", "0001", "0002"})


def _spike_script_dir() -> Path:
    return Path(__file__).resolve().parent / "migration_spike"


def _config_for(database_path: Path) -> Config:
    script_dir = _spike_script_dir()
    cfg = Config(str(script_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(script_dir))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    # Migration scripts append only their own fixed revision IDs to this
    # list.  It is bounded evidence that a pending script was actually
    # entered, even when SQLite's observed DDL rollback behavior differs by
    # platform.
    cfg.attributes["spike_executed_revisions"] = []
    return cfg


def _safe_revision(revision: object) -> str | None:
    """Return a fixed allowed revision, never an arbitrary caller value."""
    if type(revision) is str and revision in SPIKE_REVISIONS:
        return revision
    return None


def _executed_revisions(config: Config | None) -> tuple[str, ...]:
    """Read the fixed execution trace written by spike migration scripts."""
    if config is None:
        return ()
    trace: object = config.attributes.get("spike_executed_revisions")
    if not isinstance(trace, list):
        return ()
    return tuple(
        item
        for item in cast(list[object], trace)
        if type(item) is str and item in SPIKE_REVISIONS
    )


def run_upgrade(
    database_path: Path | str, revision: object = "head", fault: object = ""
) -> MigrationResult:
    """Upgrade the temporary spike database to ``revision``.

    ``fault`` must be one of ``SPIKE_FAULT_MODES``; it requests a
    deterministic migration-run fault via the env.py hooks so the injected
    failure happens during a real migration execution, never as a
    preflight-only failure (AC-12, P1-3).
    """
    safe_revision = _safe_revision(revision)
    if safe_revision is None:
        return MigrationResult(ok=False, operation="upgrade", revision="")
    if type(fault) is not str or fault not in SPIKE_FAULT_MODES:
        raise AssertionError("unknown spike fault mode")
    config: Config | None = None
    try:
        path = Path(database_path)
        config = _config_for(path)
        config.attributes["spike_fault"] = fault
        config.attributes["spike_fault_db_path"] = str(path)
        command.upgrade(config, safe_revision)
    except Exception:
        return MigrationResult(
            ok=False,
            operation="upgrade",
            revision=safe_revision,
            executed_revisions=_executed_revisions(config),
        )
    return MigrationResult(
        ok=True,
        operation="upgrade",
        revision=safe_revision,
        executed_revisions=_executed_revisions(config),
    )


def run_downgrade(
    database_path: Path | str, revision: object = "base"
) -> MigrationResult:
    """Roll the temporary spike database back to ``revision``."""
    safe_revision = _safe_revision(revision)
    if safe_revision is None:
        return MigrationResult(ok=False, operation="downgrade", revision="")
    config: Config | None = None
    try:
        path = Path(database_path)
        config = _config_for(path)
        command.downgrade(config, safe_revision)
    except Exception:
        return MigrationResult(
            ok=False,
            operation="downgrade",
            revision=safe_revision,
            executed_revisions=_executed_revisions(config),
        )
    return MigrationResult(
        ok=True,
        operation="downgrade",
        revision=safe_revision,
        executed_revisions=_executed_revisions(config),
    )


__all__ = [
    "SPIKE_FAULT_MODES",
    "SPIKE_REVISIONS",
    "MigrationResult",
    "run_downgrade",
    "run_upgrade",
]
