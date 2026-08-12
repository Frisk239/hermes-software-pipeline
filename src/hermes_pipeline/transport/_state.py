"""State-root identity and write-boundary guard (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Mirror of the shim-side state-root identity: a content digest of the
canonical absolute state-root path, so /v1/version and operator output can
name a state root without ever exposing the path itself. The write-boundary
guard rejects every filesystem write derived from the state root whose
resolved target escapes the root (symlink/junction/reparse-point escape)
before any mkdir/temp/replace/unlink can touch the outside.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path


class StateRootBoundaryError(Exception):
    """A state-root-derived path resolves outside the state root."""


def _is_link_or_reparse_point(path: Path) -> bool:
    """Return whether an existing path cannot serve as a trusted root."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise StateRootBoundaryError("state root cannot be inspected") from exc
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & 0x0400)


def _ensure_no_link_ancestors(path: Path) -> None:
    """Reject any link/reparse point on the lexical path to a state root."""
    component = Path(path.anchor)
    for part in path.parts[1:]:
        component = component / part
        if _is_link_or_reparse_point(component):
            raise StateRootBoundaryError(
                "state-root path contains a link or reparse point"
            )


def _trusted_absolute_path(path: Path) -> Path:
    """Reject relative or ``..`` paths before a no-follow ancestor walk."""
    if not path.is_absolute() or ".." in path.parts:
        raise StateRootBoundaryError(
            "state-root path must be absolute and must not contain parent traversal"
        )
    return path


def state_root_identity(root: Path) -> str:
    """A stable opaque identity for a resolved state root."""
    canonical = os.path.normcase(os.path.realpath(root))
    return hashlib.sha256(os.fsencode(canonical)).hexdigest()


def ensure_inside_state_root(root: Path, target: Path) -> None:
    """Reject any target that resolves outside the state root.

    Called before every filesystem write derived from the state root. A
    symlink, junction, or reparse point inside the root that points
    outside is detected by path resolution, so no mkdir, temp file,
    replace, or unlink can escape the root.
    """
    # Do not resolve a link-like root and accept its destination as trusted:
    # the configured state root itself is the write boundary.  Check every
    # lexical derived component too; a link that currently targets inside the
    # root can be swapped before the write and therefore is not trusted.
    lexical_root = _trusted_absolute_path(root)
    lexical_target = _trusted_absolute_path(target)
    _ensure_no_link_ancestors(lexical_root)
    try:
        relative = lexical_target.relative_to(lexical_root)
    except ValueError:
        raise StateRootBoundaryError(f"path escapes state root: {target}") from None
    component = lexical_root
    for part in relative.parts:
        component = component / part
        if _is_link_or_reparse_point(component):
            raise StateRootBoundaryError(
                "state-root path contains a link or reparse point"
            )
    base = root.resolve()
    resolved = target.resolve()
    if resolved != base and not resolved.is_relative_to(base):
        raise StateRootBoundaryError(f"path escapes state root: {target}")


__all__ = ["StateRootBoundaryError", "ensure_inside_state_root", "state_root_identity"]
