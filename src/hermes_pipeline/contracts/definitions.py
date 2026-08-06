"""Common $defs type library (``schemas/common/definitions.schema.json``).

Every committed Schema references these shared definitions by ``$ref``; the
authoring types below are their single source. Each definition carries its
exact committed JSON Schema projection and a strict validator so model
acceptance cannot widen the JSON Schema pass/reject boundary:

- ``utcTimestamp`` — RFC 3339 date-time string (``format: date-time``);
- ``gitSha`` — 40-hex or 64-hex commit SHA;
- ``sha256`` — ``sha256:<64 hex>`` content digest;
- ``relativePath`` — repository-relative path (no absolute root, no ``..``
  escape, no backslash);
- ``identity`` — ``<scope>_<name>`` identifier;
- ``schemaIdentity``, ``fileReference``, ``artifactReference``,
  ``engineeringRisk`` — object envelopes.

The library also declares the reference flavors used by the root contracts
(absolute ``$id`` fragment refs) and by the definitions document itself
(local ``#/$defs/...`` fragment refs).
"""

from __future__ import annotations

import re
from typing import Annotated, Any, ClassVar, Literal, cast

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
)
from pydantic_core import core_schema

from .formats import validate_rfc3339_datetime

# ---------------------------------------------------------------------------
# Shared constraint constants
# ---------------------------------------------------------------------------

UTC_TIMESTAMP_FORMAT = "date-time"
GIT_SHA_PATTERN = r"^[0-9a-f]{40}([0-9a-f]{24})?$"
SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
RELATIVE_PATH_PATTERN = r"^(?!/)(?![A-Za-z]:)(?!.*(?:^|/)\.\.(?:/|$))(?!.*\\).+$"
IDENTITY_PATTERN = r"^[a-z][a-z0-9_-]*_[A-Za-z0-9_-]+$"
ARTIFACT_ID_PATTERN = r"^art_[A-Za-z0-9_-]+$"
RISK_ID_PATTERN = r"^R-[0-9]{2,}$"

DEFINITIONS_ID = "https://schemas.hermes-pipeline.dev/common/definitions/v1"


def _finite_integral(value: object) -> int:
    """Draft 2020-12 ``type: integer`` semantics: a finite integral number.

    Accepts ``int`` values and finite integral JSON numbers such as ``3.0``;
    rejects strings, booleans, and non-integral or non-finite numbers, so the
    model boundary cannot diverge from the Schema boundary.
    """
    if isinstance(value, bool):
        raise ValueError("must be a finite integral JSON number")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise ValueError("must be a finite integral JSON number")


#: Integer authoring type accepting finite integral JSON numbers (revision 6).
IntegralInt = Annotated[int, BeforeValidator(_finite_integral)]


def _validate_fixed_v1(value: object) -> int:
    """``schema_version`` must be the integer ``1`` (``const: 1``).

    Accepts the ``int`` ``1`` and the finite integral JSON number ``1.0``;
    rejects booleans, strings, and non-integral numbers, matching the
    jsonschema ``const: 1`` boundary (REWORK #2). ``bool`` is rejected
    before the identity comparison because ``True == 1``.
    """
    if isinstance(value, bool):
        raise ValueError("schema_version must be the integer 1")
    if isinstance(value, int) and value == 1:
        return 1
    if isinstance(value, float) and value.is_integer() and int(value) == 1:
        return 1
    raise ValueError("schema_version must be the integer 1")


class FixedV1Integer(int):
    """The shared ``const: 1`` integer type of every root contract's
    ``schema_version`` field.

    The JSON projection stays ``{"const": 1}``; validation accepts ``1`` and
    ``1.0`` and rejects booleans, strings, and non-integral numbers, so the
    model boundary cannot diverge from the Schema boundary (REWORK #2).
    """

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: object, handler: Any
    ) -> dict[str, object]:
        return {"const": 1}

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[object], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(_validate_fixed_v1)


def _validate_utc_timestamp(value: str) -> str:
    return validate_rfc3339_datetime(value)


_RELATIVE_PATH_RE = re.compile(RELATIVE_PATH_PATTERN)


def _validate_relative_path(value: str) -> str:
    """Validate ``relativePath`` with the Python regex engine.

    The committed pattern uses look-around assertions that the Rust regex
    engine behind pydantic-core cannot compile, so validation runs through a
    Python validator while the JSON Schema projection keeps the exact
    committed pattern.
    """
    if _RELATIVE_PATH_RE.fullmatch(value) is None:
        raise ValueError("must be a repository-relative path")
    return value


def unique_values(items: list[Any]) -> list[Any]:
    """Enforce the ``uniqueItems`` boundary that pydantic v2 removed from
    ``Field`` (use ``json_schema_extra`` for the projection)."""
    seen: set[Any] = set()
    for item in items:
        if item in seen:
            raise ValueError("items must be unique")
        seen.add(item)
    return items


#: ``list[str]`` field that emits ``"uniqueItems": true`` and validates it.
UniqueStrings = Annotated[
    list[str],
    AfterValidator(unique_values),
    Field(json_schema_extra={"uniqueItems": True}),
]


# ---------------------------------------------------------------------------
# Scalar definition types (string shapes)
# ---------------------------------------------------------------------------


class UtcTimestamp(str):
    """``utcTimestamp`` definition: RFC 3339 date-time string."""

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: object, handler: Any
    ) -> dict[str, object]:
        return {"type": "string", "format": UTC_TIMESTAMP_FORMAT}

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[object], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            _validate_utc_timestamp, core_schema.str_schema(strict=True)
        )


class GitSha(str):
    """``gitSha`` definition: 40-hex or 64-hex commit SHA."""

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: object, handler: Any
    ) -> dict[str, object]:
        return {"type": "string", "pattern": GIT_SHA_PATTERN}

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[object], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.str_schema(strict=True, pattern=GIT_SHA_PATTERN)


class Sha256(str):
    """``sha256`` definition: ``sha256:<64 hex>`` digest."""

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: object, handler: Any
    ) -> dict[str, object]:
        return {"type": "string", "pattern": SHA256_PATTERN}

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[object], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.str_schema(strict=True, pattern=SHA256_PATTERN)


class RelativePath(str):
    """``relativePath`` definition: portable repository-relative path."""

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: object, handler: Any
    ) -> dict[str, object]:
        return {
            "type": "string",
            "minLength": 1,
            "maxLength": 512,
            "pattern": RELATIVE_PATH_PATTERN,
        }

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[object], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            _validate_relative_path,
            core_schema.str_schema(strict=True, min_length=1, max_length=512),
        )


class Identity(str):
    """``identity`` definition: ``<scope>_<name>`` identifier."""

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: object, handler: Any
    ) -> dict[str, object]:
        return {
            "type": "string",
            "minLength": 4,
            "maxLength": 128,
            "pattern": IDENTITY_PATTERN,
        }

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[object], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.str_schema(
            strict=True, min_length=4, max_length=128, pattern=IDENTITY_PATTERN
        )


# ---------------------------------------------------------------------------
# Reference flavors
# ---------------------------------------------------------------------------


class _Ref(str):
    """Base class for standalone ``$ref`` authoring types.

    The JSON projection is exactly ``{"$ref": <target>}``; validation is
    delegated to the target definition's own core schema so reference values
    keep the target boundary. The unregistered-reference pass-through is
    handled by ``_generator.NoResolveSchemaGenerator``.
    """

    _ref: ClassVar[str] = ""

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: object, handler: Any
    ) -> dict[str, object]:
        return {"$ref": cls._ref}


class UtcTimestampRef(_Ref):
    """Absolute reference to the ``utcTimestamp`` definition."""

    _ref = f"{DEFINITIONS_ID}#/$defs/utcTimestamp"

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[object], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            _validate_utc_timestamp, core_schema.str_schema(strict=True)
        )


class LocalUtcTimestampRef(UtcTimestampRef):
    """Local fragment reference to the ``utcTimestamp`` definition."""

    _ref = "#/$defs/utcTimestamp"


class GitShaRef(_Ref):
    """Absolute reference to the ``gitSha`` definition."""

    _ref = f"{DEFINITIONS_ID}#/$defs/gitSha"

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[object], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.str_schema(strict=True, pattern=GIT_SHA_PATTERN)


class LocalGitShaRef(GitShaRef):
    """Local fragment reference to the ``gitSha`` definition."""

    _ref = "#/$defs/gitSha"


class Sha256Ref(_Ref):
    """Absolute reference to the ``sha256`` definition."""

    _ref = f"{DEFINITIONS_ID}#/$defs/sha256"

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[object], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.str_schema(strict=True, pattern=SHA256_PATTERN)


class LocalSha256Ref(Sha256Ref):
    """Local fragment reference to the ``sha256`` definition."""

    _ref = "#/$defs/sha256"


class RelativePathRef(_Ref):
    """Absolute reference to the ``relativePath`` definition."""

    _ref = f"{DEFINITIONS_ID}#/$defs/relativePath"

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[object], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            _validate_relative_path,
            core_schema.str_schema(strict=True, min_length=1, max_length=512),
        )


class LocalRelativePathRef(RelativePathRef):
    """Local fragment reference to the ``relativePath`` definition."""

    _ref = "#/$defs/relativePath"


class ArtifactReferenceRef(_Ref):
    """Absolute reference to the ``artifactReference`` definition."""

    _ref = f"{DEFINITIONS_ID}#/$defs/artifactReference"

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[object], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            _validate_artifact_reference, _object_schema()
        )


class EngineeringRiskRef(_Ref):
    """Absolute reference to the ``engineeringRisk`` definition."""

    _ref = f"{DEFINITIONS_ID}#/$defs/engineeringRisk"

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[object], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            _validate_engineering_risk, _object_schema()
        )


def _object_schema() -> core_schema.CoreSchema:
    """A strict JSON-object core schema (validation happens in the model)."""
    return core_schema.dict_schema(
        core_schema.str_schema(strict=True),
        core_schema.any_schema(),
        strict=True,
    )


def _validate_artifact_reference(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("artifactReference must be an object")
    value = cast(dict[str, Any], value)
    ArtifactReference.model_validate(value)
    return value


def _validate_engineering_risk(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("engineeringRisk must be an object")
    value = cast(dict[str, Any], value)
    EngineeringRisk.model_validate(value)
    return value


# ---------------------------------------------------------------------------
# Object definition types
# ---------------------------------------------------------------------------

_STRICT_CONFIG = ConfigDict(extra="forbid", strict=True)


class SchemaIdentity(BaseModel):
    """``schemaIdentity`` definition."""

    model_config = _STRICT_CONFIG

    schema_id: Annotated[str, Field(json_schema_extra={"format": "uri"})]
    schema_version: Annotated[IntegralInt, Field(ge=1)]


class FileReference(BaseModel):
    """``fileReference`` definition."""

    model_config = _STRICT_CONFIG

    path: LocalRelativePathRef
    digest: LocalSha256Ref
    purpose: Annotated[str, Field(min_length=1, max_length=256)]


class ArtifactReference(BaseModel):
    """``artifactReference`` definition."""

    model_config = _STRICT_CONFIG

    artifact_id: Annotated[str, Field(pattern=ARTIFACT_ID_PATTERN)]
    manifest_digest: LocalSha256Ref
    role: Annotated[str, Field(min_length=1, max_length=128)]


class EngineeringRisk(BaseModel):
    """``engineeringRisk`` definition."""

    model_config = _STRICT_CONFIG

    risk_id: Annotated[str, Field(pattern=RISK_ID_PATTERN)]
    description: Annotated[str, Field(min_length=1)]
    impact: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    mitigation: Annotated[str, Field(min_length=1)]
    trigger: Annotated[str, Field(min_length=1)]


# ---------------------------------------------------------------------------
# Definitions document projection
# ---------------------------------------------------------------------------

# Committed $defs key order (schemas/common/definitions.schema.json).
DEFINITIONS_ORDER = (
    "utcTimestamp",
    "gitSha",
    "sha256",
    "relativePath",
    "identity",
    "schemaIdentity",
    "fileReference",
    "artifactReference",
    "engineeringRisk",
)

# The definition name -> authoring type mapping used by the generator.
DEFINITION_TYPES: dict[str, type[object]] = {
    "utcTimestamp": UtcTimestamp,
    "gitSha": GitSha,
    "sha256": Sha256,
    "relativePath": RelativePath,
    "identity": Identity,
    "schemaIdentity": SchemaIdentity,
    "fileReference": FileReference,
    "artifactReference": ArtifactReference,
    "engineeringRisk": EngineeringRisk,
}
