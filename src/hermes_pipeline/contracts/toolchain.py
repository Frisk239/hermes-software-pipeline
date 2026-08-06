"""Lazy-dispatched contract toolchain entry (AC-10).

The ``contracts`` CLI subcommand is parsed by the standard-library dispatch
layer first; only then is this module imported, which pulls in pydantic,
jsonschema, and rfc8785. The Hermes plugin entry, ``--version``, and the
normal runtime path never import this module, and ``contracts`` returns a
bounded error when the development dependencies are absent. Every failure
path returns exit 1 with a UTF-8-byte-limited, control-character-sanitized,
canary-redacted message and never a traceback (AC-10).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from hermes_pipeline import __version__

from .generate import generated_artifacts, write_generated
from .validate import (
    collect_canary_tokens,
    run_contracts_check,
    sanitize_diagnostic,
    sanitize_output,
)

EXIT_OK = 0
EXIT_FAIL = 1


def _repo_root() -> Path | None:
    """Source-checkout root required by the contract commands."""
    from hermes_pipeline.cli._bootstrap import repo_root

    return repo_root()


def _emit(root: Path | None, text: str, *, error: bool = False) -> None:
    """Write sanitized, bounded output (control chars, canaries, byte cap)."""
    try:
        canaries: frozenset[str] = (
            collect_canary_tokens(root) if root is not None else frozenset()
        )
    except (OSError, UnicodeError):
        # This is the last-resort error path. Never let a damaged fixture make
        # the bounded reporter itself raise.
        canaries = frozenset()
    stream = sys.stderr if error else sys.stdout
    stream.write(sanitize_output(text, canaries))


def run_contracts_check_command() -> int:
    """Full read-only validator; 0 pass, 1 fail (bounded output)."""
    root = _repo_root()
    if root is None:
        _emit(
            None,
            "contracts check: FAIL (requires a Hermes Pipeline source checkout)\n",
            error=True,
        )
        return EXIT_FAIL
    ok, output = run_contracts_check(root)
    _emit(root, output)
    return EXIT_OK if ok else EXIT_FAIL


def run_contracts_generate_command() -> int:
    """Development-only write command: regenerate committed projections."""
    root = _repo_root()
    if root is None:
        _emit(
            None,
            "contracts generate: FAIL (requires a Hermes Pipeline source checkout)\n",
            error=True,
        )
        return EXIT_FAIL
    changed = write_generated(root, __version__)
    if changed:
        _emit(
            root,
            "contracts generate: updated "
            + ", ".join(p.as_posix() for p in changed)
            + "\n",
        )
    else:
        _emit(root, "contracts generate: OK (no drift)\n")
    return EXIT_OK


def committed_generated_paths(root: Path) -> set[str]:
    """The committed generated-artifact file set (read-only discovery).

    Every ``*.json`` under ``schemas/`` plus the two committed ``contracts/``
    documents; the README files are documentation, not generated artifacts.
    """
    committed: set[str] = set()
    schema_dir = root / "schemas"
    if schema_dir.is_dir():
        for path in schema_dir.rglob("*.json"):
            committed.add(path.relative_to(root).as_posix())
    for name in ("contracts/openapi.json", "contracts/compatibility-registry.json"):
        if (root / name).is_file():
            committed.add(name)
    return committed


def run_contracts_drift_check_command() -> int:
    """Read-only zero-drift gate (AC-02): generate into a TemporaryDirectory,
    then byte-compare the exact file set read-only against the committed
    files."""
    root = _repo_root()
    if root is None:
        _emit(
            None,
            "contracts drift-check: FAIL (requires a Hermes Pipeline source "
            "checkout)\n",
            error=True,
        )
        return EXIT_FAIL

    generated = generated_artifacts(__version__)
    with tempfile.TemporaryDirectory(prefix="hermes-contracts-drift-") as tmp:
        tmp_root = Path(tmp)
        for relative, content in generated.items():
            target = tmp_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content.encode("utf-8"))

        expected = {p.as_posix() for p in generated}
        committed = committed_generated_paths(root)
        differing: list[str] = []
        for relative in sorted(expected | committed):
            committed_file = root / relative
            generated_file = tmp_root / relative
            if not committed_file.is_file():
                differing.append(f"{relative}: missing from the checkout")
                continue
            if not generated_file.is_file():
                differing.append(f"{relative}: not generated")
                continue
            if committed_file.read_bytes() != generated_file.read_bytes():
                differing.append(f"{relative}: differs")
        if differing:
            lines = ["contracts drift-check: FAIL"]
            for line in differing[:20]:
                # Repository paths are untrusted input. Sanitize them before
                # assembling one bounded diagnostic block: emitting one line
                # at a time would bypass the total output-byte cap.
                lines.append(f"  {sanitize_diagnostic(line)}")
            if len(differing) > 20:
                lines.append(f"  ... {len(differing) - 20} further file(s) differ")
            _emit(root, "\n".join(lines) + "\n")
            return EXIT_FAIL
        _emit(
            root,
            f"contracts drift-check: OK ({len(generated)} generated file(s) "
            "byte-identical in a temporary directory)\n",
        )
        return EXIT_OK


def run_contracts_command(argv: list[str]) -> int:
    """Dispatch one ``contracts`` subcommand after lazy toolchain import.

    Called only after the subcommand name has been parsed by the
    standard-library CLI layer. Every failure path returns a bounded,
    sanitized error (exit 1), never a traceback, including malformed
    Schema-registry input (AC-10).
    """
    subcommand = argv[0] if argv else ""
    try:
        if subcommand == "check":
            return run_contracts_check_command()
        if subcommand == "generate":
            return run_contracts_generate_command()
        if subcommand == "drift-check":
            return run_contracts_drift_check_command()
    except ImportError:
        _emit(
            None,
            f"contracts {subcommand}: FAIL (contract toolchain unavailable: "
            "development dependencies are not installed)\n",
            error=True,
        )
        return EXIT_FAIL
    except Exception as exc:
        root = _repo_root()
        _emit(
            root,
            "contracts "
            f"{subcommand}: FAIL ({type(exc).__name__}: "
            f"{sanitize_diagnostic(str(exc))})\n",
            error=True,
        )
        return EXIT_FAIL
    return EXIT_FAIL  # unreachable when the dispatcher parses first
