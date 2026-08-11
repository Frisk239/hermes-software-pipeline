"""Runtime descriptor tests (slice-00-05, AC-04/AC-10).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Atomic write (temp + rename), exact field set, owner-only protection,
token randomness per runtime start, stale-descriptor algorithm
(``os.kill(pid, 0)`` plus start marker; never pid-only), and descriptor
path-escape rejection before any write.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from hermes_pipeline.transport import _descriptor as descriptor
from hermes_pipeline.transport._acl import (
    protect_descriptor,
    verify_descriptor_protection,
)
from hermes_pipeline.transport._constants import RELEASE

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "transport"


def _valid_document(tmp_path: Path) -> dict[str, object]:
    return {
        "descriptor_version": 1,
        "protocol_version": 1,
        "pid": os.getpid(),
        "start_identity": "a" * 32,
        "creation_time": "2026-01-01T00:00:00.000000Z",
        "process_start_marker": {"value": "1", "source": "proc_stat_field22"},
        "port": 49152,
        "token": "b" * 64,
        "token_generation": 1,
        "release": RELEASE,
        "state_root_identity": "c" * 64,
    }


def test_write_descriptor_atomic_and_valid(tmp_path: Path) -> None:
    document = _valid_document(tmp_path)
    problems = descriptor.write_descriptor(tmp_path, document)
    assert problems == []
    target = tmp_path / "descriptor" / "runtime.json"
    assert target.is_file()
    # No temp litter remains.
    assert list((tmp_path / "descriptor").glob("*.tmp")) == []
    parsed = descriptor.read_descriptor(tmp_path)
    assert parsed is not None
    assert parsed["port"] == 49152


def test_write_descriptor_rejects_invalid_documents(tmp_path: Path) -> None:
    document = _valid_document(tmp_path)
    document["descriptor_version"] = 99
    assert descriptor.write_descriptor(tmp_path, document) != []
    assert not (tmp_path / "descriptor" / "runtime.json").exists()


def test_golden_descriptor_accepts(tmp_path: Path) -> None:
    golden = json.loads((GOLDEN_DIR / "descriptor-golden.json").read_text("utf-8"))
    assert descriptor.validate_descriptor(golden) == []


@pytest.mark.parametrize(
    "name",
    [
        "descriptor-reject-bad-type.json",
        "descriptor-reject-bad-version.json",
        "descriptor-reject-missing-field.json",
        "descriptor-reject-unknown-field.json",
    ],
)
def test_golden_descriptor_rejects(name: str) -> None:
    document = json.loads((GOLDEN_DIR / name).read_text("utf-8"))
    assert descriptor.validate_descriptor(document) != []


def test_descriptor_protection_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "descriptor" / "runtime.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    problems = protect_descriptor(path)
    assert problems == []
    assert verify_descriptor_protection(path) == []


def test_posix_mode_is_exactly_0600(tmp_path: Path) -> None:
    path = tmp_path / "protected"
    path.write_text("x", encoding="utf-8")
    protect_descriptor(path)
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_read_descriptor_absent_returns_none(tmp_path: Path) -> None:
    assert descriptor.read_descriptor(tmp_path) is None


def test_descriptor_path_escape_rejected(tmp_path: Path) -> None:
    """A descriptor path resolving outside the state root must be rejected.

    The write path always derives from the state root; a symlinked
    descriptor directory escaping the root is detected by resolution and
    the write is refused before any mkdir/temp/replace, so the outside
    directory stays empty.
    """
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    if hasattr(os, "symlink"):
        link = root / "descriptor"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation unavailable")
        target = descriptor.descriptor_path(root).resolve()
        assert not target.is_relative_to(root)
        assert target == (outside / "runtime.json").resolve()
        # The write itself must be refused with zero outside writes.
        problems = descriptor.write_descriptor(root, _valid_document(root))
        assert problems == ["descriptor path escapes state root"]
        assert not (outside / "runtime.json").exists()
        assert list(outside.iterdir()) == []
        # Unlink of an escaping descriptor is likewise refused.
        marker = outside / "runtime.json"
        marker.write_text("sentinel", encoding="utf-8")
        descriptor.remove_descriptor_if_inside(root)
        assert marker.exists(), "escaping descriptor must never be unlinked"


def test_boundary_guard_rejects_escape(tmp_path: Path) -> None:
    """The write-boundary guard rejects any target resolving outside the
    root — the core predicate behind every escape test, independent of
    symlink support on the host."""
    from hermes_pipeline.transport._state import (
        StateRootBoundaryError,
        ensure_inside_state_root,
    )

    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    ensure_inside_state_root(root, root / "descriptor" / "runtime.json")
    with pytest.raises(StateRootBoundaryError):
        ensure_inside_state_root(root, outside / "runtime.json")
    with pytest.raises(StateRootBoundaryError):
        ensure_inside_state_root(root, tmp_path / "elsewhere")


def test_descriptor_escape_rejected_without_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even when the derived path is hijacked to an outside location, the
    write is refused before any mkdir/temp/replace with zero outside
    writes (no symlink support required)."""
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()

    def hijacked_path(_root: Path) -> Path:
        return outside / "runtime.json"

    monkeypatch.setattr(descriptor, "descriptor_path", hijacked_path)
    problems = descriptor.write_descriptor(root, _valid_document(root))
    assert problems == ["descriptor path escapes state root"]
    assert list(outside.iterdir()) == []


def test_lock_escape_rejected_without_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lock filename resolving outside the root fails closed and never
    creates the external file (no symlink support required)."""
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    from hermes_pipeline.transport._lock import StateRootLock, StateRootLockError

    monkeypatch.setattr(
        "hermes_pipeline.transport._lock.LOCK_FILENAME", "../outside.lock"
    )
    with pytest.raises(StateRootLockError):
        StateRootLock(root).acquire()
    assert not (root.parent / "outside.lock").exists()
    assert not (outside / "lock").exists()


def test_shim_read_and_remove_escape_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shim's descriptor read/remove never cross the state-root
    boundary: an escaping path is treated as absent and never unlinked
    (no symlink support required)."""
    from hermes_shim import _descriptor as shim_descriptor

    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "runtime.json"
    sentinel.write_text('{"escaped": true}', encoding="utf-8")

    def hijacked_path(_root: Path) -> Path:
        return sentinel

    monkeypatch.setattr(shim_descriptor, "descriptor_path", hijacked_path)
    # Read: the external file is never read (treated as absent).
    assert shim_descriptor.read_descriptor(root) is None
    # Remove: the external file is never unlinked.
    shim_descriptor.remove_descriptor(root)
    assert sentinel.exists(), "escaping descriptor must never be unlinked"


def test_shim_ensure_layout_escape_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shim's setup layout never creates outside the state root: an
    escaping child name fails closed with zero outside writes."""
    from hermes_shim._state import StateRootBoundaryError, ensure_layout

    outside = tmp_path / "outside"
    monkeypatch.setattr("hermes_shim._state.STATE_ROOT_CHILDREN", ("../outside",))
    with pytest.raises(StateRootBoundaryError):
        ensure_layout(tmp_path)
    assert not outside.exists(), "layout must never escape the state root"


def test_shim_layout_symlink_escape_rejected(tmp_path: Path) -> None:
    """With symlink support, a child directory symlinked outside the root
    is refused before any marker write (zero outside writes)."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    if not hasattr(os, "symlink"):
        pytest.skip("symlink creation unavailable")
    link = root / "descriptor"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    from hermes_shim._state import StateRootBoundaryError, ensure_layout

    with pytest.raises(StateRootBoundaryError):
        ensure_layout(root)
    assert list(outside.iterdir()) == []


def test_receipt_db_escape_rejected_without_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused boundary verdict prevents any database creation (no
    symlink support required)."""
    from hermes_pipeline.transport._receipts import ReceiptStore
    from hermes_pipeline.transport._state import StateRootBoundaryError

    db = tmp_path / "descriptor" / "receipts.sqlite3"

    def refuse(root: Path, target: Path) -> None:
        raise StateRootBoundaryError("escapes")

    monkeypatch.setattr(
        "hermes_pipeline.transport._receipts.ensure_inside_state_root", refuse
    )
    with pytest.raises(StateRootBoundaryError):
        ReceiptStore(tmp_path).open()
    assert not db.exists()


def test_lock_escape_rejected(tmp_path: Path) -> None:
    """A lock file resolving outside the state root fails closed."""
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    if hasattr(os, "symlink"):
        link = root / "runtime.lock"
        try:
            link.symlink_to(outside / "lock", target_is_directory=False)
        except OSError:
            pytest.skip("symlink creation unavailable")
        from hermes_pipeline.transport._lock import StateRootLock, StateRootLockError

        with pytest.raises(StateRootLockError):
            StateRootLock(root).acquire()
        assert not (outside / "lock").exists(), "lock must not escape the root"


def test_receipt_db_escape_rejected(tmp_path: Path) -> None:
    """A receipt database resolving outside the state root fails closed."""
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    if hasattr(os, "symlink"):
        link = root / "descriptor"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation unavailable")
        from hermes_pipeline.transport._receipts import ReceiptStore
        from hermes_pipeline.transport._state import StateRootBoundaryError

        store = ReceiptStore(root)
        with pytest.raises(StateRootBoundaryError):
            store.open()
        assert not (outside / "receipts.sqlite3").exists()


def test_state_root_link_is_rejected_before_any_shim_or_runtime_access(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A link-like state root itself is never resolved into trusted storage.

    Child-path checks alone are insufficient: resolving the root first turns
    a root symlink/junction into an external base and permits all later
    operations.  Exercise the setup/read/remove/provision/lock/receipt and
    runtime-entry boundaries against one external sentinel.
    """
    root = tmp_path / "state-root"
    outside = tmp_path / "outside"
    descriptor_dir = outside / "descriptor"
    descriptor_dir.mkdir(parents=True)
    sentinel = descriptor_dir / "runtime.json"
    sentinel.write_text("sentinel", encoding="utf-8")
    if not hasattr(os, "symlink"):
        pytest.skip("symlink creation unavailable")
    try:
        root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")

    from hermes_shim import _descriptor as shim_descriptor
    from hermes_shim import _state as shim_state
    from hermes_shim._provision import provision_runtime_env

    from hermes_pipeline.transport import _descriptor as runtime_descriptor
    from hermes_pipeline.transport import _main
    from hermes_pipeline.transport._lock import StateRootLock, StateRootLockError
    from hermes_pipeline.transport._receipts import ReceiptStore
    from hermes_pipeline.transport._state import (
        StateRootBoundaryError,
        ensure_inside_state_root,
    )

    with pytest.raises(StateRootBoundaryError):
        ensure_inside_state_root(root, root)
    with pytest.raises(shim_state.StateRootBoundaryError):
        shim_state.ensure_layout(root)
    assert shim_descriptor.read_descriptor(root) is None
    shim_descriptor.remove_descriptor(root)
    assert runtime_descriptor.read_descriptor(root) is None
    runtime_descriptor.remove_descriptor_if_inside(root)
    assert not shim_state.ownership_marker_valid(root)
    with pytest.raises(StateRootLockError):
        StateRootLock(root).acquire()
    with pytest.raises(StateRootBoundaryError):
        ReceiptStore(root).open()
    provisioned = provision_runtime_env(tmp_path / "runtime-env", root)
    assert not provisioned.ok
    assert _main.main(["--state-root", str(root)]) == 1
    capsys.readouterr()

    assert sentinel.read_text(encoding="utf-8") == "sentinel"
    assert list(outside.iterdir()) == [descriptor_dir]


def test_state_root_reparse_predicate_fails_closed_without_link_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The no-follow root predicate is testable without symlink privileges."""
    from hermes_shim import _state as shim_state

    from hermes_pipeline.transport import _state as transport_state

    def always_link(_path: Path) -> bool:
        return True

    monkeypatch.setattr(transport_state, "_is_link_or_reparse_point", always_link)
    monkeypatch.setattr(shim_state, "_is_link_or_reparse_point", always_link)
    with pytest.raises(transport_state.StateRootBoundaryError):
        transport_state.ensure_inside_state_root(tmp_path, tmp_path)
    with pytest.raises(shim_state.StateRootBoundaryError):
        shim_state.ensure_layout(tmp_path)


def test_state_root_rejects_linked_hermes_home_before_external_access(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A normal state-root child still fails when its configured home links out."""
    configured_home = tmp_path / "configured-hermes-home"
    external_home = tmp_path / "external-home"
    external_home.mkdir()
    sentinel = external_home / "sentinel.txt"
    sentinel.write_text("sentinel", encoding="utf-8")
    if not hasattr(os, "symlink"):
        pytest.skip("symlink creation unavailable")
    try:
        configured_home.symlink_to(external_home, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")

    from hermes_shim import _descriptor as shim_descriptor
    from hermes_shim import _state as shim_state
    from hermes_shim._provision import provision_runtime_env

    from hermes_pipeline.transport import _main
    from hermes_pipeline.transport._lock import StateRootLock, StateRootLockError
    from hermes_pipeline.transport._receipts import ReceiptStore
    from hermes_pipeline.transport._state import (
        StateRootBoundaryError,
        ensure_inside_state_root,
    )

    root = shim_state.state_root(configured_home)
    with pytest.raises(shim_state.StateRootBoundaryError):
        shim_state.ensure_layout(root)
    assert shim_descriptor.read_descriptor(root) is None
    shim_descriptor.remove_descriptor(root)
    with pytest.raises(StateRootBoundaryError):
        ensure_inside_state_root(root, root)
    with pytest.raises(StateRootLockError):
        StateRootLock(root).acquire()
    with pytest.raises(StateRootBoundaryError):
        ReceiptStore(root).open()
    assert not provision_runtime_env(tmp_path / "runtime-env", root).ok
    assert _main.main(["--state-root", str(root)]) == 1
    capsys.readouterr()

    assert sentinel.read_text(encoding="utf-8") == "sentinel"
    assert not (external_home / "software-pipeline").exists()


def test_state_root_rejects_parent_traversal_after_linked_hermes_home(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Do not normalize ``link/..`` before checking every lexical ancestor."""
    safe_home = tmp_path / "safe-hermes-home"
    external_parent = tmp_path / "external-parent"
    external_home = external_parent / "external-home"
    safe_home.mkdir()
    external_home.mkdir(parents=True)
    sentinel = external_parent / "sentinel.txt"
    sentinel.write_text("sentinel", encoding="utf-8")
    linked_parent = safe_home / "linked-parent"
    if not hasattr(os, "symlink"):
        pytest.skip("symlink creation unavailable")
    try:
        linked_parent.symlink_to(external_home, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")

    from hermes_shim import _descriptor as shim_descriptor
    from hermes_shim import _state as shim_state
    from hermes_shim._provision import provision_runtime_env

    from hermes_pipeline.transport import _main
    from hermes_pipeline.transport._lock import StateRootLock, StateRootLockError
    from hermes_pipeline.transport._receipts import ReceiptStore
    from hermes_pipeline.transport._state import (
        StateRootBoundaryError,
        ensure_inside_state_root,
    )

    # Preserve the lexical ``..``: resolving before the no-follow ancestor walk
    # would turn this into ``safe_home/software-pipeline`` and hide the link.
    root = shim_state.state_root(linked_parent / "..")
    assert ".." in root.parts
    with pytest.raises(shim_state.StateRootBoundaryError):
        shim_state.ensure_layout(root)
    assert shim_descriptor.read_descriptor(root) is None
    shim_descriptor.remove_descriptor(root)
    with pytest.raises(StateRootBoundaryError):
        ensure_inside_state_root(root, root)
    with pytest.raises(StateRootLockError):
        StateRootLock(root).acquire()
    with pytest.raises(StateRootBoundaryError):
        ReceiptStore(root).open()
    assert not provision_runtime_env(tmp_path / "runtime-env", root).ok
    assert _main.main(["--state-root", str(root)]) == 1
    capsys.readouterr()

    assert sentinel.read_text(encoding="utf-8") == "sentinel"
    assert not (external_parent / "software-pipeline").exists()


def test_token_and_start_identity_are_random_and_sized() -> None:
    tokens = {descriptor.new_token() for _ in range(8)}
    assert len(tokens) == 8
    for token in tokens:
        assert len(token) == 64
    identities = {descriptor.new_start_identity() for _ in range(8)}
    assert len(identities) == 8
    for identity in identities:
        assert len(identity) == 32
