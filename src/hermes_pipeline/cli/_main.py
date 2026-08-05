"""Bootstrap CLI for the hermes-pipeline runtime (slice-00-02).

Supported surface, deliberately small:

- ``--version`` prints the installed distribution version (sole version
  source: package metadata) and exits 0;
- ``contracts check`` delegates in-process to the existing bootstrap Schema
  checker ``scripts/check_schemas.py`` from a source checkout (no second
  validation logic, no shell string);
- ``architecture check`` runs the standard-library AST import-boundary
  checker against ``src/hermes_pipeline`` in a source checkout, or against
  an explicit ``--root`` path.

Exit codes are stable: 0 success, 1 check failure, 2 usage error.
"""

from __future__ import annotations

import sys
from pathlib import Path

from hermes_pipeline import __version__

from ._architecture_check import check_package_tree, render_diagnostics
from ._bootstrap import EXIT_CHECK_FAIL, EXIT_OK, EXIT_USAGE, repo_root
from ._contracts import run_contracts_check

DEFAULT_PACKAGE_ROOT = "src/hermes_pipeline"

USAGE = (
    "usage: hermes-pipeline-runtime [--version] <command> [args]\n"
    "commands:\n"
    "  contracts check     validate the committed Schema registry\n"
    "  architecture check  validate package import boundaries\n"
)


def _usage_error(message: str) -> int:
    print(f"hermes-pipeline-runtime: {message}", file=sys.stderr)
    sys.stderr.write(USAGE)
    return EXIT_USAGE


def _run_architecture_check(argv: list[str]) -> int:
    if argv:
        if argv[0] != "--root" or len(argv) != 2:
            return _usage_error("architecture check accepts only --root <path>")
        root = Path(argv[1]).resolve()
    else:
        repository = repo_root()
        if repository is None:
            print(
                "architecture check: FAIL (requires a Hermes Pipeline source checkout)",
                file=sys.stderr,
            )
            return EXIT_CHECK_FAIL
        root = repository / DEFAULT_PACKAGE_ROOT
    diagnostics = check_package_tree(root)
    if diagnostics:
        print("architecture check: FAIL")
        print(render_diagnostics(diagnostics))
        return EXIT_CHECK_FAIL
    print(f"architecture check: OK ({root} satisfies the import boundaries)")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write(USAGE)
        return EXIT_USAGE
    if args[0] == "--version":
        if len(args) != 1:
            return _usage_error("--version takes no arguments")
        print(__version__)
        return EXIT_OK
    if args[0] == "contracts":
        if len(args) < 2 or args[1] != "check":
            return _usage_error("expected 'contracts check'")
        return run_contracts_check(args[2:])
    if args[0] == "architecture":
        if len(args) < 2 or args[1] != "check":
            return _usage_error("expected 'architecture check'")
        return _run_architecture_check(args[2:])
    return _usage_error(f"unknown command {args[0]!r}")
