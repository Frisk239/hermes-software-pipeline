"""Owner-only gate/replay ACL (slice-00-06).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07
"""

from __future__ import annotations

import contextlib
import os
import re
import stat
import subprocess
from pathlib import Path

_ACE_SUBJECT_RE = re.compile(r"([^:()\s]+(?:\s+[^:()\s]+)*):((?:\([^)]*\))+)")


def parse_icacls_aces(text: str) -> list[tuple[str, str]]:
    """Parse icacls ACE lines."""
    aces: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or "(" not in line or ":" not in line:
            continue
        if re.match(r"^[A-Za-z]:[\\/]", line) or line.startswith("\\"):
            line = re.sub(r"^.*?\s+(?=[^:()\s]+(?:\s+[^:()\s]+)*:\([^)]*\))", "", line)
        for match in _ACE_SUBJECT_RE.finditer(line):
            subject = match.group(1).strip()
            flags = "".join(re.findall(r"\(([^)]*)\)", match.group(2)))
            if subject and flags:
                aces.append((subject, flags))
    return aces


def current_user_identities() -> tuple[str | None, str | None]:
    """(SID, DOMAIN\\user) for the current account."""
    sid: str | None = None
    name: str | None = None
    try:
        proc = subprocess.run(["whoami", "/user"], capture_output=True, timeout=30)
        if proc.returncode == 0:
            match = re.search(
                r"\bS-1-[0-9-]+\b", proc.stdout.decode("utf-8", errors="replace")
            )
            if match:
                sid = match.group(0)
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        proc = subprocess.run(["whoami"], capture_output=True, timeout=30)
        if proc.returncode == 0:
            name = proc.stdout.decode("utf-8", errors="replace").strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return sid, name


def current_user_sid() -> str | None:
    """Resolve the current user SID via whoami /user."""
    sid, _name = current_user_identities()
    return sid


def protect_owner_only(path: Path) -> None:
    """Apply owner-only DACL / 0o600. Never a shell string."""
    if os.name == "nt":
        sid = current_user_sid()
        if sid is None:
            raise OSError("cannot resolve current user SID")
        applied = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(F)"],
            capture_output=True,
            timeout=60,
        )
        if applied.returncode != 0:
            raise OSError("icacls grant failed")
        for principal in (
            "NT AUTHORITY\\SYSTEM",
            "BUILTIN\\Administrators",
            "BUILTIN\\Users",
            "Everyone",
            "OWNER RIGHTS",
        ):
            with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                subprocess.run(
                    ["icacls", str(path), "/remove", principal],
                    capture_output=True,
                    timeout=30,
                )
        return
    os.chmod(path, 0o600)


def verify_owner_only(path: Path) -> None:
    """Reject a gate/replay file that is not owner-only."""
    if os.name == "nt":
        listed = subprocess.run(["icacls", str(path)], capture_output=True, timeout=60)
        if listed.returncode != 0:
            raise OSError("icacls verify failed")
        text = listed.stdout.decode("utf-8", errors="replace")
        aces = parse_icacls_aces(text)
        sid, user = current_user_identities()
        if sid is None or not aces:
            raise OSError("owner-only DACL missing")
        allowed = {sid.lower(), f"*{sid.lower()}"}
        if user:
            allowed.add(user.lower())
        explicit = [
            (subject, flags) for subject, flags in aces if "i" not in flags.lower()
        ]
        if len(explicit) != 1:
            raise OSError("gate DACL must be exactly one ACE")
        subject, flags = explicit[0]
        if subject.lower() not in allowed or "f" not in flags.lower():
            raise OSError("gate DACL is not current-user (F)")
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != 0o600:
        raise OSError(f"mode must be 0o600 (got {oct(mode)})")
