"""Online backup and restore helper for spike databases (slice-00-04, AC-07).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE

Backup and restore go through the Python ``sqlite3.Connection.backup`` API
only, while readers or writers may be active. The policy rejects the
raw-copy path before any I/O: requesting ``mode="raw"`` raises
``RawCopyForbidden`` immediately, and a guard test proves the helper only
ever calls ``sqlite3.Connection.backup()``. No test asserts that a raw copy
"necessarily corrupts" a database.

The helper returns bounded typed results (``BackupResult`` /
``RestoreResult``) and never exposes raw driver exceptions, SQL, paths, or
database content. Restored copies are validated with ``PRAGMA
integrity_check`` and ``PRAGMA foreign_key_check`` before a success result
is returned. Restore follows the "fresh staging target" boundary: an
existing target file is rejected before any I/O, so a restore never
silently overwrites an existing database (AC-07).
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import cast

#: Allowed backup modes. ``raw`` exists only so the policy can reject it
#: before any file I/O; the implementation supports ``online`` only.
BACKUP_MODES: frozenset[str] = frozenset({"online", "raw"})


class RawCopyForbidden(Exception):
    """The raw-copy backup path is rejected before any file I/O."""


class BackupFailure(Exception):
    """Bounded, sensitive-free backup/restore failure (no raw driver text)."""


@dataclass(frozen=True)
class BackupResult:
    """Bounded typed result of one online backup."""

    ok: bool
    source_sha256: str
    target_sha256: str
    integrity_ok: bool
    foreign_keys_ok: bool
    detail: str = ""


@dataclass(frozen=True)
class RestoreResult:
    """Bounded typed result of one restore into a fresh database file."""

    ok: bool
    target_sha256: str
    integrity_ok: bool
    foreign_keys_ok: bool
    detail: str = ""


@dataclass(frozen=True)
class _FileDigest:
    sha256: str = ""
    integrity_ok: bool = False
    foreign_keys_ok: bool = False


def _path_from_boundary(value: object) -> Path:
    """Convert a helper boundary value to ``Path`` inside its safe wrapper."""
    return Path(cast(str | PathLike[str], value))


def _paths_from_boundary(first: object, second: object) -> tuple[Path, Path] | None:
    """Return two boundary paths or a neutral failure marker.

    A caller-supplied ``PathLike`` may throw arbitrary exceptions while
    converting itself, including a forged ``BackupFailure``.  The caller
    maps the marker to its fixed public diagnostic only after this handler
    has completed, so no raw exception chain can cross the helper boundary.
    """
    try:
        return (_path_from_boundary(first), _path_from_boundary(second))
    except Exception:
        return None


def _digest_and_validate(path: Path) -> _FileDigest:
    """SHA-256 plus integrity and foreign-key checks of one database file."""
    try:
        raw = path.read_bytes()
    except OSError:
        return _FileDigest()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        conn = sqlite3.connect(path)
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchall()
            foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return _FileDigest(sha256=digest)
    integrity_ok = len(integrity) == 1 and str(integrity[0][0]) == "ok"
    return _FileDigest(
        sha256=digest,
        integrity_ok=integrity_ok,
        foreign_keys_ok=len(foreign_keys) == 0,
    )


def backup_database(
    source: object,
    target: object,
    mode: object = "online",
) -> BackupResult:
    """Back up ``source`` into a fresh ``target`` via the online backup API.

    ``mode="raw"`` is rejected before any file I/O with ``RawCopyForbidden``.
    The only copy path implemented is ``sqlite3.Connection.backup()``; the
    guard test proves this by mocking the backup method.
    """
    if type(mode) is not str or mode not in BACKUP_MODES:
        # This test-helper Interface is deliberately sensitive-free.  Never
        # echo an arbitrary caller-controlled mode value in an exception.
        raise BackupFailure("unsupported backup mode")
    if mode == "raw":
        raise RawCopyForbidden("raw-copy backup is rejected before any I/O")

    try:
        source_path = _path_from_boundary(source)
        target_path = _path_from_boundary(target)
        source_conn = sqlite3.connect(source_path)
        try:
            target_conn = sqlite3.connect(target_path)
            try:
                source_conn.backup(target_conn)
            finally:
                target_conn.close()
        finally:
            source_conn.close()
        source_digest = _digest_and_validate(source_path)
        target_digest = _digest_and_validate(target_path)
        ok = (
            target_digest.integrity_ok
            and target_digest.foreign_keys_ok
            and source_digest.integrity_ok
            and source_digest.foreign_keys_ok
        )
    except Exception:
        # Leave the except suite before raising the safe boundary exception:
        # ``raise ... from None`` still retains the raw exception in
        # ``__context__`` for programmatic consumers.
        pass
    else:
        return BackupResult(
            ok=ok,
            source_sha256=source_digest.sha256,
            target_sha256=target_digest.sha256,
            integrity_ok=target_digest.integrity_ok,
            foreign_keys_ok=target_digest.foreign_keys_ok,
            detail="" if ok else "restored copy failed validation",
        )
    raise BackupFailure("backup failed")


def restore_backup(backup_path: object, target: object) -> RestoreResult:
    """Restore one online backup into a fresh staging target database file.

    The restore boundary is "first restore into a fresh staging file":
    ``target`` must be a *non-existent* file. An existing target (for
    example a live Controller database) is rejected with ``BackupFailure``
    before any file I/O, so a restore can never silently overwrite an
    existing database; callers copy or move the verified staging file into
    place explicitly after a successful restore.
    """
    paths = _paths_from_boundary(backup_path, target)
    if paths is None:
        raise BackupFailure("restore failed")
    backup_file, target_file = paths

    target_exists = False
    result: RestoreResult | None = None
    try:
        target_exists = target_file.exists()
        if not target_exists:
            source_conn = sqlite3.connect(backup_file)
            try:
                target_conn = sqlite3.connect(target_file)
                try:
                    source_conn.backup(target_conn)
                finally:
                    target_conn.close()
            finally:
                source_conn.close()
            target_digest = _digest_and_validate(target_file)
            ok = target_digest.integrity_ok and target_digest.foreign_keys_ok
            result = RestoreResult(
                ok=ok,
                target_sha256=target_digest.sha256,
                integrity_ok=target_digest.integrity_ok,
                foreign_keys_ok=target_digest.foreign_keys_ok,
                detail="" if ok else "restored copy failed validation",
            )
    except Exception:
        # Raise after the handler so neither __cause__ nor __context__ keeps
        # a raw driver/path exception reachable through this helper boundary.
        pass

    if result is not None:
        return result
    if target_exists:
        raise BackupFailure("restore target must be a non-existent fresh staging file")
    raise BackupFailure("restore failed")


__all__ = [
    "BACKUP_MODES",
    "BackupFailure",
    "BackupResult",
    "RawCopyForbidden",
    "RestoreResult",
    "backup_database",
    "restore_backup",
]
