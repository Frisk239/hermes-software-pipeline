"""Contract generation, registry, OpenAPI, and validator tests (AC-01/03/07/08).

Asserts that the authoring models reproduce the committed projections
byte-for-byte, that the full validator passes, and that the OpenAPI
document and compatibility registry match their fixed shapes.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from jsonschema import Draft202012Validator

from hermes_pipeline.contracts.generate import (
    generate_compatibility_registry,
    generate_contract_document,
    generate_openapi_document,
    generate_schema_files,
    generated_artifacts,
)
from hermes_pipeline.contracts.jcs import canonical_json
from hermes_pipeline.contracts.registry import (
    COMPONENT_KEYS,
    CONTRACTS,
    EXPECTED_SCHEMA_IDS,
)
from hermes_pipeline.contracts.validate import run_contracts_check

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_generation_reproduces_every_committed_schema() -> None:
    for relative, content in generate_schema_files().items():
        committed = (REPO_ROOT / relative).read_bytes()
        assert content.encode("utf-8") == committed, (
            f"generated {relative} differs from the committed file"
        )


def test_generated_artifacts_are_stable_and_utf8_lf() -> None:
    first = generated_artifacts("0.1.0")
    second = generated_artifacts("0.1.0")
    assert first == second
    for relative, content in first.items():
        assert content.endswith("\n"), relative
        assert "\r" not in content, relative
        content.encode("utf-8")  # must be valid UTF-8


def test_canonical_projection_is_a_plain_deterministic_rendering() -> None:
    """The new canonical representation (revision 6) is a plain sorted-key,
    two-space-indent rendering — no f36-derived layout table is replicated
    and no generated file is required to equal the historical f36 bytes."""
    for relative, content in generate_schema_files().items():
        committed = (REPO_ROOT / relative).read_bytes()
        parsed = json.loads(committed)
        plain = json.dumps(parsed, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        assert content == plain, relative
        assert content.encode("utf-8") == committed, relative
        assert parsed.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        assert parsed.get("$id"), relative


def test_identity_lock_matches_bootstrap_set() -> None:
    declared = {
        json.loads((REPO_ROOT / contract.relative_path).read_text(encoding="utf-8"))[
            "$id"
        ]
        for contract in CONTRACTS
    }
    assert declared == EXPECTED_SCHEMA_IDS


def test_every_generated_schema_meta_validates() -> None:
    for contract in CONTRACTS:
        document = generate_contract_document(contract)
        Draft202012Validator.check_schema(document)


def test_snapshot_raw_digest_manifest_matches_bytes() -> None:
    """The f36 snapshots are immutable historical evidence of the /v1
    equivalence; their raw digests are bound by the committed manifest and
    they are never required to equal the new canonical projection bytes."""
    manifest = json.loads(
        (REPO_ROOT / "tests" / "fixtures" / "contracts" / "raw-digests.json").read_text(
            encoding="utf-8"
        )
    )
    from hermes_pipeline.contracts.jcs import raw_digest

    assert manifest["kind"] == "f36-schema-snapshot-raw-digests"
    assert manifest["base_sha"] == "f36ba6a2930267e2d90682ff61930c82fd1237bb"
    expected_paths = {
        "snapshots/" + Path(contract.relative_path).relative_to("schemas").as_posix()
        for contract in CONTRACTS
    }
    assert set(manifest["digests"]) == expected_paths
    for relative, expected in manifest["digests"].items():
        data = (REPO_ROOT / "tests" / "fixtures" / "contracts" / relative).read_bytes()
        assert raw_digest(data) == expected


def _validation_root(tmp_path: Path) -> Path:
    """Minimal copied checkout for public full-validator negative cases."""
    for relative in ("schemas", "contracts", "tests/fixtures/contracts"):
        shutil.copytree(REPO_ROOT / relative, tmp_path / relative)
    return tmp_path


def test_full_validator_rejects_an_incomplete_snapshot_digest_manifest(
    tmp_path: Path,
) -> None:
    root = _validation_root(tmp_path)
    (root / "tests" / "fixtures" / "contracts" / "raw-digests.json").write_text(
        json.dumps(
            {
                "kind": "f36-schema-snapshot-raw-digests",
                "base_sha": "f36ba6a2930267e2d90682ff61930c82fd1237bb",
                "digests": {},
            }
        ),
        encoding="utf-8",
    )
    ok, output = run_contracts_check(root)
    assert not ok
    assert "missing raw digest entries" in output


def test_full_validator_rejects_an_extra_snapshot_digest_entry(
    tmp_path: Path,
) -> None:
    root = _validation_root(tmp_path)
    manifest_path = root / "tests" / "fixtures" / "contracts" / "raw-digests.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["digests"]["snapshots/extra.schema.json"] = "sha256:" + "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    ok, output = run_contracts_check(root)
    assert not ok
    assert "unexpected raw digest entries" in output


def test_full_validator_rejects_a_tampered_snapshot_digest(
    tmp_path: Path,
) -> None:
    root = _validation_root(tmp_path)
    manifest_path = root / "tests" / "fixtures" / "contracts" / "raw-digests.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first = sorted(manifest["digests"])[0]
    manifest["digests"][first] = "sha256:" + "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    ok, output = run_contracts_check(root)
    assert not ok
    assert "raw digest mismatch" in output


def test_full_validator_rejects_wrong_manifest_kind_and_base_sha(
    tmp_path: Path,
) -> None:
    root = _validation_root(tmp_path)
    manifest_path = root / "tests" / "fixtures" / "contracts" / "raw-digests.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["kind"] = "something-else"
    manifest["base_sha"] = "0" * 40
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    ok, output = run_contracts_check(root)
    assert not ok
    assert "unexpected snapshot manifest kind" in output
    assert "snapshot base_sha must be f36ba6a" in output


def test_full_validator_rejects_non_draft_2020_12_declaration(
    tmp_path: Path,
) -> None:
    root = _validation_root(tmp_path)
    path = root / "schemas" / "engineering" / "closeout.schema.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["$schema"] = "https://json-schema.org/draft/2019-09/schema"
    path.write_text(json.dumps(document), encoding="utf-8")
    ok, output = run_contracts_check(root)
    assert not ok
    assert "$schema must be exactly Draft 2020-12" in output


def test_full_validator_rejects_missing_required_corpus_category(
    tmp_path: Path,
) -> None:
    root = _validation_root(tmp_path)
    path = (
        root
        / "tests"
        / "fixtures"
        / "contracts"
        / "corpus"
        / "engineering-closeout.json"
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    document["entries"] = [
        entry for entry in document["entries"] if entry["category"] != "canary"
    ]
    path.write_text(json.dumps(document), encoding="utf-8")
    ok, output = run_contracts_check(root)
    assert not ok
    assert "corpus missing required categories" in output


def test_full_validator_rejects_a_snapshot_with_an_unlocked_identity(
    tmp_path: Path,
) -> None:
    """A snapshot whose $id deviates from the locked identity fails even when
    its raw digest is kept consistent with the manifest."""
    from hermes_pipeline.contracts.jcs import raw_digest

    root = _validation_root(tmp_path)
    snapshot = (
        root
        / "tests"
        / "fixtures"
        / "contracts"
        / "snapshots"
        / "engineering"
        / "closeout.schema.json"
    )
    document = json.loads(snapshot.read_text(encoding="utf-8"))
    document["$id"] = document["$id"].replace("/v1", "/v2")
    snapshot.write_text(json.dumps(document), encoding="utf-8")
    manifest_path = root / "tests" / "fixtures" / "contracts" / "raw-digests.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["digests"]["snapshots/engineering/closeout.schema.json"] = raw_digest(
        snapshot.read_bytes()
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    ok, output = run_contracts_check(root)
    assert not ok
    assert "snapshot $id does not match its locked identity" in output


def test_full_validator_passes() -> None:
    ok, output = run_contracts_check(REPO_ROOT)
    assert ok, output


def test_openapi_fixed_shape_and_embedded_schemas() -> None:
    document = generate_openapi_document("0.1.0")
    assert document["openapi"] == "3.1.0"
    assert (
        document["jsonSchemaDialect"] == "https://json-schema.org/draft/2020-12/schema"
    )
    assert document["info"]["title"]
    assert document["info"]["version"]
    assert document["paths"] == {}
    assert set(document["components"]["schemas"]) == set(COMPONENT_KEYS)
    for contract in CONTRACTS:
        component = document["components"]["schemas"][contract.component_key]
        expected = generate_contract_document(contract)
        assert canonical_json(component) == canonical_json(expected)
        assert component["$id"] == contract.schema_id


def test_openapi_has_no_servers_security_or_operation_ids() -> None:
    document = json.loads(
        (REPO_ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8")
    )
    assert "servers" not in document
    assert "security" not in document
    assert "operationId" not in json.dumps(document)


def test_compatibility_registry_structure() -> None:
    registry = generate_compatibility_registry()
    assert set(registry) == EXPECTED_SCHEMA_IDS
    for entry in registry.values():
        current = entry["current_version"]
        supported = entry["supported_versions"]
        assert isinstance(current, int) and current >= 1
        assert supported and supported == sorted(supported)
        assert len(supported) == len(set(supported))
        assert supported[-1] == current


def test_full_validator_rejects_boolean_registry_versions(tmp_path: Path) -> None:
    root = _validation_root(tmp_path)
    registry = generate_compatibility_registry()
    schema_id = sorted(registry)[0]
    registry[schema_id] = {"current_version": True, "supported_versions": [True]}
    (root / "contracts" / "compatibility-registry.json").write_text(
        json.dumps(registry), encoding="utf-8"
    )

    ok, output = run_contracts_check(root)
    assert not ok
    assert "current_version must be an integer" in output


def test_registry_and_openapi_key_sets_match_identities() -> None:
    registry = json.loads(
        (REPO_ROOT / "contracts" / "compatibility-registry.json").read_text(
            encoding="utf-8"
        )
    )
    openapi = json.loads(
        (REPO_ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8")
    )
    assert set(registry) == EXPECTED_SCHEMA_IDS
    assert set(openapi["components"]["schemas"]) == set(COMPONENT_KEYS)
    for contract in CONTRACTS:
        assert contract.schema_id in registry
        assert contract.component_key in openapi["components"]["schemas"]
