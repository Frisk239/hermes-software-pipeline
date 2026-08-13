"""Host isolation proof required before any real CLI.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from hermes_pipeline.runtime_broker._codes import UNSUPPORTED_RUNTIME

CHILD_PROBE_SOURCE = r"""
import json, os, socket, sys
from pathlib import Path

def _denied(exc: BaseException) -> bool:
    err = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
    return err in {5, 13} or "denied" in str(exc).lower()

def main() -> int:
    outside, snapshot, state = map(Path, sys.argv[1:4])
    report = {
        "appcontainer": False,
        "outside_read": "error",
        "outside_write": "error",
        "snapshot_write": "error",
        "state_write": "error",
        "egress": "error",
        "uid": os.getuid() if hasattr(os, "getuid") else None,
    }
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            TokenIsAppContainer = 29
            token = wintypes.HANDLE()
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            advapi = ctypes.WinDLL("advapi32", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            advapi.OpenProcessToken.argtypes = [
                wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)
            ]
            advapi.GetTokenInformation.argtypes = [
                wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
            ]
            opened = advapi.OpenProcessToken(
                kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)
            )
            if opened:
                flag = wintypes.DWORD()
                needed = wintypes.DWORD()
                if advapi.GetTokenInformation(
                    token, TokenIsAppContainer, ctypes.byref(flag),
                    ctypes.sizeof(flag), ctypes.byref(needed),
                ):
                    report["appcontainer"] = bool(flag.value)
                kernel32.CloseHandle(token)
        except Exception:
            report["appcontainer"] = False
    try:
        (outside / "canary.txt").read_text(encoding="utf-8")
        report["outside_read"] = "ok"
    except Exception as exc:
        report["outside_read"] = "access_denied" if _denied(exc) else "error"
    try:
        (outside / "child-write.txt").write_text("x", encoding="utf-8")
        report["outside_write"] = "ok"
    except Exception as exc:
        report["outside_write"] = "access_denied" if _denied(exc) else "error"
    try:
        (snapshot / "child-write.txt").write_text("x", encoding="utf-8")
        report["snapshot_write"] = "ok"
    except Exception as exc:
        report["snapshot_write"] = "access_denied" if _denied(exc) else "error"
    try:
        target = state / "tools" / "isolation-child-write.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ok", encoding="utf-8")
        report["state_write"] = "ok"
    except Exception as exc:
        report["state_write"] = "error"
    try:
        probe = socket.create_connection(("192.0.2.1", 1), timeout=0.2)
        probe.close()
        report["egress"] = "connected"
    except OSError:
        report["egress"] = "failed"
    out = Path(sys.argv[3]) / "tools" / "isolation-child-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report), encoding="utf-8")
    sys.stdout.write(json.dumps(report))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
"""


class IsolationError(RuntimeError):
    """Platform isolation proof is absent."""

    def __init__(self) -> None:
        super().__init__(UNSUPPORTED_RUNTIME)
        self.code = UNSUPPORTED_RUNTIME


def evaluate_child_probe_report(report: Mapping[str, object], *, windows: bool) -> bool:
    """True only when the locked child assertions all hold."""
    if report.get("outside_read") != "access_denied":
        return False
    if report.get("outside_write") != "access_denied":
        return False
    if report.get("snapshot_write") != "access_denied":
        return False
    if report.get("state_write") != "ok":
        return False
    if report.get("egress") != "failed":
        return False
    if windows and report.get("appcontainer") is not True:
        return False
    if not windows:
        uid = report.get("uid")
        if not isinstance(uid, int) or uid == 0:
            return False
        getuid = getattr(os, "getuid", None)
        if callable(getuid) and uid == getuid():
            return False
    return True


def _windows_job_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            return False
        kernel32.CloseHandle(handle)
    except OSError:
        return False
    return True


def _state_root_writable(state_root: Path) -> bool:
    try:
        state_root.mkdir(parents=True, exist_ok=True)
        probe = state_root / "tools" / ".isolation-write-probe"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True


def _write_child_probe(state_root: Path) -> Path:
    script = state_root / "tools" / "isolation-child-probe.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(CHILD_PROBE_SOURCE, encoding="utf-8")
    return script


def _grant_sid(path: Path, sid: str, rights: str) -> bool:
    granted = subprocess.run(
        ["icacls", str(path), "/grant", f"*{sid}:({rights})"],
        capture_output=True,
        timeout=30,
    )
    return granted.returncode == 0


def _run_appcontainer_process(
    argv: list[str], appcontainer_sid: object, *, cwd: Path
) -> str | None:
    """CreateProcess inside the AppContainer; None if the spawn fails."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    extended = 0x00080000
    unicode_env = 0x00000400
    attribute_security = 0x00020009

    class _STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.c_void_p),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class _STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [
            ("StartupInfo", _STARTUPINFOW),
            ("lpAttributeList", ctypes.c_void_p),
        ]

    class _SECURITY_CAPABILITIES(ctypes.Structure):
        _fields_ = [
            ("AppContainerSid", ctypes.c_void_p),
            ("Capabilities", ctypes.c_void_p),
            ("CapabilityCount", wintypes.DWORD),
            ("Reserved", wintypes.DWORD),
        ]

    class _PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    caps = _SECURITY_CAPABILITIES()
    caps.AppContainerSid = int(getattr(appcontainer_sid, "value", 0) or 0)
    size = ctypes.c_size_t()
    kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    buf = ctypes.create_string_buffer(size.value)
    if not kernel32.InitializeProcThreadAttributeList(buf, 1, 0, ctypes.byref(size)):
        return None
    if not kernel32.UpdateProcThreadAttribute(
        buf, 0, attribute_security, ctypes.byref(caps), ctypes.sizeof(caps), None, None
    ):
        kernel32.DeleteProcThreadAttributeList(buf)
        return None
    info = _STARTUPINFOEXW()
    info.StartupInfo.cb = ctypes.sizeof(_STARTUPINFOEXW)
    info.lpAttributeList = ctypes.cast(buf, ctypes.c_void_p)
    proc = _PROCESS_INFORMATION()
    cmd = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
    created = kernel32.CreateProcessW(
        None,
        cmd,
        None,
        None,
        False,
        extended | unicode_env,
        None,
        str(cwd),
        ctypes.byref(info),
        ctypes.byref(proc),
    )
    kernel32.DeleteProcThreadAttributeList(buf)
    if not created:
        return None
    kernel32.WaitForSingleObject(proc.hProcess, 15000)
    kernel32.CloseHandle(proc.hThread)
    kernel32.CloseHandle(proc.hProcess)
    report_path = cwd / "tools" / "isolation-child-report.json"
    if not report_path.is_file():
        return None
    return report_path.read_text(encoding="utf-8")


def _demonstrate_windows_child(state_root: Path, snapshot: Path) -> bool:
    """Spawn an AppContainer child and evaluate the locked probe."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    userenv = ctypes.WinDLL("userenv", use_last_error=True)
    if not hasattr(userenv, "CreateAppContainerProfile"):
        return False
    name = f"hermes00iso{os.getpid()}"
    sid = ctypes.c_void_p()
    created = userenv.CreateAppContainerProfile(
        name, name, name, None, 0, ctypes.byref(sid)
    )
    if created not in {0, 0x80071392}:
        derived = userenv.DeriveAppContainerSidFromAppContainerName(
            name, ctypes.byref(sid)
        )
        if derived != 0 or not sid.value:
            return False
    if not sid.value:
        return False
    convert = ctypes.windll.advapi32.ConvertSidToStringSidW
    convert.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    string_sid = wintypes.LPWSTR()
    if not convert(sid, ctypes.byref(string_sid)):
        return False
    sid_text = string_sid.value or ""
    outside = Path(tempfile.mkdtemp(prefix="hermes-iso-canary-"))
    (outside / "canary.txt").write_text("secret", encoding="utf-8")
    script = _write_child_probe(state_root)
    try:
        if not _grant_sid(snapshot, sid_text, "R"):
            return False
        if not _grant_sid(state_root, sid_text, "F"):
            return False
        argv = [
            sys.executable,
            str(script),
            str(outside),
            str(snapshot),
            str(state_root),
        ]
        stdout = _run_appcontainer_process(argv, sid, cwd=state_root)
        if stdout is None:
            return False
        try:
            loaded = json.loads(stdout)
        except json.JSONDecodeError:
            return False
        if not isinstance(loaded, dict):
            return False
        return evaluate_child_probe_report(cast(dict[str, Any], loaded), windows=True)
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        for child in outside.rglob("*"):
            if child.is_file():
                child.unlink(missing_ok=True)
        outside.rmdir()
        userenv.DeleteAppContainerProfile(name)


def _demonstrate_linux_child(state_root: Path, snapshot: Path) -> bool:
    """Spawn a user/mount/pid/netns child and evaluate the locked probe."""
    if sys.platform == "win32":
        return False
    script = _write_child_probe(state_root)
    outside = Path(tempfile.mkdtemp(prefix="hermes-iso-canary-"))
    (outside / "canary.txt").write_text("secret", encoding="utf-8")
    argv = [
        "unshare",
        "--user",
        "--map-user=1",
        "--map-group=1",
        "--mount",
        "--pid",
        "--net",
        "--fork",
        "--kill-child",
        sys.executable,
        str(script),
        str(outside),
        str(snapshot),
        str(state_root),
    ]
    try:
        completed = subprocess.run(argv, capture_output=True, timeout=15, check=False)
        if completed.returncode != 0:
            return False
        loaded = json.loads(completed.stdout.decode("utf-8"))
        if not isinstance(loaded, dict):
            return False
        return evaluate_child_probe_report(cast(dict[str, Any], loaded), windows=False)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return False
    finally:
        for child in outside.rglob("*"):
            if child.is_file():
                child.unlink(missing_ok=True)
        outside.rmdir()


def prove_host_isolation(*, state_root: Path, snapshot: Path) -> None:
    """Return only when every locked local assertion is demonstrated."""
    missing: list[str] = []
    if not snapshot.is_dir() or (snapshot / ".git").exists():
        missing.append("snapshot")
    if not _state_root_writable(state_root):
        missing.append("state-root-write")
    if sys.platform == "win32":
        if not _windows_job_available():
            missing.append("job-object")
        if not _demonstrate_windows_child(state_root, snapshot):
            missing.append("appcontainer-child")
    elif not _demonstrate_linux_child(state_root, snapshot):
        missing.append("ns-child")
    if missing:
        raise IsolationError
