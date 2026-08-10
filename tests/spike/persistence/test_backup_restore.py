"""Online backup and restore tests (slice-00-04, AC-07).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Online backup via ``sqlite3.Connection.backup`` while readers or writers
are active, then restore into a fresh staging database file, validating
with ``PRAGMA integrity_check`` and ``PRAGMA foreign_key_check``. The
backup API and policy reject the raw-copy path before any I/O, and a guard
or mock proves the implementation only ever calls
``sqlite3.Connection.backup()``. Restore follows the fresh-staging-target
boundary: an existing target is rejected before any I/O (a restore never
silently overwrites an existing database). No assertion that a raw copy
necessarily corrupts the database is permitted. The helper returns bounded
typed results and never exposes raw driver exceptions.

The active-writer and active-reader scenarios use explicit synchronization
barriers: the writer/reader enters a controlled active state (open
transaction) and stays active until the backup completes, and the ordered
timeline proves the backup ran while the peer was active (AC-07
semantics).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from tests.spike.conftest import make_event_id_provider, make_spike_command

from hermes_pipeline.controller.spike_controller import SpikeController
from hermes_pipeline.persistence.backup import (
    BackupFailure,
    RawCopyForbidden,
    backup_database,
    restore_backup,
)
from hermes_pipeline.persistence.sqlite_spike import SqliteControllerStore

#: A fake sensitive value that must never appear in helper output.
_FAKE_TOKEN = "fake-secret-token-0000"


def _assert_safe_text(rendered: str, forbidden: tuple[str, ...]) -> None:
    """Fail closed without letting pytest echo an unsafe value on regression."""
    if (
        any(value in rendered for value in forbidden)
        or chr(10) in rendered
        or chr(13) in rendered
        or chr(9) in rendered
        or chr(7) in rendered
    ):
        raise AssertionError("unsafe backup helper diagnostic")


def _assert_exact_safe_text(
    rendered: str, expected: str, forbidden: tuple[str, ...]
) -> None:
    """Check a fixed helper result without rendering an unsafe actual value."""
    if rendered != expected:
        raise AssertionError("backup helper returned an unexpected diagnostic")
    _assert_safe_text(rendered, forbidden)


def _assert_no_exception_chain(error: BaseException) -> None:
    """The helper boundary must not retain raw exceptions for loggers."""
    if error.__cause__ is not None or error.__context__ is not None:
        raise AssertionError("backup helper retained an unsafe exception chain")


def _populate(database: Path, count: int, seed: str) -> None:
    store = SqliteControllerStore(database)
    controller = SpikeController(
        store,
        lambda: datetime(2026, 1, 1),
        make_event_id_provider(f"evt_bk_{seed}"),
    )
    for index in range(count):
        receipt = controller.submit(
            make_spike_command(
                f"cmd_bk_{seed}_{index:04d}",
                expected_revision=index,
                payload_extra={"token": _FAKE_TOKEN},
            )
        )
        assert receipt.status == "ACCEPTED"
    store.close()


def test_online_backup_and_restore_validates_restored_copy(
    tmp_path: Path,
) -> None:
    """Positive: a backup taken mid-activity restores to a fully valid,
    queryable copy with integrity and foreign-key checks passing."""
    source = tmp_path / "source.db"
    backup_path = tmp_path / "backup.db"
    restored = tmp_path / "restored.db"
    _populate(source, 3, "a")

    result = backup_database(source, backup_path)
    assert result.ok
    assert result.integrity_ok
    assert result.foreign_keys_ok
    assert result.source_sha256
    assert result.target_sha256

    restore = restore_backup(backup_path, restored)
    assert restore.ok
    assert restore.integrity_ok
    assert restore.foreign_keys_ok

    # The restored copy is fully queryable.
    conn = sqlite3.connect(restored)
    try:
        count = conn.execute("SELECT COUNT(*) FROM spike_events").fetchone()
    finally:
        conn.close()
    assert count is not None and count[0] == 3


def test_restore_rejects_existing_target_before_any_io(tmp_path: Path) -> None:
    """AC-07 negative: restore follows the fresh-staging-target boundary —
    an existing target file (for example a live database) is rejected
    before any file I/O, and the existing file is left untouched."""
    source = tmp_path / "rr-source.db"
    backup_path = tmp_path / "rr-backup.db"
    _populate(source, 1, "x")
    assert backup_database(source, backup_path).ok

    # An existing database at the target path must never be overwritten.
    existing = tmp_path / "rr-existing.db"
    _populate(existing, 1, "y")
    before = existing.read_bytes()
    with pytest.raises(BackupFailure) as excinfo:
        restore_backup(backup_path, existing)
    _assert_exact_safe_text(
        str(excinfo.value),
        "restore target must be a non-existent fresh staging file",
        (str(existing),),
    )
    _assert_no_exception_chain(excinfo.value)
    # Pre-I/O rejection: the existing file is byte-identical afterwards.
    assert existing.read_bytes() == before
    conn = sqlite3.connect(existing)
    try:
        count = conn.execute("SELECT COUNT(*) FROM spike_events").fetchone()
    finally:
        conn.close()
    assert count is not None and count[0] == 1  # the original content


def test_backup_while_writer_is_active_is_consistent(
    tmp_path: Path,
) -> None:
    """AC-07: the writer explicitly enters a controlled active state (an
    open write transaction on the Controller database) and stays active
    until the backup completes; the ordered timeline proves the backup ran
    while the writer was active, and the restored copy is valid."""
    source = tmp_path / "active.db"
    backup_path = tmp_path / "active-backup.db"
    _populate(source, 2, "w")

    writer_active = threading.Event()
    release_writer = threading.Event()
    timeline: list[str] = []
    timeline_lock = threading.Lock()

    def record(entry: str) -> None:
        with timeline_lock:
            timeline.append(entry)

    def keep_writing() -> None:
        store = SqliteControllerStore(source)
        controller = SpikeController(
            store,
            lambda: datetime(2026, 1, 1),
            make_event_id_provider("evt_active_w"),
        )
        for index in range(2):
            controller.submit(
                make_spike_command(f"cmd_active_{index:04d}", expected_revision=index)
            )
        # Enter the controlled active state: one real write transaction on
        # the store's engine stays open while the backup runs, so the
        # writer is demonstrably active mid-session (AC-07 semantics).
        with store._engine.begin() as conn:  # type: ignore[attr-defined]
            conn.execute(
                text(
                    "INSERT INTO spike_outbox (command_id, effect_type, "
                    "payload_json) VALUES ('cmd_active_hold', "
                    "'SPIKE_NOOP_EFFECT', '{}')"
                )
            )
            record("writer:transaction-open")
            writer_active.set()
            release_writer.wait(timeout=30)
        record("writer:transaction-closed")
        store.close()

    writer = threading.Thread(target=keep_writing)
    writer.start()
    assert writer_active.wait(timeout=30), "writer never entered its active state"
    record("backup:start")
    result = backup_database(source, backup_path)
    record("backup:end")
    release_writer.set()
    writer.join(timeout=30)
    assert not writer.is_alive(), "writer did not finish after release"

    assert result.ok
    restored = tmp_path / "active-restored.db"
    restore = restore_backup(backup_path, restored)
    assert restore.ok
    # The backup ran entirely inside the writer's active window.
    assert timeline.index("backup:start") > timeline.index("writer:transaction-open")
    assert timeline.index("backup:end") < timeline.index("writer:transaction-closed")


def test_backup_while_reader_is_active_is_consistent(tmp_path: Path) -> None:
    """AC-07: a reader with an open read transaction stays active while the
    backup runs; the ordered timeline proves the backup ran during the
    read, and the restored copy is valid."""
    source = tmp_path / "reader.db"
    backup_path = tmp_path / "reader-backup.db"
    _populate(source, 2, "r")

    reader_active = threading.Event()
    release_reader = threading.Event()
    timeline: list[str] = []
    timeline_lock = threading.Lock()

    def record(entry: str) -> None:
        with timeline_lock:
            timeline.append(entry)

    def keep_reading() -> None:
        conn = sqlite3.connect(source)
        try:
            conn.execute("BEGIN")
            conn.execute("SELECT COUNT(*) FROM spike_events").fetchone()
            record("reader:transaction-open")
            reader_active.set()
            release_reader.wait(timeout=30)
            conn.execute("SELECT COUNT(*) FROM spike_events").fetchone()
            record("reader:transaction-closed")
        finally:
            conn.close()

    reader = threading.Thread(target=keep_reading)
    reader.start()
    assert reader_active.wait(timeout=30), "reader never entered its active state"
    record("backup:start")
    result = backup_database(source, backup_path)
    record("backup:end")
    release_reader.set()
    reader.join(timeout=30)
    assert not reader.is_alive(), "reader did not finish after release"

    assert result.ok
    restored = tmp_path / "reader-restored.db"
    restore = restore_backup(backup_path, restored)
    assert restore.ok
    # The backup ran entirely inside the reader's active window.
    assert timeline.index("backup:start") > timeline.index("reader:transaction-open")
    assert timeline.index("backup:end") < timeline.index("reader:transaction-closed")


def test_raw_copy_mode_rejected_before_any_io(tmp_path: Path) -> None:
    """Negative: a raw-copy request is rejected by the API before any file
    I/O; no backup file is created."""
    source = tmp_path / "raw-source.db"
    target = tmp_path / "raw-target.db"
    _populate(source, 1, "r")
    with pytest.raises(RawCopyForbidden):
        backup_database(source, target, mode="raw")
    assert not target.exists()


@pytest.mark.parametrize(
    "mode",
    (
        pytest.param(_FAKE_TOKEN, id="token-canary"),
        pytest.param(_FAKE_TOKEN + chr(10) + "next-line", id="control-canary"),
        pytest.param(_FAKE_TOKEN * 100, id="oversized-canary"),
    ),
)
def test_invalid_backup_mode_is_bounded_and_never_echoes_input(
    tmp_path: Path, mode: str
) -> None:
    """An unsupported helper mode is rejected before I/O with fixed safe
    text, even when it contains a token, controls, or an oversized value."""
    target = tmp_path / "invalid-mode-target.db"
    with pytest.raises(BackupFailure) as excinfo:
        backup_database(tmp_path / "not-opened.db", target, mode=mode)
    _assert_exact_safe_text(str(excinfo.value), "unsupported backup mode", (mode,))
    assert not target.exists()


def test_subclassed_backup_mode_fails_closed_before_membership_check(
    tmp_path: Path,
) -> None:
    """A hostile str subclass cannot escape through mode pre-validation."""

    class LeakyMode(str):
        def __hash__(self) -> int:
            return hash(str(self))

        def __eq__(self, other: object) -> bool:
            del other
            raise RuntimeError(_FAKE_TOKEN + chr(10) + "mode-detail" + chr(7))

    with pytest.raises(BackupFailure) as excinfo:
        backup_database(
            tmp_path / "not-opened.db",
            tmp_path / "subclass-mode-target.db",
            mode=LeakyMode("online"),
        )
    _assert_exact_safe_text(
        str(excinfo.value), "unsupported backup mode", (_FAKE_TOKEN,)
    )
    _assert_no_exception_chain(excinfo.value)


def test_invalid_helper_paths_are_bounded_and_never_echo_input(tmp_path: Path) -> None:
    """Bad path-like inputs cannot leak their representation through either
    helper Interface."""

    class PoisonPath:
        def __init__(self, error_type: type[Exception]) -> None:
            self._error_type = error_type

        def __fspath__(self) -> str:
            raise self._error_type(_FAKE_TOKEN + chr(10) + "path-detail" + chr(7))

    for error_type in (ValueError, RuntimeError, BackupFailure):
        poison = PoisonPath(error_type)
        with pytest.raises(BackupFailure) as excinfo:
            backup_database(poison, tmp_path / "not-opened.db")
        _assert_exact_safe_text(str(excinfo.value), "backup failed", (_FAKE_TOKEN,))
        _assert_no_exception_chain(excinfo.value)

        with pytest.raises(BackupFailure) as excinfo:
            restore_backup(poison, tmp_path / "not-restored.db")
        _assert_exact_safe_text(str(excinfo.value), "restore failed", (_FAKE_TOKEN,))
        _assert_no_exception_chain(excinfo.value)


def test_guard_proves_only_backup_api_is_used(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard: the helper only ever calls sqlite3.Connection.backup(); a
    direct copy implementation would fail the guard. Connections are wrapped
    (sqlite3.Connection is an immutable C type, so the method cannot be
    replaced in place) and every copy primitive call is recorded."""
    source = tmp_path / "guard-source.db"
    backup_path = tmp_path / "guard-backup.db"
    _populate(source, 1, "g")

    calls: list[str] = []
    real_connect = sqlite3.connect

    class RecordingConnection:
        def __init__(self, real: sqlite3.Connection) -> None:
            self._real = real

        def backup(self, target: object, **kw: object) -> None:
            calls.append("backup")
            real_target = (
                target._real  # type: ignore[attr-defined]
                if isinstance(target, RecordingConnection)
                else target
            )
            return self._real.backup(real_target, **kw)  # type: ignore[arg-type]

        def close(self) -> None:
            self._real.close()

        def __getattr__(self, name: str) -> object:
            return getattr(self._real, name)

    def recording_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        return RecordingConnection(real_connect(*args, **kwargs))  # type: ignore[arg-type]

    monkeypatch.setattr(
        "hermes_pipeline.persistence.backup.sqlite3.connect", recording_connect
    )
    result = backup_database(source, backup_path)
    assert result.ok
    # The only copy primitive observed is the online backup API.
    assert calls == ["backup"]


def test_raw_driver_exception_never_escapes_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative: a raw driver exception escaping the backup helper fails."""
    source = tmp_path / "fail-source.db"
    backup_path = tmp_path / "fail-backup.db"
    _populate(source, 1, "f")

    real_connect = sqlite3.connect

    class BrokenSource:
        def __init__(self, real: sqlite3.Connection) -> None:
            self._real = real

        def backup(self, target: object, **kw: object) -> None:
            raise sqlite3.OperationalError(
                _FAKE_TOKEN + chr(10) + "driver-detail" + chr(7)
            )

        def close(self) -> None:
            self._real.close()

    def broken_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        return BrokenSource(real_connect(*args, **kwargs))  # type: ignore[arg-type]

    monkeypatch.setattr(
        "hermes_pipeline.persistence.backup.sqlite3.connect", broken_connect
    )
    with pytest.raises(BackupFailure) as excinfo:
        backup_database(source, backup_path)
    _assert_exact_safe_text(str(excinfo.value), "backup failed", (_FAKE_TOKEN,))
    _assert_no_exception_chain(excinfo.value)


def test_restore_driver_exception_never_retains_exception_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-07 negative: restore hides driver text and removes its exception chain."""
    source = tmp_path / "restore-fail-source.db"
    target = tmp_path / "restore-fail-target.db"
    _populate(source, 1, "restore-fail")
    real_connect = sqlite3.connect

    class BrokenSource:
        def __init__(self, real: sqlite3.Connection) -> None:
            self._real = real

        def backup(self, target: object, **kw: object) -> None:
            raise sqlite3.OperationalError(
                _FAKE_TOKEN + chr(10) + "restore-detail" + chr(7)
            )

        def close(self) -> None:
            self._real.close()

    def broken_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        return BrokenSource(real_connect(*args, **kwargs))  # type: ignore[arg-type]

    monkeypatch.setattr(
        "hermes_pipeline.persistence.backup.sqlite3.connect", broken_connect
    )
    with pytest.raises(BackupFailure) as excinfo:
        restore_backup(source, target)
    _assert_exact_safe_text(str(excinfo.value), "restore failed", (_FAKE_TOKEN,))
    _assert_no_exception_chain(excinfo.value)


def test_helper_output_contains_no_sensitive_value_or_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The bounded typed results never carry raw exception text, database
    content, sensitive values, or absolute paths."""
    source = tmp_path / "leak-source.db"
    backup_path = tmp_path / "leak-backup.db"
    _populate(source, 1, "l")
    result = backup_database(source, backup_path)
    assert result.ok
    rendered = repr(result) + result.detail
    _assert_safe_text(rendered, (_FAKE_TOKEN, "Traceback", str(tmp_path)))
    captured = capsys.readouterr()
    _assert_safe_text(captured.out + captured.err, (_FAKE_TOKEN,))
