"""Corpus three-way agreement, round-trip, and canary-leak tests (AC-04/05).

Every corpus entry is validated by the immutable f36 snapshot, the strict
authoring model, and the generated Schema; results must agree with the
recorded expectation. Positive entries additionally round-trip through
Model validate, JSON dump, then Model and Schema revalidate. Secret canaries
never appear in any reported output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource

from hermes_pipeline.contracts.corpus import (
    BASE_CATEGORIES,
    EXPECTED_PASS,
    CorpusEntry,
    EntryResult,
    load_corpus,
    validate_entry,
)
from hermes_pipeline.contracts.formats import build_format_checker
from hermes_pipeline.contracts.registry import CONTRACTS, contract_by_id
from hermes_pipeline.contracts.validate import run_contracts_check

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "contracts"


def _schema_accepts(validator: Any, document: object) -> bool:
    # pyright's bundled jsonschema stub types is_valid via a recursive
    # _JsonParameter alias it cannot resolve in strict mode.
    return bool(validator.is_valid(document))


def _registry() -> Registry[Any]:
    registry: Registry[Any] = Registry()
    for contract in CONTRACTS:
        document = json.loads(
            (REPO_ROOT / contract.relative_path).read_text(encoding="utf-8")
        )
        registry = registry.with_resource(
            contract.schema_id, Resource.from_contents(document)
        )
    return registry


def _snapshot_registry() -> Registry[Any]:
    """Baseline $ref registry built only from the 14 f36 snapshot files
    (revision 6: the baseline authority never resolves through the current
    generated registry)."""
    registry: Registry[Any] = Registry()
    for contract in CONTRACTS:
        snapshot = json.loads(
            (
                FIXTURES
                / "snapshots"
                / Path(contract.relative_path).relative_to("schemas")
            ).read_text(encoding="utf-8")
        )
        registry = registry.with_resource(
            snapshot["$id"], Resource.from_contents(snapshot)
        )
    return registry


def _validator(
    document: dict[str, Any], registry: Registry[Any] | None = None
) -> Draft202012Validator:
    return Draft202012Validator(
        document,
        format_checker=build_format_checker(),
        registry=_registry() if registry is None else registry,
    )


def _corpus_entries() -> list[CorpusEntry]:
    return load_corpus(FIXTURES)


def test_corpus_covers_every_category_per_root_contract() -> None:
    per_id: dict[str, set[str]] = {}
    for entry in _corpus_entries():
        per_id.setdefault(entry.schema_id, set()).add(entry.category)
    instantiable = [c for c in CONTRACTS if c.model is not None]
    assert len(instantiable) == 13
    for contract in instantiable:
        categories = per_id[contract.schema_id]
        assert set(BASE_CATEGORIES) <= categories, contract.schema_id


@pytest.mark.parametrize(
    ("schema_id", "category", "expected"),
    [
        ("https://schemas.hermes-pipeline.dev/unknown/example/v1", "minimal", "pass"),
        (
            "https://schemas.hermes-pipeline.dev/engineering/closeout/v1",
            "unknown",
            "pass",
        ),
        (
            "https://schemas.hermes-pipeline.dev/engineering/closeout/v1",
            "minimal",
            "PASS",
        ),
    ],
)
def test_corpus_loader_rejects_unknown_metadata(
    tmp_path: Path, schema_id: str, category: str, expected: str
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "broken.json").write_text(
        json.dumps(
            {
                "schema_id": schema_id,
                "entries": [
                    {
                        "name": "minimal",
                        "category": category,
                        "expected": expected,
                        "document": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_corpus(tmp_path)


def test_every_entry_agrees_three_way_with_expectation() -> None:
    results: list[EntryResult] = []
    for contract in CONTRACTS:
        if contract.model is None:
            continue
        snapshot = json.loads(
            (
                FIXTURES
                / "snapshots"
                / Path(contract.relative_path).relative_to("schemas")
            ).read_text(encoding="utf-8")
        )
        generated = json.loads(
            (REPO_ROOT / contract.relative_path).read_text(encoding="utf-8")
        )
        baseline = _validator(snapshot, _snapshot_registry())
        schema = _validator(generated)
        for entry in [
            e for e in _corpus_entries() if e.schema_id == contract.schema_id
        ]:
            results.append(validate_entry(entry, contract.model, baseline, schema))
    assert results
    for result in results:
        expected = result.entry.expected == EXPECTED_PASS
        assert result.baseline_pass == expected, result.entry.name
        assert result.model_pass == expected, result.entry.name
        assert result.generated_pass == expected, result.entry.name
        assert result.baseline_pass == result.model_pass == result.generated_pass
        if expected:
            assert result.round_trip_ok, result.entry.name


def test_positive_entries_round_trip_through_model_and_schema() -> None:
    for contract in CONTRACTS:
        if contract.model is None:
            continue
        snapshot = json.loads(
            (
                FIXTURES
                / "snapshots"
                / Path(contract.relative_path).relative_to("schemas")
            ).read_text(encoding="utf-8")
        )
        generated = json.loads(
            (REPO_ROOT / contract.relative_path).read_text(encoding="utf-8")
        )
        baseline = _validator(snapshot, _snapshot_registry())
        schema = _validator(generated)
        for entry in [
            e for e in _corpus_entries() if e.schema_id == contract.schema_id
        ]:
            if entry.expected != EXPECTED_PASS:
                continue
            instance = contract.model.model_validate(entry.document)
            dumped = instance.model_dump(mode="json", exclude_unset=True)
            # Model revalidate
            contract.model.model_validate(dumped)
            # Schema revalidate (generated and baseline snapshot)
            assert _schema_accepts(schema, dumped), (contract.schema_id, entry.name)
            assert _schema_accepts(baseline, dumped), (contract.schema_id, entry.name)


def test_invalid_entries_rejected_by_model_and_schema() -> None:
    for contract in CONTRACTS:
        if contract.model is None:
            continue
        generated = json.loads(
            (REPO_ROOT / contract.relative_path).read_text(encoding="utf-8")
        )
        schema = _validator(generated)
        for entry in [
            e for e in _corpus_entries() if e.schema_id == contract.schema_id
        ]:
            if entry.expected == EXPECTED_PASS:
                continue
            assert not _schema_accepts(schema, entry.document), (
                contract.schema_id,
                entry.name,
            )
            try:
                contract.model.model_validate(entry.document)
            except ValidationError:
                pass
            else:
                raise AssertionError(
                    f"model accepted invalid entry {contract.schema_id}:{entry.name}"
                )


def test_baseline_authority_uses_a_snapshot_only_registry() -> None:
    """The baseline registry is built only from the 14 f36 snapshot files;
    every baseline $ref must resolve through the snapshot contents, never
    through the current generated Schemas (revision 6)."""
    from hermes_pipeline.contracts.validate import Reporter, build_snapshot_registry

    snapshot_dir = FIXTURES / "snapshots"
    report = Reporter()
    registry = build_snapshot_registry(snapshot_dir, report)
    assert not report.has_issues, report.render()
    for contract in CONTRACTS:
        resource = registry.get_or_retrieve(contract.schema_id).value
        snapshot = json.loads(
            (
                snapshot_dir / Path(contract.relative_path).relative_to("schemas")
            ).read_text(encoding="utf-8")
        )
        assert resource.contents == snapshot, contract.schema_id


def test_canaries_never_leak_into_check_output() -> None:
    canaries: set[str] = set()
    import re

    for path in sorted((FIXTURES / "corpus").glob("*.json")):
        canaries.update(
            re.findall(r"canary_[A-Za-z0-9_-]+", path.read_text(encoding="utf-8"))
        )
    assert canaries
    ok, output = run_contracts_check(REPO_ROOT)
    assert ok
    for canary in canaries:
        assert canary not in output, f"canary leaked: {canary}"


def test_canary_entries_are_rejected() -> None:
    for entry in _corpus_entries():
        if entry.category == "canary":
            assert entry.expected == "reject", entry.name


def test_every_entry_has_a_content_hash_when_required() -> None:
    for entry in _corpus_entries():
        contract = contract_by_id(entry.schema_id)
        assert contract is not None
        schema = json.loads(
            (REPO_ROOT / contract.relative_path).read_text(encoding="utf-8")
        )
        if "content_hash" in schema.get("required", []):
            assert "content_hash" in entry.document, entry.name


def test_schema_version_fixed_v1_boundary_agrees_three_way() -> None:
    """Every root contract's schema_version is ``const: 1``: 1 and the finite
    integral JSON number 1.0 pass, while booleans, strings, and non-integral
    numbers are rejected by the f36 snapshot, the Pydantic model, and the
    generated Schema alike (REWORK #2)."""
    from hermes_pipeline.contracts.jcs import content_hash

    cases = ((1, True), (1.0, True), (True, False), ("1", False), (1.5, False))
    instantiable = [c for c in CONTRACTS if c.model is not None]
    assert len(instantiable) == 13
    for contract in instantiable:
        model = contract.model
        assert model is not None
        snapshot = json.loads(
            (
                FIXTURES
                / "snapshots"
                / Path(contract.relative_path).relative_to("schemas")
            ).read_text(encoding="utf-8")
        )
        generated = json.loads(
            (REPO_ROOT / contract.relative_path).read_text(encoding="utf-8")
        )
        baseline = _validator(snapshot, _snapshot_registry())
        schema = _validator(generated)
        entry = next(
            e
            for e in _corpus_entries()
            if e.schema_id == contract.schema_id and e.name == "minimal"
        )
        for value, expected in cases:
            doc = dict(entry.document)
            doc["schema_version"] = value
            if "content_hash" in doc:
                doc["content_hash"] = content_hash(doc)
            baseline_pass = _schema_accepts(baseline, doc)
            generated_pass = _schema_accepts(schema, doc)
            model_pass = True
            try:
                model.model_validate(doc)
            except ValidationError:
                model_pass = False
            assert baseline_pass == expected, (contract.schema_id, value)
            assert generated_pass == expected, (contract.schema_id, value)
            assert model_pass == expected, (contract.schema_id, value)
            assert baseline_pass == generated_pass == model_pass


def test_fact_value_integral_boundary_matches_draft_2020_12() -> None:
    """Fact.value accepts finite integral JSON numbers such as 3.0 and never
    coerces strings or booleans into the integer branch (revision 6)."""
    from pydantic import TypeAdapter

    from hermes_pipeline.contracts.engineering import Fact

    adapter = TypeAdapter(Fact)
    integral = adapter.validate_python({"name": "n", "value": 3.0, "source": "s"})
    assert integral.value == 3 and isinstance(integral.value, int)
    # Strings and booleans stay in their own union branch: no numeric
    # coercion of "3" into 3 or true into 1.
    assert (
        adapter.validate_python({"name": "n", "value": "3", "source": "s"}).value == "3"
    )
    assert (
        adapter.validate_python({"name": "n", "value": True, "source": "s"}).value
        is True
    )
    # Non-integral numbers are rejected on all three authorities.
    with pytest.raises(ValidationError):
        adapter.validate_python({"name": "n", "value": 3.5, "source": "s"})
