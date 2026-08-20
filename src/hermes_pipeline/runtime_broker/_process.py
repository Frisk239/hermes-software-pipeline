"""External process-tree fencing (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import IO

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _JobObjectExtendedLimitInformation = 9
    _JobObjectBasicProcessIdList = 3
    _CREATE_SUSPENDED = 0x00000004
    _TH32CS_SNAPPROCESS = 0x00000002
    _PROCESS_ALL_ACCESS = 0x1F0FFF
    _STILL_ACTIVE = 259

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _JOBOBJECT_BASIC_PROCESS_ID_LIST(ctypes.Structure):
        _fields_ = [
            ("NumberOfAssignedProcesses", wintypes.DWORD),
            ("NumberOfProcessIdsInList", wintypes.DWORD),
            ("ProcessIdList", ctypes.c_size_t * 64),
        ]

    class _PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    _KERNEL32.CreateJobObjectW.restype = wintypes.HANDLE
    _KERNEL32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _KERNEL32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _KERNEL32.OpenProcess.restype = wintypes.HANDLE
    _KERNEL32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _KERNEL32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _KERNEL32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    _NTDLL = ctypes.WinDLL("ntdll")
    _NTDLL.NtResumeProcess.argtypes = [wintypes.HANDLE]
    _KERNEL32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _KERNEL32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _KERNEL32.Process32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_PROCESSENTRY32W),
    ]
    _KERNEL32.Process32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_PROCESSENTRY32W),
    ]
    _KERNEL32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]

    def _windows_job() -> int:
        handle = _KERNEL32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError("CreateJobObjectW failed")
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = _KERNEL32.SetInformationJobObject(
            handle,
            _JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            _KERNEL32.CloseHandle(handle)
            raise OSError("SetInformationJobObject failed")
        return int(handle)

    def _job_pids(job: int) -> list[int]:
        info = _JOBOBJECT_BASIC_PROCESS_ID_LIST()
        returned = wintypes.DWORD(0)
        ok = _KERNEL32.QueryInformationJobObject(
            job,
            _JobObjectBasicProcessIdList,
            ctypes.byref(info),
            ctypes.sizeof(info),
            ctypes.byref(returned),
        )
        if not ok:
            return []
        count = min(int(info.NumberOfProcessIdsInList), 64)
        return [int(info.ProcessIdList[index]) for index in range(count)]

    def _run_fenced_windows(
        argv: Sequence[str],
        *,
        cwd: str | None,
        env: Mapping[str, str] | None,
        timeout_s: float,
        output_bytes: int,
        cancel_event: threading.Event | None,
    ) -> BoundedResult:
        job = _windows_job()
        child = subprocess.Popen(
            list(argv),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_CREATE_SUSPENDED,
        )
        process_handle = _KERNEL32.OpenProcess(_PROCESS_ALL_ACCESS, False, child.pid)
        try:
            if not process_handle or not _KERNEL32.AssignProcessToJobObject(
                job, process_handle
            ):
                _KERNEL32.TerminateJobObject(job, 1)
                raise OSError("AssignProcessToJobObject failed")
            _NTDLL.NtResumeProcess(process_handle)
            timed_out = False
            cancelled = False
            if cancel_event is not None:
                finished = threading.Event()
                captured: list[tuple[bytes, bytes]] = []

                def _wait() -> None:
                    with contextlib.suppress(Exception):
                        captured.append(child.communicate())
                    finished.set()

                worker = threading.Thread(target=_wait, daemon=True)
                worker.start()
                stop_at = time.monotonic() + timeout_s
                while not finished.is_set():
                    if cancel_event.is_set():
                        cancelled = True
                        _KERNEL32.TerminateJobObject(job, 1)
                        break
                    if time.monotonic() >= stop_at:
                        timed_out = True
                        _KERNEL32.TerminateJobObject(job, 1)
                        break
                    finished.wait(0.05)
                worker.join(timeout=5)
                if captured:
                    stdout, stderr = captured[0]
                else:
                    stdout, stderr = b"", b""
            else:
                try:
                    stdout, stderr = child.communicate(timeout=timeout_s)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    _KERNEL32.TerminateJobObject(job, 1)
                    stdout, stderr = child.communicate(timeout=5)
            survivors = tuple(pid for pid in _job_pids(job) if _pid_alive(pid))
            deadline = time.monotonic() + 0.5
            while survivors and time.monotonic() < deadline:
                time.sleep(0.05)
                survivors = tuple(pid for pid in _job_pids(job) if _pid_alive(pid))
            return BoundedResult(
                returncode=1 if child.returncode is None else int(child.returncode),
                stdout=stdout[:output_bytes],
                stderr=stderr[:output_bytes],
                timed_out=timed_out,
                cancelled=cancelled,
                survivors=survivors,
            )
        finally:
            if process_handle:
                _KERNEL32.CloseHandle(process_handle)
            _KERNEL32.CloseHandle(job)


@dataclass
class BoundedResult:
    """Captured child output after external fencing."""

    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    cancelled: bool
    survivors: tuple[int, ...]


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        handle = _KERNEL32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = wintypes.DWORD()
        _KERNEL32.GetExitCodeProcess(handle, ctypes.byref(code))
        _KERNEL32.CloseHandle(handle)
        return int(code.value) == _STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def descendant_pids(root_pid: int) -> list[int]:
    """Scan the full descendant tree, not only the root pid."""
    if sys.platform == "win32":
        snapshot = _KERNEL32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if snapshot == wintypes.HANDLE(-1).value or snapshot == 0xFFFFFFFF:
            return [root_pid] if _pid_alive(root_pid) else []
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        children: dict[int, list[int]] = {}
        ok = _KERNEL32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            children.setdefault(int(entry.th32ParentProcessID), []).append(
                int(entry.th32ProcessID)
            )
            ok = _KERNEL32.Process32NextW(snapshot, ctypes.byref(entry))
        _KERNEL32.CloseHandle(snapshot)
        found: list[int] = []
        stack = list(children.get(root_pid, []))
        while stack:
            pid = stack.pop()
            if pid in found:
                continue
            found.append(pid)
            stack.extend(children.get(pid, []))
        if _pid_alive(root_pid):
            found.append(root_pid)
        return found
    found: list[int] = []
    proc = os.path.join("/proc")
    if not os.path.isdir(proc):
        return found
    parents: dict[int, int] = {}
    for name in os.listdir(proc):
        if not name.isdigit():
            continue
        try:
            with open(os.path.join(proc, name, "stat"), encoding="utf-8") as handle:
                body = handle.read()
        except OSError:
            continue
        parts = body.rsplit(")", 1)
        if len(parts) != 2:
            continue
        fields = parts[1].split()
        if len(fields) >= 2 and fields[1].isdigit():
            parents[int(name)] = int(fields[1])
    for pid, parent in parents.items():
        walk = parent
        while walk and walk in parents:
            if walk == root_pid:
                found.append(pid)
                break
            walk = parents.get(walk, 0)
        if parent == root_pid:
            found.append(pid)
    return list(dict.fromkeys(found))


def zero_survivors(root_pid: int) -> tuple[int, ...]:
    """Alive descendants after the fence; empty means clean."""
    return tuple(pid for pid in descendant_pids(root_pid) if _pid_alive(pid))


def run_fenced(
    argv: Sequence[str],
    *,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    timeout_s: float = 30.0,
    output_bytes: int = 65536,
    stdin: IO[bytes] | None = None,
    cancel_event: threading.Event | None = None,
) -> BoundedResult:
    """Start a child under a Job Object / process group and fence it."""
    if not argv or any(part == "" for part in argv):
        raise ValueError("argv must be a non-empty argument array")
    if sys.platform == "win32":
        return _run_fenced_windows(
            argv,
            cwd=cwd,
            env=env,
            timeout_s=timeout_s,
            output_bytes=output_bytes,
            cancel_event=cancel_event,
        )
    child = subprocess.Popen(
        list(argv),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        stdin=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    timed_out = False
    cancelled = False
    try:
        if cancel_event is None:
            stdout, stderr = child.communicate(timeout=timeout_s)
        else:
            finished = threading.Event()
            captured: list[tuple[bytes, bytes]] = []

            def _wait() -> None:
                with contextlib.suppress(Exception):
                    captured.append(child.communicate())
                finished.set()

            threading.Thread(target=_wait, daemon=True).start()
            stop_at = time.monotonic() + timeout_s
            while not finished.is_set():
                if cancel_event.is_set():
                    cancelled = True
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGKILL)
                    break
                if time.monotonic() >= stop_at:
                    timed_out = True
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGKILL)
                    break
                finished.wait(0.05)
            finished.wait(5)
            stdout, stderr = captured[0] if captured else (b"", b"")
    except subprocess.TimeoutExpired:
        timed_out = True
        with contextlib.suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGKILL)
        stdout, stderr = child.communicate(timeout=5)
    survivors = zero_survivors(child.pid)
    return BoundedResult(
        returncode=1 if child.returncode is None else int(child.returncode),
        stdout=stdout[:output_bytes],
        stderr=stderr[:output_bytes],
        timed_out=timed_out,
        cancelled=cancelled,
        survivors=survivors,
    )
