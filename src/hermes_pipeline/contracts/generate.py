"""Deterministic generation of the committed contract projections.

``contracts generate`` is the only command that writes the generated
artifacts: the 14 Schema documents under ``schemas/``, the OpenAPI document
at ``contracts/openapi.json``, and the compatibility registry at
``contracts/compatibility-registry.json``. Generation is pure: it takes the
authoring models and the repository root, and its output is order-stable,
LF/UTF-8, with no timestamp, path, or environment input.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, TypeAdapter

from ._generator import NoResolveSchemaGenerator
from .definitions import DEFINITION_TYPES, DEFINITIONS_ID, DEFINITIONS_ORDER
from .registry import CONTRACTS, DRAFT_2020_12, ContractDef
from .serialize import inline_local_defs, normalize_schema, render_json


def model_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The raw Pydantic projection of one authoring model."""
    return model.model_json_schema(schema_generator=NoResolveSchemaGenerator)


def definition_schema(name: str) -> dict[str, Any]:
    """The raw Pydantic projection of one ``common/definitions`` $def."""
    typ = DEFINITION_TYPES[name]
    return TypeAdapter(typ).json_schema(schema_generator=NoResolveSchemaGenerator)


def generate_definitions_document() -> dict[str, Any]:
    """The committed ``schemas/common/definitions.schema.json`` document."""
    defs: dict[str, Any] = {}
    for name in DEFINITIONS_ORDER:
        defs[name] = normalize_schema(definition_schema(name))
    return {
        "$schema": DRAFT_2020_12,
        "$id": DEFINITIONS_ID,
        "title": "Hermes Pipeline Common Definitions",
        "$defs": defs,
    }


def generate_contract_document(contract: ContractDef) -> dict[str, Any]:
    """One committed Schema document generated from its authoring model."""
    if contract.model is None:
        return generate_definitions_document()
    raw = model_schema(contract.model)
    inline = inline_local_defs(raw, raw.get("$defs", {}))
    normalized = normalize_schema(inline, root=True)
    return {
        "$schema": DRAFT_2020_12,
        "$id": contract.schema_id,
        **{key: value for key, value in normalized.items() if key != "$id"},
    }


def generate_schema_files() -> dict[Path, str]:
    """Map of repository-relative path -> rendered Schema bytes for all 14."""
    files: dict[Path, str] = {}
    for contract in CONTRACTS:
        files[Path(contract.relative_path)] = render_json(
            generate_contract_document(contract)
        )
    return files


def generate_openapi_document(version: str) -> dict[str, Any]:
    """The committed ``contracts/openapi.json`` document (AC-07)."""
    components: dict[str, Any] = {}
    for contract in CONTRACTS:
        components[contract.component_key] = generate_contract_document(contract)
    return {
        "openapi": "3.1.0",
        "jsonSchemaDialect": DRAFT_2020_12,
        "info": {
            "title": "Hermes Pipeline Contract Catalog",
            "version": version,
        },
        "paths": {},
        "components": {"schemas": components},
    }


def generate_compatibility_registry() -> dict[str, Any]:
    """The committed ``contracts/compatibility-registry.json`` document."""
    registry: dict[str, Any] = {}
    for contract in CONTRACTS:
        registry[contract.schema_id] = {
            "current_version": contract.version,
            "supported_versions": [contract.version],
        }
    return {schema_id: registry[schema_id] for schema_id in sorted(registry)}


def generated_artifacts(version: str) -> dict[Path, str]:
    """Every generated artifact: relative path -> rendered content."""
    files = generate_schema_files()
    files[Path("contracts/openapi.json")] = render_json(
        generate_openapi_document(version)
    )
    files[Path("contracts/compatibility-registry.json")] = render_json(
        generate_compatibility_registry()
    )
    return files


def write_generated(root: Path, version: str) -> list[Path]:
    """Write every generated artifact under root; returns changed paths."""
    changed: list[Path] = []
    for relative, content in generated_artifacts(version).items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != content.encode("utf-8"):
            target.write_bytes(content.encode("utf-8"))
            changed.append(relative)
    return changed


def load_json_document(path: Path) -> dict[str, Any]:
    """Parse one committed JSON document (strict UTF-8, JSON object)."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path}: not valid UTF-8 ({exc.reason})") from exc
    document = json.loads(text)
    if not isinstance(document, dict):
        raise ValueError(f"{path}: document is not a JSON object")
    return cast(dict[str, Any], document)
