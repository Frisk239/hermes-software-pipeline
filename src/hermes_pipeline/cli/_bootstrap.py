"""Shared constants and repository discovery for bootstrap commands."""

from __future__ import annotations

from pathlib import Path

# Stable exit codes: 0 success, 1 check failure, 2 usage error.
EXIT_OK = 0
EXIT_CHECK_FAIL = 1
EXIT_USAGE = 2


def repo_root() -> Path:
    """Repository root, found from the installed source layout.

    Bootstrap tooling is bound to the repository that owns it: the root is
    the nearest ancestor of this file that contains ``scripts/``. This
    keeps ``contracts check`` and ``architecture check`` deterministic
    without ambient environment variables or current-directory dependence.
    """
    return Path(__file__).resolve().parents[3]
