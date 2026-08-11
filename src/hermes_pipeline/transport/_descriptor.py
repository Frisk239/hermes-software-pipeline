"""Runtime descriptor writer and validator (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

The runtime descriptor records protocol version, PID, start identity,
creation time, port, token generation, active release, and state-root
identity. It is written atomically (temp + rename) with owner-only
ACL/mode (Windows: the exact single-ACE DACL via icacls; POSIX: ``0o600``).
Token rotation happens only when the runtime process starts; a Hermes
restart merely re-reads the existing descriptor and token — it never
rotates and never rewrites the descriptor. Removal happens only via the
start-identity algorithm in ``_identity.py``.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from ._acl import protect_descriptor, verify_descriptor_protection
from ._constants import (
    DESCRIPTOR_FILENAME,
    DESCRIPTOR_VERSION,
    PROTOCOL_VERSION,
    RELEASE,
    START_IDENTITY_HEX_CHARS,
    TOKEN_HEX_CHARS,
)
from ._state import ensure_inside_state_root

# Required descriptor fields (mirrored by hermes_shim._descriptor and by the
# golden fixtures under tests/fixtures/transport/).
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


def new_token() -> str:
    """One fresh random bearer token (generated per runtime start only)."""
    return secrets.token_hex(TOKEN_HEX_CHARS // 2)


def new_start_identity() -> str:
    """One fresh random 128-bit start identity (hex)."""
    return secrets.token_hex(START_IDENTITY_HEX_CHARS // 2)


def descriptor_path(root: Path) -> Path:
    return root / "descriptor" / DESCRIPTOR_FILENAME


def build_descriptor(
    *,
    pid: int,
    start_identity: str,
    creation_time: datetime,
    process_start_marker: dict[str, str],
    port: int,
    token: str,
    token_generation: int,
    state_root_identity: str,
) -> dict[str, Any]:
    """One descriptor document with the fixed field set."""
    return {
        "descriptor_version": DESCRIPTOR_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "pid": pid,
        "start_identity": start_identity,
        "creation_time": creation_time.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
        "process_start_marker": process_start_marker,
        "port": port,
        "token": token,
        "token_generation": token_generation,
        "release": RELEASE,
        "state_root_identity": state_root_identity,
    }


def validate_descriptor(document: dict[str, Any]) -> list[str]:
    """Structural validation; empty list means valid.

    Unknown fields are rejected at the trust boundary (data-and-api-
    contracts.md principle 3), matching the committed reject vectors.
    """
    problems: list[str] = []
    unknown = sorted(set(document) - set(REQUIRED_FIELDS))
    if unknown:
        problems.append(f"unknown field(s): {', '.join(unknown)}")
    for field in REQUIRED_FIELDS:
        if field not in document:
            problems.append(f"missing field {field!r}")
    if document.get("descriptor_version") != DESCRIPTOR_VERSION:
        problems.append("unsupported descriptor_version")
    if document.get("protocol_version") != PROTOCOL_VERSION:
        problems.append("unsupported protocol_version")
    for field in ("pid", "port", "token_generation"):
        value = document.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            problems.append(f"{field} must be an integer")
    marker = document.get("process_start_marker")
    marker_dict = cast(dict[str, Any], marker)
    if not isinstance(marker, dict) or not isinstance(marker_dict.get("value"), str):
        problems.append("process_start_marker must carry a string value")
    return problems


def write_descriptor(root: Path, document: dict[str, Any]) -> list[str]:
    """Atomically write the descriptor with owner-only protection.

    Writes to a temp file in the same directory, applies the platform
    owner-only protection, then ``os.replace`` over the target. Returns a
    list of problems (empty on success). A descriptor path resolving
    outside the state root (symlink/junction/reparse-point escape) is
    rejected before any write, so no external directory is ever touched.
    """
    problems = validate_descriptor(document)
    if problems:
        return problems
    target = descriptor_path(root)
    try:
        ensure_inside_state_root(root, target)
    except Exception:
        return ["descriptor path escapes state root"]
    directory = target.parent
    directory.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix="runtime.json.", suffix=".tmp", dir=str(directory)
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
            problems = protect_descriptor(temp_path)
            if problems:
                return problems
            os.replace(temp_path, target)
        finally:
            import contextlib

            with contextlib.suppress(OSError):
                temp_path.unlink()
    except OSError as exc:
        return [f"descriptor write failed: {type(exc).__name__}"]
    return []


def remove_descriptor_if_inside(root: Path) -> None:
    """Remove the descriptor only when its path stays inside the root.

    An escaping descriptor path (attacker-controlled symlink) must never
    be unlinked, because unlink itself is a write outside the root.
    """
    target = descriptor_path(root)
    try:
        ensure_inside_state_root(root, target)
    except Exception:
        return
    import contextlib

    with contextlib.suppress(OSError):
        target.unlink()


def verify_descriptor_protected(root: Path) -> list[str]:
    """Verify the owner-only protection of the committed descriptor."""
    path = descriptor_path(root)
    try:
        ensure_inside_state_root(root, path)
    except Exception:
        return ["descriptor path escapes state root"]
    if not path.is_file():
        return ["descriptor file missing"]
    return verify_descriptor_protection(path)


def read_descriptor(root: Path) -> dict[str, Any] | None:
    """Read and validate the committed descriptor (None when absent/invalid)."""
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
    document = cast(dict[str, Any], document)
    if validate_descriptor(document):
        return None
    return document


def utc_now() -> datetime:
    """Injected wall-clock seam (tests freeze this)."""
    return datetime.now(UTC)


__all__ = [
    "build_descriptor",
    "descriptor_path",
    "new_start_identity",
    "new_token",
    "read_descriptor",
    "remove_descriptor_if_inside",
    "validate_descriptor",
    "verify_descriptor_protected",
    "write_descriptor",
]
