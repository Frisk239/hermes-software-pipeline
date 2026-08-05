"""In-process delegation to the bootstrap Schema checker (slice-00-02).

``contracts check`` must not fork a second validation implementation: it
loads the existing ``scripts/check_schemas.py`` module from the repository
that owns this distribution and forwards its ``main`` entry, so the
bootstrap checker remains the single Schema-validation authority.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import cast

from ._bootstrap import EXIT_CHECK_FAIL, isolated_script_module, repo_root


def run_contracts_check(argv: list[str]) -> int:
    """Run the bootstrap Schema checker in-process with the given argv."""
    root = repo_root()
    if root is None:
        print(
            "contracts check: FAIL (requires a Hermes Pipeline source checkout)",
            file=sys.stderr,
        )
        return EXIT_CHECK_FAIL
    scripts = root / "scripts"
    script = scripts / "check_schemas.py"
    if not script.is_file():
        print(
            f"contracts check: FAIL (bootstrap checker missing: {script})",
            file=sys.stderr,
        )
        return EXIT_CHECK_FAIL
    try:
        with isolated_script_module("check_schemas", script) as module:
            main = getattr(module, "main", None)
            if not callable(main):
                print(
                    "contracts check: FAIL (bootstrap checker has no main entry)",
                    file=sys.stderr,
                )
                return EXIT_CHECK_FAIL
            checker_main = cast(Callable[[list[str]], int], main)
            return checker_main(argv)
    except (ImportError, OSError) as exc:
        print(
            f"contracts check: FAIL (cannot load bootstrap checker: {exc})",
            file=sys.stderr,
        )
        return EXIT_CHECK_FAIL
