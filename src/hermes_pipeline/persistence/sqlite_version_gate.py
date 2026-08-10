"""SQLite WAL-reset repair-version gate (slice-00-04, AC-08).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

The exact WAL-reset repair-version predicate is an independent per-platform
acceptance gate measured via ``sqlite3.sqlite_version``::

    >=3.51.3 OR (>=3.50.7 AND <3.51.0) OR (>=3.44.6 AND <3.45.0)

Official SQLite fix points are only 3.51.3 and the two named backports; no
3.49.x relaxation exists. The revision-7 managed interpreter pin
(uv-managed CPython 3.12.13) is a precondition for the gate, never a
replacement: a linked library failing the predicate on either required
platform stops the Slice with a Contract Change Request before any spike
persistence conclusion is claimed.

The committed accept and reject version vectors below are part of the
contract; the gate test passes for every accept vector and fails for every
reject vector deterministically.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Final

#: Exact WAL-reset repair-version predicate (revision 7, unchanged).
ACCEPT_VECTORS: Final[tuple[tuple[int, int, int], ...]] = (
    (3, 51, 3),
    (3, 51, 4),
    (3, 50, 7),
    (3, 50, 8),
    (3, 44, 6),
    (3, 44, 7),
)

#: Committed reject vectors that must fail the gate deterministically.
REJECT_VECTORS: Final[tuple[tuple[int, int, int], ...]] = (
    (3, 51, 2),
    (3, 51, 0),
    (3, 50, 6),
    (3, 44, 5),
    (3, 43, 0),
)


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse ``X.Y.Z`` (optionally suffixed, e.g. ``3.53.1``) into a tuple.

    Only the leading digits of the patch segment count: a pre-release suffix
    such as ``10beta2`` still parses as patch ``10``.
    """
    major, minor, patch = version.split(".", 2)[:3]
    leading = re.match(r"\d+", patch)
    patch_number = int(leading.group(0)) if leading else 0
    return (int(major), int(minor), patch_number)


def wal_reset_predicate(version: tuple[int, int, int]) -> bool:
    """True when the linked SQLite version satisfies the repair predicate."""
    major, minor, patch = version
    if (major, minor, patch) >= (3, 51, 3):
        return True
    if (3, 50, 7) <= (major, minor, patch) < (3, 51, 0):
        return True
    return (3, 44, 6) <= (major, minor, patch) < (3, 45, 0)


def linked_sqlite_version() -> tuple[int, int, int]:
    """The ``sqlite3.sqlite_version`` of the running interpreter."""
    return parse_version(sqlite3.sqlite_version)


__all__ = [
    "ACCEPT_VECTORS",
    "REJECT_VECTORS",
    "linked_sqlite_version",
    "parse_version",
    "wal_reset_predicate",
]
