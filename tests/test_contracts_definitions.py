"""Per-$defs fragment tests for ``common/definitions`` (AC-04).

``common/definitions`` is a ``$defs`` type library, not an instantiable
payload Schema; each definition gets fragment tests instead of instance
corpora. Every fragment case is validated by three authorities that must
agree: the f36 snapshot ``$defs`` entry, the committed generated ``$defs``
entry, and the corresponding authoring type. The deterministic RFC 3339
checker is local to each Draft 2020-12 validator (revision 7), so
``format: date-time`` violations are rejected by both Schema authorities and
the authoring type, and integer fragments accept finite integral JSON
numbers such as ``3.0`` while rejecting strings, booleans, and non-integral
numbers.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError
from referencing import Registry, Resource

from hermes_pipeline.contracts.definitions import DEFINITION_TYPES, DEFINITIONS_ID
from hermes_pipeline.contracts.formats import build_format_checker

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = REPO_ROOT / "tests" / "fixtures" / "contracts" / "snapshots" / "common"


def _accepts(validator: Any, value: object) -> bool:
    # pyright's bundled jsonschema stub types is_valid via a recursive
    # _JsonParameter alias it cannot resolve in strict mode.
    return bool(validator.is_valid(value))


FRAGMENTS: dict[str, tuple[list[object], list[object]]] = {
    "utcTimestamp": (
        [
            "2026-08-06T00:00:00.000Z",
            "2026-08-06T09:30:00+08:00",
            "2026-08-06T23:59:60Z",  # RFC 3339 leap second
            "2026-08-06t09:30:00z",  # lower-case t/z are permitted
        ],
        [
            123,
            None,
            ["2026-08-06T00:00:00.000Z"],
            "not-a-date",
            "2026-08-06T00:00:00",  # no time offset
            "2026-13-06T00:00:00Z",  # month 13
            "2026-08-06T24:00:00Z",  # hour 24
            "2026-08-06T00:00:00+25:00",  # offset hour 25
            "2026-08-06T00:00:00+08:60",  # offset minute 60
            "2026-02-30T00:00:00Z",  # impossible calendar day
        ],
    ),
    "gitSha": (
        ["a" * 40, "b" * 64],
        ["zz", "a" * 39, "A" * 40],
    ),
    "sha256": (
        ["sha256:" + "c" * 64],
        ["sha256:" + "c" * 63, "md5:" + "d" * 32, "c" * 64],
    ),
    "relativePath": (
        ["docs/guide.md", "src/hermes_pipeline/contracts/__init__.py"],
        ["/abs/path", "../escape.md", "C:/win/path", "a\\b", ""],
    ),
    "identity": (
        ["scope_name", "repo_Owner-1"],
        ["name", "1scope_name", "scope"],
    ),
    "schemaIdentity": (
        [
            {
                "schema_id": "https://schemas.hermes-pipeline.dev/x/v1",
                "schema_version": 1,
            },
            {
                "schema_id": "https://schemas.hermes-pipeline.dev/x/v1",
                "schema_version": 3.0,  # finite integral JSON number
            },
        ],
        [
            {"schema_id": "https://schemas.hermes-pipeline.dev/x/v1"},
            {
                "schema_id": "https://schemas.hermes-pipeline.dev/x/v1",
                "schema_version": 0,
            },
            {
                "schema_id": "https://schemas.hermes-pipeline.dev/x/v1",
                "schema_version": 1,
                "extra": 1,
            },
            {
                "schema_id": "https://schemas.hermes-pipeline.dev/x/v1",
                "schema_version": 3.5,  # non-integral number
            },
            {
                "schema_id": "https://schemas.hermes-pipeline.dev/x/v1",
                "schema_version": "3",  # string coercion forbidden
            },
            {
                "schema_id": "https://schemas.hermes-pipeline.dev/x/v1",
                "schema_version": True,  # boolean coercion forbidden
            },
        ],
    ),
    "fileReference": (
        [
            {
                "path": "docs/guide.md",
                "digest": "sha256:" + "c" * 64,
                "purpose": "governing",
            }
        ],
        [
            {
                "path": "../escape.md",
                "digest": "sha256:" + "c" * 64,
                "purpose": "governing",
            },
            {"path": "docs/guide.md", "digest": "sha256:zz", "purpose": "governing"},
            {"path": "docs/guide.md", "digest": "sha256:" + "c" * 64},
        ],
    ),
    "artifactReference": (
        [
            {
                "artifact_id": "art_evidence_001",
                "manifest_digest": "sha256:" + "c" * 64,
                "role": "evidence",
            }
        ],
        [
            {
                "artifact_id": "artifact_1",
                "manifest_digest": "sha256:" + "c" * 64,
                "role": "evidence",
            },
            {
                "artifact_id": "art_evidence_001",
                "manifest_digest": "sha256:bad",
                "role": "evidence",
            },
            {
                "artifact_id": "art_evidence_001",
                "manifest_digest": "sha256:" + "c" * 64,
            },
        ],
    ),
    "engineeringRisk": (
        [
            {
                "risk_id": "R-01",
                "description": "d",
                "impact": "HIGH",
                "mitigation": "m",
                "trigger": "t",
            }
        ],
        [
            {
                "risk_id": "R1",
                "description": "d",
                "impact": "HIGH",
                "mitigation": "m",
                "trigger": "t",
            },
            {
                "risk_id": "R-01",
                "description": "d",
                "impact": "UNKNOWN",
                "mitigation": "m",
                "trigger": "t",
            },
            {
                "risk_id": "R-01",
                "description": "d",
                "impact": "HIGH",
                "mitigation": "m",
            },
        ],
    ),
}


def _definitions_documents() -> list[dict[str, Any]]:
    """The snapshot and generated ``common/definitions`` documents."""
    documents: list[dict[str, Any]] = []
    for path in (
        SNAPSHOT_DIR / "definitions.schema.json",
        REPO_ROOT / "schemas" / "common" / "definitions.schema.json",
    ):
        documents.append(json.loads(path.read_text(encoding="utf-8")))
    return documents


def _definitions_validator(
    document: dict[str, Any], fragment: str
) -> Draft202012Validator:
    registry: Registry[Any] = Registry()
    registry = registry.with_resource(DEFINITIONS_ID, Resource.from_contents(document))
    schema = {"$ref": f"{DEFINITIONS_ID}#/$defs/{fragment}"}
    return Draft202012Validator(
        schema,
        format_checker=build_format_checker(),
        registry=registry,
    )


def test_every_fragment_has_positive_and_negative_cases() -> None:
    assert set(FRAGMENTS) == set(DEFINITION_TYPES)
    for name, (positive, negative) in FRAGMENTS.items():
        assert positive, name
        assert negative, name


@pytest.mark.parametrize("fragment", sorted(FRAGMENTS))
def test_fragment_positive_and_negative_agree_three_way(fragment: str) -> None:
    adapter = TypeAdapter(DEFINITION_TYPES[fragment])
    positive, negative = FRAGMENTS[fragment]
    for document in _definitions_documents():
        validator = _definitions_validator(document, fragment)
        for value in positive:
            assert _accepts(validator, value), (fragment, value)
            adapter.validate_python(value)  # must not raise
        for value in negative:
            assert not _accepts(validator, value), (fragment, value)
            with pytest.raises(ValidationError):
                adapter.validate_python(value)


def test_rfc3339_checker_is_local_and_shared() -> None:
    """The local checker shares the authoring type's rule without global state."""
    from hermes_pipeline.contracts.formats import is_rfc3339_datetime

    default_handlers = dict(Draft202012Validator.FORMAT_CHECKER.checkers)
    checker = build_format_checker()
    assert checker is not Draft202012Validator.FORMAT_CHECKER
    assert Draft202012Validator.FORMAT_CHECKER.checkers == default_handlers
    adapter = TypeAdapter(DEFINITION_TYPES["utcTimestamp"])
    for value in (
        "2026-08-06T00:00:00.000Z",
        "2026-08-06T09:30:00+08:00",
        "2026-08-06T23:59:60Z",
        "not-a-date",
        "2026-08-06T00:00:00",
        "2026-13-06T00:00:00Z",
        "2026-08-06T24:00:00Z",
        "2026-08-06T00:00:00+25:00",
    ):
        schema_accepts = True
        try:
            checker.check(value, "date-time")
        except Exception:
            schema_accepts = False
        model_accepts = True
        try:
            adapter.validate_python(value)
        except ValidationError:
            model_accepts = False
        assert schema_accepts == model_accepts, value
        assert schema_accepts == is_rfc3339_datetime(value), value


def test_utc_timestamp_strict_type_rejects_format_violations() -> None:
    """The strict authoring type enforces the RFC 3339 boundary with the same
    rule as the local Schema-side format checker."""
    adapter = TypeAdapter(DEFINITION_TYPES["utcTimestamp"])
    for value in (
        "not-a-date",
        "2026-08-06T00:00:00",
        "2026-08-06",
        "2026-13-06T00:00:00Z",
    ):
        with pytest.raises(ValidationError):
            adapter.validate_python(value)


def test_contract_imports_do_not_mutate_default_format_checker() -> None:
    """Import-time behavior is checked in a fresh process (revision 7)."""
    script = """
from jsonschema import Draft202012Validator

before = dict(Draft202012Validator.FORMAT_CHECKER.checkers)
import hermes_pipeline.contracts.formats  # noqa: F401
import hermes_pipeline.contracts.validate  # noqa: F401
after = Draft202012Validator.FORMAT_CHECKER.checkers

assert set(before) == set(after)
assert all(before[name] is after[name] for name in before)
"""
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
