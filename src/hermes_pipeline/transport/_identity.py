"""Process identity helpers for the fake managed runtime (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE

Cross-platform process-start markers used by the stale-descriptor
algorithm. A descriptor is stale and removable only when
``os.kill(pid, 0)`` reports the process gone **or** the recorded start
marker mismatches the process currently holding the PID (PID-reuse
detection); ``os.kill(pid, 0)`` alone is never proof of identity.

Marker sources are pinned per platform:

- Linux: ``/proc/<pid>/stat`` field 22 (starttime in clock ticks);
- Windows: ``ctypes`` ``kernel32.OpenProcess``/``GetProcessTimes``
  creation FILETIME.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast


def _win32_bindings() -> tuple[Any, Any]:
    """Return ctypes and kernel32 behind a Windows-only type boundary.

    ``ctypes.windll`` is deliberately unavailable in the Linux typeshed stub.
    The callers are reached only under ``os.name == "nt"``; keeping the
    platform binding local preserves that runtime gate while letting Linux CI
    type-check the shared module.
    """
    import ctypes

    ctypes_api: Any = ctypes
    return ctypes_api, ctypes_api.windll.kernel32


def read_process_start_marker(pid: int) -> dict[str, str] | None:
    """Read the platform start marker for a PID (None when unreadable)."""
    if os.name == "nt":
        value = _win32_creation_time(pid)
        if value is None:
            return None
        return {"value": value, "source": "win_getprocess_times"}
    value = _linux_starttime_ticks(pid)
    if value is None:
        return None
    return {"value": value, "source": "proc_stat_field22"}


def _linux_stat_fields(pid: int) -> list[str] | None:
    """Read fields after Linux ``/proc/<pid>/stat``'s parenthesized comm."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    # The comm field may contain spaces and parentheses; starttime is field
    # 22, so split after the LAST ')' of the comm field (a legal process
    # name may itself contain ')').
    try:
        return stat.rsplit(")", 1)[1].split()
    except IndexError:
        return None


def _linux_starttime_ticks(pid: int) -> str | None:
    fields = _linux_stat_fields(pid)
    if fields is None:
        return None
    try:
        return fields[22 - 3]  # field 22 is index 19 of the tail list
    except IndexError:
        return None


def _linux_process_is_zombie(pid: int) -> bool | None:
    """Return whether a Linux process is a zombie, or None if unreadable."""
    fields = _linux_stat_fields(pid)
    if not fields:
        return None
    return fields[0] == "Z"  # field 3: process state


def _win32_creation_time(pid: int) -> str | None:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    ctypes_api, kernel32 = _win32_bindings()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        creation = ctypes_api.c_ulonglong()
        exit_time = ctypes_api.c_ulonglong()
        kernel_time = ctypes_api.c_ulonglong()
        user_time = ctypes_api.c_ulonglong()
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes_api.byref(creation),
            ctypes_api.byref(exit_time),
            ctypes_api.byref(kernel_time),
            ctypes_api.byref(user_time),
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
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    ctypes_api, kernel32 = _win32_bindings()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return kernel32.GetLastError() == 87
    try:
        exit_code = ctypes_api.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes_api.byref(exit_code))
        return bool(ok and exit_code.value != STILL_ACTIVE)
    finally:
        kernel32.CloseHandle(handle)


def process_matches_identity(pid: int, expected: Any) -> bool:
    """True only when a live process holds this PID with this start marker.

    The platform start marker (read with query-limited permissions) is the
    primary identity evidence; the Windows presence probe (exit code) is
    the liveness evidence, because a terminated process object can still
    answer a marker read. A descriptor may be removed only when the
    process is provably gone or the marker provably mismatches; any
    unverifiable state fails closed and keeps the descriptor.

    Windows: creation FILETIMEs are compared with a 200 ms tolerance
    (system clock granularity and cross-session query offset); a PID-reuse
    window smaller than the tolerance is a documented residual limit.
    Linux: ``/proc/<pid>/stat`` field 22 (clock ticks) is exact.
    """
    current = read_process_start_marker(pid)
    if current is not None and isinstance(expected, dict):
        expected_marker = cast(dict[str, Any], expected)
        if current.get("source") != expected_marker.get("source"):
            return False
        if current.get("source") == "win_getprocess_times":
            try:
                current_value = int(str(current.get("value")))
                expected_value = int(str(expected_marker.get("value")))
            except ValueError:
                return False
            if abs(current_value - expected_value) > 2_000_000:
                return False
        elif current.get("value") != expected_marker.get("value"):
            return False
        # The marker matches; Windows process objects can outlive a process,
        # and Linux zombies retain a readable /proc marker. Prove liveness
        # before preserving a descriptor in either case.
        if os.name == "nt":
            return not _win32_process_gone(pid)
        return _linux_process_is_zombie(pid) is not True
    # The marker cannot be read: the process is gone, inside a PID-reuse
    # window, or not queryable. A descriptor may be removed only when the
    # process is provably absent; any unverifiable state fails closed and
    # keeps the descriptor.
    if os.name == "nt":
        gone = _win32_process_gone(pid)
        return gone is not True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False  # provably absent
    except OSError:
        # EPERM (exists) or any other unverifiable error: fail closed.
        return True
    # os.kill succeeded: the process exists — fail closed.
    return True


__all__ = ["process_matches_identity", "read_process_start_marker"]
