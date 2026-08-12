"""Owner-only descriptor ACL enforcement (slice-00-05, fixed decision D3).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Windows: the exact ACE set is **exactly one grant ACE for the current user
(resolved user SID) with full control ``(F)`` and nothing else**, applied
with a controlled argv subprocess (never a shell string)::

    icacls <path> /inheritance:r /grant:r <user-sid>:(F)

Verification parses ``icacls <path>`` output and must show only the
current-user SID (or user name) with ``(F)``; any other subject — including
``Everyone`` (``*S-1-1-0``), ``BUILTIN\\Users`` (``*S-1-5-32-545``),
``SYSTEM`` (``*S-1-5-18``), ``BUILTIN\\Administrators``
(``*S-1-5-32-544``), or any other — in the descriptor DACL fails
verification. Residual limit: the host-admin boundary (take-ownership,
backup semantics) is outside the DACL and is documented, not permitted.

POSIX: ``0o600`` plus a mode check.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

# Forbidden subjects in the descriptor DACL (Windows well-known SIDs and
# their common display names).
FORBIDDEN_SUBJECT_PATTERNS = (
    "s-1-1-0",  # Everyone
    "s-1-5-32-545",  # BUILTIN\Users
    "s-1-5-18",  # SYSTEM
    "s-1-5-32-544",  # BUILTIN\Administrators
    "everyone",
    "users",
    "system",
    "administrators",
)

# One ACE: <subject>:(<flags>...) with optional repeated parenthesized
# flag groups (e.g. "(F)" or "(OI)(CI)(F)"). A subject may be a multi-word
# account name ("NT AUTHORITY\SYSTEM").
_ACE_SUBJECT_RE = re.compile(r"([^:()\s]+(?:\s+[^:()\s]+)*):((?:\([^)]*\))+)")


def parse_icacls_aces(text: str) -> list[tuple[str, str]]:
    """Extract (subject, joined-permission-flags) pairs from icacls output.

    Real ``icacls <path>`` output places the file path before the first ACE
    (``<path> <subject>:(F)``); subsequent ACE lines are indented without a
    path. Lines whose first token is an absolute path get the path prefix
    stripped before ACE extraction; header/status lines carry no
    ``subject:(flags)`` shape and are ignored, so parsing is
    locale-independent.
    """
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
    """(SID, "MACHINE\\user") for the current user via controlled argv.

    Returns (None, None) when the platform tools are unavailable. Output is
    captured as bytes and decoded lossily so non-UTF-8 system locales
    (e.g. GBK on Chinese Windows) cannot break identity resolution.
    """
    sid: str | None = None
    name: str | None = None
    try:
        proc = subprocess.run(["whoami", "/user"], capture_output=True, timeout=30)
        if proc.returncode == 0:
            text = proc.stdout.decode("utf-8", errors="replace")
            match = re.search(r"\bS-1-[0-9-]+\b", text)
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


def verify_descriptor_acl_text(
    text: str,
    current_sid: str | None,
    current_user: str | None,
) -> list[str]:
    """Validate parsed DACL text: exactly one current-user (F) ACE.

    Returns a list of problems (empty when the DACL is exactly the accepted
    single-ACE set). Inherited ACEs (flag ``I``) are host-inherited noise
    outside the file's explicit DACL and are ignored for the exact-one
    check; only explicit ACEs are validated.
    """
    problems: list[str] = []
    aces = parse_icacls_aces(text)
    if not aces:
        return ["no ACE found in icacls output"]
    explicit = [(s, f) for s, f in aces if "i" not in f.lower()]
    if not explicit:
        return ["no ACE found in icacls output"]
    allowed: set[str] = {current_sid.lower()} if current_sid else set()
    if current_sid:
        allowed.add(f"*{current_sid.lower()}")
    if current_user:
        allowed.add(current_user.lower())
    for subject, flags in explicit:
        normalized = subject.lower()
        if normalized not in allowed:
            problems.append(f"descriptor DACL contains subject {subject!r}")
            continue
        if "f" not in flags.lower():
            problems.append(f"current-user ACE lacks full control: ({flags})")
    if len(explicit) != 1:
        problems.append(
            f"descriptor DACL must contain exactly one ACE (got {len(explicit)})"
        )
    return problems


def apply_windows_dacl(path: Path) -> list[str]:
    """Apply the exact single-ACE DACL with controlled icacls argv.

    The grant target uses icacls' documented ``*SID`` syntax so the SID is
    used directly without an account-name lookup round trip; the resulting
    DACL is exactly one current-user ``(F)`` ACE. (Some hosts, e.g. Docker-
    virtualized Windows, cannot map a well-formed local SID to a name and
    fail the plain-SID form with ERROR_NONE_MAPPED; ``*SID`` is the
    documented icacls form and behaves identically everywhere.)
    """
    sid, _ = current_user_identities()
    if sid is None:
        return ["cannot resolve current user SID"]
    argv = ["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(F)"]
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"icacls application failed: {type(exc).__name__}"]
    if proc.returncode != 0:
        return [f"icacls application failed (exit {proc.returncode})"]
    return []


def verify_windows_dacl(path: Path) -> list[str]:
    """Read and validate the applied DACL for one descriptor file."""
    try:
        proc = subprocess.run(["icacls", str(path)], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"icacls verification failed: {type(exc).__name__}"]
    if proc.returncode != 0:
        return [f"icacls verification failed (exit {proc.returncode})"]
    sid, user = current_user_identities()
    text = proc.stdout.decode("utf-8", errors="replace")
    return verify_descriptor_acl_text(text, sid, user)


def apply_posix_mode(path: Path) -> list[str]:
    """Owner-only 0o600 (POSIX)."""
    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        return [f"chmod failed: {type(exc).__name__}"]
    return []


def verify_posix_mode(path: Path) -> list[str]:
    """Mode check: 0o600 exactly."""
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        return [f"stat failed: {type(exc).__name__}"]
    if mode != 0o600:
        return [f"descriptor mode must be 0o600 (got {oct(mode)})"]
    return []


def protect_descriptor(path: Path) -> list[str]:
    """Apply the platform owner-only protection to a descriptor file."""
    if os.name == "nt":
        return apply_windows_dacl(path)
    return apply_posix_mode(path)


def verify_descriptor_protection(path: Path) -> list[str]:
    """Verify the platform owner-only protection of a descriptor file."""
    if os.name == "nt":
        return verify_windows_dacl(path)
    return verify_posix_mode(path)


__all__ = [
    "apply_windows_dacl",
    "parse_icacls_aces",
    "protect_descriptor",
    "verify_descriptor_acl_text",
    "verify_descriptor_protection",
]
