"""State-root resolution and layout for the Hermes Shim (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

The lifecycle state root is derived from HERMES_HOME (fixed decision D5):
``<HERMES_HOME>/software-pipeline/`` with the accepted child layout
``descriptor/``, ``runtimes/``, ``logs/``. Each child carries an ownership
marker; destructive operations validate the resolved path and marker.
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys
from pathlib import Path

from ._constants import (
    DESCRIPTOR_DIRNAME,
    LOGS_DIRNAME,
    OWNERSHIP_MARKER_FILENAME,
    RUNTIMES_DIRNAME,
    STATE_ROOT_CHILDREN,
    STATE_ROOT_NAME,
)

# Platform defaults mirror Hermes' own home resolution
# (hermes_constants.py:78-91): %LOCALAPPDATA%\hermes on Windows,
# ~/.hermes on POSIX. The environment variable always wins.
_DEFAULT_HOME_WINDOWS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "hermes"
_DEFAULT_HOME_POSIX = Path.home() / ".hermes"


def hermes_home(environ: dict[str, str] | None = None) -> Path:
    """Resolve HERMES_HOME (explicit env override or platform default).

    ``environ`` is injectable for deterministic tests; the real process
    environment is used when omitted.
    """
    env = os.environ if environ is None else environ
    override = env.get("HERMES_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        return _DEFAULT_HOME_WINDOWS
    return _DEFAULT_HOME_POSIX


def state_root(home: Path) -> Path:
    """The lifecycle state root beneath a Hermes home."""
    return home / STATE_ROOT_NAME


def child_layout(root: Path) -> dict[str, Path]:
    """Resolve the accepted child paths without creating anything."""
    return {
        DESCRIPTOR_DIRNAME: root / DESCRIPTOR_DIRNAME,
        RUNTIMES_DIRNAME: root / RUNTIMES_DIRNAME,
        LOGS_DIRNAME: root / LOGS_DIRNAME,
    }


def state_root_identity(root: Path) -> str:
    """A stable opaque identity for a resolved state root.

    The identity is a content digest of the canonical absolute path; it
    never exposes the path itself (redaction rule). It is reported by
    /v1/version and used by doctor/status output.
    """
    canonical = os.path.normcase(os.path.realpath(root))
    return hashlib.sha256(os.fsencode(canonical)).hexdigest()


class StateRootBoundaryError(Exception):
    """A state-root-derived path resolves outside the state root."""


def _is_link_or_reparse_point(path: Path) -> bool:
    """Return whether an existing path must not be trusted as a root.

    ``Path.is_symlink()`` does not cover Windows junctions.  ``lstat`` keeps
    the inspection no-follow and exposes the Windows reparse-point bit when
    it is present.  A missing path is safe to create; an unreadable one is
    rejected by the caller rather than resolved optimistically.
    """
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise StateRootBoundaryError("state root cannot be inspected") from exc
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & 0x0400)


def _ensure_no_link_ancestors(path: Path) -> None:
    """Reject a link/reparse point in the complete lexical path to ``path``.

    Checking only ``<HERMES_HOME>/software-pipeline`` is insufficient: when
    ``HERMES_HOME`` itself is a junction or symlink, the final component is a
    normal directory but all state still lives outside the configured home.
    Walk from the filesystem anchor without resolving any component first.
    """
    component = Path(path.anchor)
    for part in path.parts[1:]:
        component = component / part
        if _is_link_or_reparse_point(component):
            raise StateRootBoundaryError(
                "state-root path contains a link or reparse point"
            )


def _trusted_absolute_path(path: Path) -> Path:
    """Require an absolute, traversal-free lexical path before resolution.

    ``abspath()`` removes ``..`` before a no-follow walk.  That is unsafe:
    a symlink before ``..`` is followed by kernel path resolution before the
    parent component is applied.  Reject relative and parent-traversal forms
    rather than normalizing away the evidence.
    """
    if not path.is_absolute() or ".." in path.parts:
        raise StateRootBoundaryError(
            "state-root path must be absolute and must not contain parent traversal"
        )
    return path


def ensure_inside_state_root(root: Path, target: Path) -> None:
    """Reject any target that resolves outside the state root.

    Called before every filesystem write or read derived from the state
    root (setup layout, runtime logs, descriptor read/remove, provision
    environment). A symlink, junction, or reparse point inside the root
    that points outside is detected by resolution, so no mkdir, temp
    file, replace, unlink, or read can escape the root.
    """
    # The root itself is the trust boundary.  Resolving it first would turn
    # a state-root symlink or junction into an apparently safe external root,
    # then allow writes there.  Reject it before either resolution or mkdir.
    lexical_root = _trusted_absolute_path(root)
    lexical_target = _trusted_absolute_path(target)
    _ensure_no_link_ancestors(lexical_root)
    try:
        relative = lexical_target.relative_to(lexical_root)
    except ValueError:
        raise StateRootBoundaryError(f"path escapes state root: {target}") from None
    # No derived component may be a link or reparse point either.  This is
    # deliberately stricter than a resolved-path containment check: a link
    # that currently targets inside the root can be swapped between check and
    # write, so it is not a trusted write path.
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


# Spike installation identity recorded in every ownership marker.
_MARKER_TEXT = (
    "hermes-pipeline spike ownership marker\n"
    "schema-version: 1\n"
    "release: hermes-pipeline-0.1.0-slice-00-05-spike\n"
)


def ensure_layout(root: Path) -> None:
    """Create the state-root layout with ownership markers (setup).

    Idempotent: repeated setup calls converge. Each child gets an
    OWNERSHIP marker recording the spike installation identity; destructive
    operations must validate the marker before touching the child. Every
    child is guarded before creation: a symlinked/junctioned child that
    resolves outside the root is refused with zero outside writes.
    """
    ensure_inside_state_root(root, root)
    root.mkdir(parents=True, exist_ok=True)
    for name in STATE_ROOT_CHILDREN:
        child = root / name
        ensure_inside_state_root(root, child)
        child.mkdir(parents=True, exist_ok=True)
        own = child / OWNERSHIP_MARKER_FILENAME
        ensure_inside_state_root(root, own)
        if not own.is_file():
            own.write_text(_MARKER_TEXT, encoding="utf-8")


def ownership_marker_valid(root: Path) -> bool:
    """Read-only validation of the ownership markers.

    True only when every required child exists with a matching marker.
    Never creates directories or markers: a missing state root reports
    invalid with zero writes (doctor must report, never repair).
    """
    try:
        ensure_inside_state_root(root, root)
    except StateRootBoundaryError:
        return False
    if not root.is_dir():
        return False
    for name in STATE_ROOT_CHILDREN:
        child = root / name
        if not child.is_dir():
            return False
        own = child / OWNERSHIP_MARKER_FILENAME
        try:
            if own.read_text(encoding="utf-8") != _MARKER_TEXT:
                return False
        except OSError:
            return False
    return True
