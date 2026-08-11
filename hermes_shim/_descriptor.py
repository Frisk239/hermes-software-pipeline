"""Runtime descriptor access for the Hermes Shim (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

The shim reads, validates, and (on stale proof) removes the runtime
descriptor written by the fake managed runtime. Descriptor shape is pinned
by the spike versioned constants and the golden JSON fixtures under
``tests/fixtures/transport/``; the shim never writes a descriptor (only the
runtime process does, atomically, with owner-only ACL/mode).

The stale-descriptor algorithm (contract-pinned): a descriptor is stale and
removable only when ``os.kill(pid, 0)`` reports the process gone **or** the
recorded process-start marker mismatches the process currently holding the
PID (PID reuse detection). A live matching process means the descriptor is
never removed; ``os.kill(pid, 0)`` alone is never proof of identity.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ._constants import (
    DESCRIPTOR_FILENAME,
    DESCRIPTOR_VERSION,
    PROTOCOL_VERSION,
)
from ._state import ensure_inside_state_root

# Required descriptor fields (spike versioned shape).
REQUIRED_FIELDS = (
    "descriptor_version",
    "protocol_version",
    "pid",
    "start_identity",
    "creation_time",
    "process_start_marker",
    "port",
    "token",
    "token_generation",
    "release",
    "state_root_identity",
)


def descriptor_path(root: Path) -> Path:
    """The runtime descriptor file inside a state root."""
    return root / "descriptor" / DESCRIPTOR_FILENAME


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def validate_descriptor(document: dict[str, Any]) -> list[str]:
    """Structural validation of one descriptor document.

    Unknown fields are rejected at the trust boundary, matching the
    runtime-side validator and the committed reject vectors. Returns a list
    of field problems (empty when the document is valid).
    """
    problems: list[str] = []
    unknown = sorted(set(document) - set(REQUIRED_FIELDS))
    if unknown:
        problems.append(f"unknown field(s): {', '.join(unknown)}")
    for field in REQUIRED_FIELDS:
        if field not in document:
            problems.append(f"missing field {field!r}")
    if (
        "descriptor_version" in document
        and document["descriptor_version"] != DESCRIPTOR_VERSION
    ):
        problems.append("unsupported descriptor_version")
    if (
        "protocol_version" in document
        and document["protocol_version"] != PROTOCOL_VERSION
    ):
        problems.append("unsupported protocol_version")
    for field in ("pid", "port", "token_generation"):
        if field in document and _as_int(document[field]) is None:
            problems.append(f"{field} must be an integer")
    for field in (
        "start_identity",
        "token",
        "release",
        "creation_time",
        "state_root_identity",
    ):
        if field in document and not isinstance(document[field], str):
            problems.append(f"{field} must be a string")
    marker = document.get("process_start_marker")
    if not isinstance(marker, dict):
        problems.append("process_start_marker must be an object")
    elif not isinstance(marker.get("value"), str) or not isinstance(
        marker.get("source"), str
    ):
        problems.append("process_start_marker needs string value and source")
    return problems


def read_descriptor(root: Path) -> dict[str, Any] | None:
    """Read and validate the descriptor; None when absent or malformed.

    An escaping descriptor path (symlinked outside the state root) is
    treated as absent: the external file is never read.
    """
    path = descriptor_path(root)
    try:
        ensure_inside_state_root(root, path)
    except Exception:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        document = json.loads(text)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(document, dict):
        return None
    if validate_descriptor(document):
        return None
    return document


def _read_process_start_marker(pid: int) -> str | None:
    """Re-read the platform start marker for a PID (None when unknown).

    Linux: ``/proc/<pid>/stat`` field 22 (starttime in clock ticks).
    Windows: ctypes ``kernel32.OpenProcess``/``GetProcessTimes`` creation
    FILETIME. This mirrors the runtime-side identity module; both sides
    compare the same source so PID reuse is detected.
    """
    if os.name == "nt":
        return _win32_creation_time(pid)
    return _linux_starttime_ticks(pid)


def _linux_starttime_ticks(pid: int) -> str | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    # The comm field may contain spaces/parentheses; starttime is field 22,
    # so split after the LAST ')' (a legal process name may contain ')').
    try:
        tail = stat.rsplit(")", 1)[1].split()
        return tail[22 - 3]  # field 22 is index 19 of the tail list
    except (IndexError, ValueError):
        return None


def _win32_creation_time(pid: int) -> str | None:
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        creation = ctypes.c_ulonglong()
        exit_time = ctypes.c_ulonglong()
        kernel_time = ctypes.c_ulonglong()
        user_time = ctypes.c_ulonglong()
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        )
        if not ok:
            return None
        return str(creation.value)
    finally:
        kernel32.CloseHandle(handle)


def _win32_process_gone(pid: int) -> bool | None:
    """Windows presence probe: True when provably gone, False when running,
    None when unverifiable.

    ``OpenProcess`` succeeds while the process object exists, including
    the termination window and while other processes hold handles, so a
    successful open is never proof of liveness. ``GetExitCodeProcess`` is
    the precise verdict: a value other than ``STILL_ACTIVE`` (259) means
    the process has terminated. ERROR_INVALID_PARAMETER (87) on open means
    the PID does not exist at all.
    """
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return kernel32.GetLastError() == 87
    try:
        exit_code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        return bool(ok and exit_code.value != STILL_ACTIVE)
    finally:
        kernel32.CloseHandle(handle)


def process_matches_identity(pid: int, expected_marker: dict[str, str] | None) -> bool:
    """Stale check: does a live process with this PID and start marker exist?

    The platform start marker (query-limited permissions) is the primary
    identity evidence; the Windows presence probe (exit code) is the
    liveness evidence, because a terminated process object can still
    answer a marker read. A descriptor may be removed only when the
    process is provably gone or the marker provably mismatches; any
    unverifiable state fails closed and keeps the descriptor. Windows
    creation FILETIMEs are compared with a 200 ms tolerance; Linux
    ``/proc/<pid>/stat`` field 22 is exact. A PID-reuse window smaller
    than the tolerance is a documented residual limit.
    """
    current = _read_process_start_marker(pid)
    if current is not None and isinstance(expected_marker, dict):
        expected = expected_marker.get("value")
        if not isinstance(expected, str):
            return True
        if expected_marker.get("source") == "win_getprocess_times":
            try:
                matches = (
                    current == expected
                    or abs(int(current) - int(expected)) <= 2_000_000
                )
            except ValueError:
                matches = False
        else:
            matches = current == expected
        if not matches:
            return False
        # The marker matches; on Windows the process object may still be a
        # terminated one (handles held elsewhere), so prove liveness there.
        if os.name == "nt":
            return not _win32_process_gone(pid)
        return True
    # The marker cannot be read: the process is gone, inside a PID-reuse
    # window, or not queryable. A descriptor may be removed only when the
    # process is provably absent; any unverifiable state fails closed and
    # keeps the descriptor.
    if os.name == "nt":
        return _win32_process_gone(pid) is not True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False  # provably absent
    except OSError:
        # EPERM (exists) or any other unverifiable error: fail closed.
        return True
    # os.kill succeeded: the process exists — fail closed.
    return True


def is_stale(root: Path) -> bool:
    """True when the descriptor's process is gone or its identity mismatches."""
    document = read_descriptor(root)
    if document is None:
        return True  # absent or malformed: nothing live is claimed
    pid = int(document["pid"])
    marker = document["process_start_marker"]
    return not process_matches_identity(pid, marker)


def remove_descriptor(root: Path) -> None:
    """Remove the descriptor file (only after stale proof by the caller).

    Removal is itself a write: an escaping descriptor path (attacker-
    controlled symlink/junction/reparse point) is never unlinked.
    """
    path = descriptor_path(root)
    try:
        ensure_inside_state_root(root, path)
    except Exception:
        return
    import contextlib

    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def render_redacted_summary(document: dict[str, Any]) -> dict[str, object]:
    """Bounded, redacted descriptor summary for operator output.

    Never includes the token, the start identity, or any path.
    """
    return {
        "protocol_version": document["protocol_version"],
        "pid": int(document["pid"]),
        "port": int(document["port"]),
        "token_generation": int(document["token_generation"]),
        "release": document["release"],
        "state_root_identity": document["state_root_identity"],
        "creation_time": document["creation_time"],
    }


__all__ = [
    "descriptor_path",
    "is_stale",
    "process_matches_identity",
    "read_descriptor",
    "remove_descriptor",
    "render_redacted_summary",
    "validate_descriptor",
]
