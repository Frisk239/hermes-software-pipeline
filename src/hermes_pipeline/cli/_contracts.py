"""In-process delegation to the bootstrap Schema checker (slice-00-02).

``contracts check`` must not fork a second validation implementation: it
loads the existing ``scripts/check_schemas.py`` module from the repository
that owns this distribution and forwards its ``main`` entry, so the
bootstrap checker remains the single Schema-validation authority.
"""

from __future__ import annotations

import importlib.util
import sys

from ._bootstrap import EXIT_CHECK_FAIL, repo_root


def run_contracts_check(argv: list[str]) -> int:
    """Run the bootstrap Schema checker in-process with the given argv."""
    root = repo_root()
    scripts = root / "scripts"
    script = scripts / "check_schemas.py"
    if not script.is_file():
        print(
            f"contracts check: FAIL (bootstrap checker missing: {script})",
            file=sys.stderr,
        )
        return EXIT_CHECK_FAIL
    # The bootstrap module imports its helper with a bare name, so the
    # scripts directory must be importable for this process only.
    sys.path.insert(0, str(scripts))
    try:
        spec = importlib.util.spec_from_file_location("check_schemas", script)
        if spec is None or spec.loader is None:
            print(
                "contracts check: FAIL (cannot load bootstrap checker)",
                file=sys.stderr,
            )
            return EXIT_CHECK_FAIL
        module = importlib.util.module_from_spec(spec)
        sys.modules["check_schemas"] = module
        spec.loader.exec_module(module)
        return int(module.main(argv))
    finally:
        sys.modules.pop("check_schemas", None)
        sys.path.pop(0)
