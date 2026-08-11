"""State-root singleton lock (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

One runtime may claim one state root. Startup acquires an operating-system
file lock; a second start on the same state root fails closed
(``DEPENDENCY_UNAVAILABLE``) without touching the live descriptor.
"""

# fcntl's flock/LOCK_* surface is absent from the Windows typeshed stub
# (POSIX-only), so the module is exposed through Any; both call sites are
# platform-gated by the None sentinel assigned on ImportError.

from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO

from ._constants import LOCK_FILENAME
from ._state import StateRootBoundaryError, ensure_inside_state_root

try:  # POSIX
    import fcntl as _fcntl
except ImportError:  # Windows
    _fcntl = None  # type: ignore[assignment]

fcntl: Any = _fcntl

try:  # Windows
    import msvcrt as _msvcrt
except ImportError:
    _msvcrt = None  # type: ignore[assignment]

# msvcrt's locking/constant surface is absent from the Linux typeshed stub.
# Keep this Windows-only binding behind the same Any boundary as fcntl above;
# every use remains guarded by the platform sentinel.
msvcrt: Any = _msvcrt


class StateRootLockError(Exception):
    """The state-root singleton lock is held by another runtime."""


class StateRootLock:
    """Exclusive advisory lock on the state root."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._path = root / LOCK_FILENAME
        self._handle: BinaryIO | None = None

    def acquire(self) -> None:
        """Acquire the lock; raise StateRootLockError when already held.

        The file handle stays open after a successful acquisition: the OS
        file lock is bound to the open handle (``msvcrt.locking`` and
        ``fcntl.flock`` both release the lock when the handle closes), so
        the handle must live until ``release()`` unlocks and closes it.
        The boundary guard runs before any mkdir: a lock filename
        resolving outside the root (``..`` or a symlinked parent) is
        refused with zero outside writes.
        """
        try:
            ensure_inside_state_root(self._root, self._path)
        except StateRootBoundaryError:
            raise StateRootLockError(
                "state-root singleton lock escapes state root"
            ) from None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self._path, "a+b")  # noqa: SIM115 - handle outlives acquire()
        try:
            if fcntl is not None:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise StateRootLockError(
                        "state-root singleton lock already held"
                    ) from None
            else:
                assert msvcrt is not None  # platform invariant
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    raise StateRootLockError(
                        "state-root singleton lock already held"
                    ) from None
        except BaseException:
            handle.close()
            raise
        self._handle = handle

    def release(self) -> None:
        """Release the lock (idempotent)."""
        handle = self._handle
        if handle is None:
            return
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            else:
                assert msvcrt is not None  # platform invariant
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            import contextlib

            with contextlib.suppress(OSError):
                handle.close()
            self._handle = None

    def __enter__(self) -> StateRootLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


__all__ = ["StateRootLock", "StateRootLockError"]
