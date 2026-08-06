"""Baseline corpus loading and three-way semantic validation (AC-04/AC-05).

Every corpus entry lives under ``tests/fixtures/contracts/corpus/`` as
historical validation evidence. Each entry is validated by three independent
authorities that must agree with the recorded expectation:

1. the immutable f36 Schema snapshot (``tests/fixtures/contracts/snapshots/``);
2. the strict Pydantic authoring model;
3. the generated Schema (``schemas/``).

Positive entries additionally round-trip: Model validate, JSON dump, then
Model and Schema revalidate. Canary strings never appear in any reported
output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from .jcs import content_hash
from .registry import contract_by_id

# Corpus categories fixed by the Slice contract (AC-04); "integral" carries
# the revision-6 finite-integral-number parity cases.
CATEGORIES = ("minimal", "maximal", "integral", "invalid", "legacy", "canary")

# The categories every instantiable root contract must cover (AC-04).
BASE_CATEGORIES = ("minimal", "maximal", "invalid", "legacy", "canary")

# Corpus entries carry a "category" and an "expected" verdict.
EXPECTED_PASS = "pass"
EXPECTED_REJECT = "reject"


@dataclass(frozen=True)
class CorpusEntry:
    """One parsed corpus entry."""

    schema_id: str
    name: str
    category: str
    expected: str
    document: dict[str, Any]


@dataclass(frozen=True)
class EntryResult:
    """Three-way validation results for one entry."""

    entry: CorpusEntry
    baseline_pass: bool
    model_pass: bool
    generated_pass: bool
    round_trip_ok: bool
    hash_ok: bool


def load_corpus(fixture_root: Path) -> list[CorpusEntry]:
    """Parse every committed corpus file under the fixture root."""
    entries: list[CorpusEntry] = []
    corpus_dir = fixture_root / "corpus"
    if not corpus_dir.is_dir():
        return entries
    for path in sorted(corpus_dir.glob("*.json")):
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError(f"{path}: corpus file must be a JSON object")
        document = cast(dict[str, Any], parsed)
        if not isinstance(document.get("entries"), list):
            raise ValueError(f"{path}: corpus file must map schema_id to entries")
        schema_id = document.get("schema_id")
        if not isinstance(schema_id, str) or not schema_id:
            raise ValueError(f"{path}: corpus file has no schema_id")
        contract = contract_by_id(schema_id)
        if contract is None or contract.model is None:
            raise ValueError(
                f"{path}: corpus file must target a registered root contract"
            )
        for raw in document["entries"]:
            if not isinstance(raw, dict):
                raise ValueError(f"{path}: corpus entry must be an object")
            raw = cast(dict[str, Any], raw)
            name = raw.get("name")
            category = raw.get("category")
            expected = raw.get("expected")
            if not all(isinstance(v, str) for v in (name, category, expected)):
                raise ValueError(f"{path}: corpus entry metadata must be strings")
            payload = raw.get("document")
            if not isinstance(payload, dict):
                raise ValueError(f"{path}: corpus entry document must be an object")
            payload = cast(dict[str, Any], payload)
            name = cast(str, name)
            category = cast(str, category)
            expected = cast(str, expected)
            if not name:
                raise ValueError(f"{path}: corpus entry name must not be empty")
            if category not in CATEGORIES:
                raise ValueError(
                    f"{path}: corpus entry has unknown category {category!r}"
                )
            if expected not in (EXPECTED_PASS, EXPECTED_REJECT):
                raise ValueError(f"{path}: corpus entry has unknown expected value")
            entries.append(
                CorpusEntry(
                    schema_id=schema_id,
                    name=name,
                    category=category,
                    expected=expected,
                    document=payload,
                )
            )
    return entries


def _is_valid(validator: Any, document: dict[str, Any]) -> bool:
    # jsonschema's validator Protocol types is_valid via a recursive
    # _JsonParameter alias that pyright's bundled stub cannot fully resolve
    # in strict mode, so the validator is accepted as Any here.
    try:
        return bool(validator.is_valid(document))
    except Exception:
        return False


def _model_accepts(model: type[BaseModel], document: dict[str, Any]) -> bool:
    try:
        model.model_validate(document)
        return True
    except ValidationError:
        return False


def validate_entry(
    entry: CorpusEntry,
    model: type[BaseModel],
    baseline_validator: Draft202012Validator,
    generated_validator: Draft202012Validator,
) -> EntryResult:
    """Run the three-way gate plus round-trip and hash checks for one entry."""
    baseline_pass = _is_valid(baseline_validator, entry.document)
    model_pass = _model_accepts(model, entry.document)
    generated_pass = _is_valid(generated_validator, entry.document)

    round_trip_ok = True
    if entry.expected == EXPECTED_PASS and model_pass:
        try:
            instance = model.model_validate(entry.document)
            dumped = instance.model_dump(mode="json", exclude_unset=True)
            if not _model_accepts(model, dumped):
                round_trip_ok = False
            if not _is_valid(generated_validator, dumped):
                round_trip_ok = False
            if not _is_valid(baseline_validator, dumped):
                round_trip_ok = False
        except ValidationError:
            round_trip_ok = False

    hash_ok = True
    if "content_hash" in entry.document:
        try:
            hash_ok = content_hash(entry.document) == entry.document["content_hash"]
        except (TypeError, ValueError):
            hash_ok = False

    return EntryResult(
        entry=entry,
        baseline_pass=baseline_pass,
        model_pass=model_pass,
        generated_pass=generated_pass,
        round_trip_ok=round_trip_ok,
        hash_ok=hash_ok,
    )
