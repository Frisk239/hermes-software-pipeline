#!/usr/bin/env python3
"""Dependency-free bootstrap Schema integrity checker (slice-00-01).

Validates every ``*.json`` file under the schema directory using only the
Python standard library:

- strict UTF-8 decoding and JSON parsing;
- each document is a JSON object with a string ``$id`` under
  ``https://schemas.hermes-pipeline.dev/``;
- ``$id`` values are unique across the registry;
- every local (``#/...``) and absolute (``https://...``) ``$ref`` resolves to
  a declared Schema, and every JSON Pointer fragment (RFC 6901) resolves
  within its target document;
- when checking the repository Schema registry, the declared ``$id`` set
  must exactly equal the locked set of the 14 bootstrap Schemas, so deleting
  or renaming a Schema fails even if nothing references it.

This is a bootstrap integrity gate: full Draft 2020-12 meta-schema
validation and Pydantic-authoring adoption are owned by slice-00-03.

``--self-test-negative`` executes the checker as a subprocess against the
bootstrap fixtures and asserts that positive fixtures exit 0 and every
deliberately broken fixture exits nonzero, proving the CLI's stable exit
behavior rather than reusing in-process state.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Keep the worktree free of __pycache__ artifacts: the checker imports a
# local module, and bytecode caching must not leave untracked files behind.
sys.dont_write_bytecode = True

from _check_common import Reporter, fixture_roots, render_bounded_lines, repo_root

# Exit codes: 0 = pass, 1 = check failure.
EXIT_OK = 0
EXIT_FAIL = 1

SCHEMA_ID_PREFIX = "https://schemas.hermes-pipeline.dev/"

# Locked identity set of the 14 bootstrap Schemas (BOOT-02 / AC-02).
EXPECTED_SCHEMA_IDS = frozenset(
    {
        "https://schemas.hermes-pipeline.dev/common/definitions/v1",
        "https://schemas.hermes-pipeline.dev/engineering/closeout/v1",
        "https://schemas.hermes-pipeline.dev/engineering/context-manifest/v1",
        "https://schemas.hermes-pipeline.dev/engineering/contract-change-request/v1",
        "https://schemas.hermes-pipeline.dev/engineering/execution-report/v1",
        "https://schemas.hermes-pipeline.dev/engineering/phase-plan/v1",
        "https://schemas.hermes-pipeline.dev/engineering/review-verdict/v1",
        "https://schemas.hermes-pipeline.dev/engineering/slice-contract/v1",
        "https://schemas.hermes-pipeline.dev/runtime/artifact-manifest/v1",
        "https://schemas.hermes-pipeline.dev/runtime/capability-profile/v1",
        "https://schemas.hermes-pipeline.dev/runtime/command-receipt/v1",
        "https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
        "https://schemas.hermes-pipeline.dev/runtime/evidence-bundle/v1",
        "https://schemas.hermes-pipeline.dev/runtime/pipeline-event/v1",
    }
)
REQUIRED_SCHEMA_NEGATIVE_FIXTURES = frozenset(
    {
        "bad-array-index",
        "bad-pointer",
        "broken-json",
        "duplicate-id",
        "invalid-schema",
        "missing-schema",
        "oversized-ref",
        "unresolvable-ref",
    }
)


def load_documents(schema_dir: Path, report: Reporter) -> dict[Path, object]:
    """Parse every JSON file under schema_dir; report failures."""
    documents: dict[Path, object] = {}
    for path in sorted(schema_dir.rglob("*.json")):
        report.scanned += 1
        if path.is_symlink():
            report.issue(f"{path}: Schema document must not be a symbolic link")
            continue
        if not path.resolve().is_relative_to(schema_dir):
            report.issue(f"{path}: Schema document resolves outside the checked root")
            continue
        try:
            raw = path.read_bytes()
        except OSError as exc:
            report.issue(f"{path}: unreadable ({exc})")
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            report.issue(f"{path}: not valid UTF-8 ({exc.reason} at byte {exc.start})")
            continue
        try:
            documents[path] = json.loads(text)
        except json.JSONDecodeError as exc:
            report.issue(
                f"{path}: invalid JSON (line {exc.lineno}, column {exc.colno}: "
                f"{exc.msg})"
            )
    return documents


def schema_ids(
    documents: dict[Path, object], report: Reporter
) -> dict[str, Path]:
    """Collect declared $ids; report missing, malformed, or duplicate ids."""
    ids: dict[str, Path] = {}
    for path, document in documents.items():
        if not isinstance(document, dict):
            report.issue(f"{path}: Schema document is not a JSON object")
            continue
        schema_id = document.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            report.issue(f"{path}: missing string $id")
            continue
        if not schema_id.startswith(SCHEMA_ID_PREFIX):
            report.issue(
                f"{path}: $id {schema_id!r} is outside the registry "
                f"({SCHEMA_ID_PREFIX}...)"
            )
        if schema_id in ids:
            report.issue(
                f"{path}: duplicate $id {schema_id!r} (also declared by {ids[schema_id]})"
            )
        else:
            ids[schema_id] = path
    return ids


def check_identity_lock(
    declared: dict[str, Path], report: Reporter
) -> None:
    """The declared $id set must exactly equal the locked bootstrap set."""
    declared_ids = set(declared)
    for schema_id in sorted(EXPECTED_SCHEMA_IDS - declared_ids):
        report.issue(
            f"expected bootstrap Schema $id not declared: {schema_id}"
        )
    for schema_id in sorted(declared_ids - EXPECTED_SCHEMA_IDS):
        report.issue(
            f"unexpected Schema $id (outside the locked bootstrap set): "
            f"{schema_id} ({declared[schema_id]})"
        )


def decode_pointer_token(token: str) -> str | None:
    """Decode one JSON Pointer token; None on invalid escape."""
    out: list[str] = []
    i = 0
    while i < len(token):
        char = token[i]
        if char == "~":
            if i + 1 >= len(token) or token[i + 1] not in ("0", "1"):
                return None
            out.append("~" if token[i + 1] == "0" else "/")
            i += 2
        else:
            out.append(char)
            i += 1
    return "".join(out)


def resolve_pointer(document: object, pointer: str) -> bool:
    """True if the JSON Pointer resolves inside document (RFC 6901).

    Array reference tokens must be a decimal representation of an index in
    [0, 2^31-1] with no leading zeros, or exactly '-' (which never refers to
    an existing member). Tokens such as '-0' and '01' are invalid.
    """
    if not pointer:
        return True
    if not pointer.startswith("/"):
        return False
    current = document
    for raw_token in pointer[1:].split("/"):
        token = decode_pointer_token(raw_token)
        if token is None:
            return False
        if isinstance(current, dict):
            if token not in current:
                return False
            current = current[token]
        elif isinstance(current, list):
            if token == "-":
                return False  # "-" denotes a nonexistent member
            if not token.isdigit() or (len(token) > 1 and token[0] == "0"):
                return False
            index = int(token)
            if index > 2**31 - 1 or index >= len(current):
                return False
            current = current[index]
        else:
            return False
    return True


def check_refs(
    path: Path,
    document: object,
    registry: dict[str, Path],
    documents: dict[Path, object],
    report: Reporter,
) -> None:
    """Resolve every $ref found recursively inside document."""

    def walk(node: object, trail: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref":
                    _resolve_ref(path, value, trail, registry, documents, report)
                else:
                    walk(value, f"{trail}/{key}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{trail}/{i}")

    walk(document, "")


def _resolve_ref(
    path: Path,
    ref: object,
    trail: str,
    registry: dict[str, Path],
    documents: dict[Path, object],
    report: Reporter,
) -> None:
    if not isinstance(ref, str):
        report.issue(f"{path}: $ref at '{trail}' is not a string")
        return
    uri, separator, fragment = ref.partition("#")
    if not separator:
        fragment = ""
    if uri:
        target_path = registry.get(uri)
        if target_path is None:
            report.issue(
                f"{path}: $ref at '{trail}' does not resolve to a declared "
                f"Schema: {ref}"
            )
            return
        target = documents.get(target_path)
    else:
        target = documents.get(path)

    if fragment and not fragment.startswith("/"):
        report.issue(
            f"{path}: $ref at '{trail}' uses an unsupported non-pointer "
            f"fragment: {ref}"
        )
        return
    if not resolve_pointer(target, fragment):
        report.issue(
            f"{path}: $ref at '{trail}' JSON Pointer does not resolve: {ref}"
        )


def check_schemas(
    schema_dir: Path, report: Reporter, lock_identity: bool = False
) -> None:
    """Run every Schema integrity check against schema_dir."""
    if schema_dir.is_symlink():
        report.issue(f"{schema_dir}: Schema directory must not be a symbolic link")
        return
    if not schema_dir.is_dir():
        report.issue(f"{schema_dir}: Schema directory missing")
        return
    documents = load_documents(schema_dir, report)
    registry = schema_ids(documents, report)
    if lock_identity:
        check_identity_lock(registry, report)
    for path, document in documents.items():
        check_refs(path, document, registry, documents, report)


def run_self_test_negative(root: Path) -> tuple[list[str], bool]:
    """Execute the checker as a subprocess against the bootstrap fixtures.

    A fixture passes only when the checker command exits 0 for positive
    fixtures and exits nonzero for negative fixtures, proving the stable
    CLI exit behavior. Returns (rendered lines, all_ok).
    """
    script = Path(__file__).resolve()
    lines: list[str] = []
    all_ok = True
    try:
        cases = fixture_roots(
            root,
            "positive/schemas",
            "negative/schemas",
            REQUIRED_SCHEMA_NEGATIVE_FIXTURES,
        )
    except ValueError as exc:
        return [f"fixture inventory: FAIL ({exc})"], False
    for name, path, should_pass in cases:
        argv = [sys.executable, str(script), "--schema-dir", str(path)]
        if name == "missing-schema":
            argv.append("--lock-identity")
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            ok = False
            proc = None
        else:
            expected_code = EXIT_OK if should_pass else EXIT_FAIL
            ok = proc.returncode == expected_code
        all_ok = all_ok and ok
        actual = "timeout" if proc is None else f"exit {proc.returncode}"
        lines.append(
            f"fixture {name}: expected exit "
            f"{EXIT_OK if should_pass else EXIT_FAIL}, got {actual} -> "
            f"{'PASS' if ok else 'FAIL'}"
        )
        if proc is None:
            lines.append("  (subprocess timed out)")
            continue
        detail = (proc.stdout + proc.stderr).strip().splitlines()
        for line in detail[:8]:
            lines.append(f"  {line}")
        if len(detail) > 8:
            lines.append("  ... (output truncated)")
    return lines, all_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dependency-free bootstrap Schema integrity checker."
    )
    parser.add_argument(
        "--self-test-negative",
        action="store_true",
        help="execute the checker against broken fixtures and assert nonzero exits",
    )
    parser.add_argument(
        "--schema-dir",
        default=None,
        help="schema directory to check (default: <repo>/schemas)",
    )
    parser.add_argument(
        "--lock-identity",
        action="store_true",
        help="require the declared $id set to equal the locked bootstrap set",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    schema_dir = (
        Path(args.schema_dir).resolve()
        if args.schema_dir
        else root / "schemas"
    )
    report = Reporter()
    if not schema_dir.is_relative_to(root):
        report.issue(
            f"{schema_dir}: Schema directory must remain inside the repository"
        )
    else:
        check_schemas(
            schema_dir,
            report,
            lock_identity=args.lock_identity or schema_dir == root / "schemas",
        )

    self_test_lines: list[str] = []
    self_test_ok = True
    if args.self_test_negative:
        self_test_lines, self_test_ok = run_self_test_negative(root)

    if report.has_issues:
        print("check_schemas: FAIL")
        print(report.render())
        return EXIT_FAIL
    if not self_test_ok:
        print("check_schemas: FAIL (self-test-negative)")
        print(render_bounded_lines(self_test_lines))
        return EXIT_FAIL
    if args.self_test_negative:
        print(render_bounded_lines(self_test_lines))
    print(f"check_schemas: OK ({report.scanned} Schema document(s) checked)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
