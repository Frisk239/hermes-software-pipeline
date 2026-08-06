"""Lazy-dispatched ``contracts`` CLI subcommand (slice-00-03).

Subcommand parsing happens here with the standard library only; the contract
toolchain (pydantic, jsonschema, rfc8785) is imported only after the
subcommand name is known, so the Hermes plugin entry, ``--version``, and the
normal runtime path never import it (AC-10).
"""

from __future__ import annotations

import sys

from ._bootstrap import EXIT_CHECK_FAIL, EXIT_USAGE

CONTRACTS_SUBCOMMANDS = ("check", "generate", "drift-check")

USAGE = (
    "usage: hermes-pipeline-runtime contracts <check|generate|drift-check>\n"
    "  check         full read-only contract registry validation\n"
    "  generate      development-only: regenerate committed projections\n"
    "  drift-check   read-only: prove committed projections match generation\n"
)


def run_contracts(argv: list[str]) -> int:
    """Parse the subcommand, then lazily import and run the toolchain."""
    if not argv or argv[0] not in CONTRACTS_SUBCOMMANDS:
        sys.stderr.write(USAGE)
        return EXIT_USAGE
    if len(argv) != 1:
        print(
            f"hermes-pipeline-runtime: contracts {argv[0]} takes no arguments",
            file=sys.stderr,
        )
        sys.stderr.write(USAGE)
        return EXIT_USAGE

    # The toolchain is imported only after the subcommand is parsed. A
    # missing development dependency surfaces as a bounded error (AC-10).
    # The exception payload is untrusted input, so this standard-library
    # branch reports fixed safe text: no traceback, no injected control
    # characters, no canaries, and a bounded byte count.
    try:
        from hermes_pipeline.contracts.toolchain import run_contracts_command
    except ImportError:
        print(
            f"contracts {argv[0]}: FAIL (contract toolchain unavailable: "
            "development dependencies are not installed)",
            file=sys.stderr,
        )
        return EXIT_CHECK_FAIL

    return run_contracts_command(argv)
