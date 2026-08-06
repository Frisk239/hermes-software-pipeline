"""Runtime contract authoring models (``schemas/runtime/*.json``).

Six root contracts governing the installed production Pipeline. Every model
config sets ``extra="forbid"`` and ``strict=True`` so model acceptance cannot
widen the committed JSON Schema contracts.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from .definitions import (
    ArtifactReferenceRef,
    FixedV1Integer,
    GitShaRef,
    IntegralInt,
    Sha256Ref,
    UtcTimestampRef,
    unique_values,
)

_STRICT_CONFIG = ConfigDict(extra="forbid", strict=True)


class Producer(BaseModel):
    """Stage attempt / execution run producer identity."""

    model_config = _STRICT_CONFIG

    stage_attempt_id: Annotated[str, Field(pattern=r"^att_[A-Za-z0-9_-]+$")]
    execution_run_id: Annotated[str, Field(pattern=r"^run_[A-Za-z0-9_-]+$")]
    lease_generation: Annotated[IntegralInt, Field(ge=1)]


class ArtifactSourceIdentity(BaseModel):
    """Optional source SHAs of an Artifact Manifest."""

    model_config = _STRICT_CONFIG

    planning_base_sha: GitShaRef = Field(default_factory=lambda: GitShaRef(""))
    candidate_sha: GitShaRef = Field(default_factory=lambda: GitShaRef(""))
    integration_base_sha: GitShaRef = Field(default_factory=lambda: GitShaRef(""))
    integration_candidate_sha: GitShaRef = Field(default_factory=lambda: GitShaRef(""))


class Provenance(BaseModel):
    """Workflow and runtime provenance of an Artifact Manifest."""

    model_config = _STRICT_CONFIG

    workflow_version: str
    runtime_version: str
    capability_profile_hash: Sha256Ref
    tool: str = Field(default_factory=lambda: "")
    tool_version: str = Field(default_factory=lambda: "")
    model: str = Field(default_factory=lambda: "")


class Filesystem(BaseModel):
    """Read/write roots of a Stage Capability Profile."""

    model_config = _STRICT_CONFIG

    read_roots: list[str]
    write_roots: list[str]


class Network(BaseModel):
    """Network mode and allow list of a Stage Capability Profile."""

    model_config = _STRICT_CONFIG

    mode: Literal["DENY_ALL", "ALLOW_LIST"]
    allow: list[str]


class Resources(BaseModel):
    """Resource bounds of a Stage Capability Profile."""

    model_config = _STRICT_CONFIG

    wall_time_ms: Annotated[IntegralInt, Field(ge=1000)]
    output_bytes: Annotated[IntegralInt, Field(ge=1024)]
    processes: Annotated[IntegralInt, Field(ge=1)]


class Actor(BaseModel):
    """Command actor identity."""

    model_config = _STRICT_CONFIG

    principal_id: str
    provider: Literal["CLI", "FEISHU", "SYSTEM", "GITHUB"]
    provider_actor_id: str


class CommandError(BaseModel):
    """Structured error of a Command Receipt."""

    model_config = _STRICT_CONFIG

    code: Literal[
        "VALIDATION_ERROR",
        "AUTHENTICATION_FAILED",
        "AUTHORIZATION_DENIED",
        "NOT_FOUND",
        "CONFLICT",
        "POLICY_REJECTED",
        "LEASE_STALE",
        "DEPENDENCY_UNAVAILABLE",
        "RATE_LIMITED",
        "INTERNAL_ERROR",
    ]
    message: str
    retryable: bool
    field_violations: list[str] = Field(default_factory=list)


class EvidenceSourceIdentity(BaseModel):
    """Source SHAs of an Evidence Bundle; at least one must be present."""

    model_config = _STRICT_CONFIG

    planning_base_sha: GitShaRef = Field(default_factory=lambda: GitShaRef(""))
    candidate_sha: GitShaRef = Field(default_factory=lambda: GitShaRef(""))
    integration_candidate_sha: GitShaRef = Field(default_factory=lambda: GitShaRef(""))

    @model_validator(mode="after")
    def _at_least_one_sha(self) -> EvidenceSourceIdentity:
        """JSON Schema ``minProperties: 1`` boundary."""
        if not self.model_fields_set:
            raise ValueError("source_identity requires at least one SHA")
        return self


# Root contracts -----------------------------------------------------------


class ArtifactManifest(BaseModel):
    """``runtime/artifact-manifest/v1`` — Artifact Manifest."""

    model_config = ConfigDict(extra="forbid", strict=True, title="Artifact Manifest")

    schema_id: Literal[
        "https://schemas.hermes-pipeline.dev/runtime/artifact-manifest/v1"
    ]
    schema_version: FixedV1Integer
    artifact_id: Annotated[str, Field(pattern=r"^art_[A-Za-z0-9_-]+$")]
    logical_role: Annotated[str, Field(min_length=1)]
    media_type: Annotated[str, Field(min_length=3)]
    byte_size: Annotated[IntegralInt, Field(ge=0)]
    content_digest: Sha256Ref
    document_schema_id: Annotated[
        str, Field(json_schema_extra={"format": "uri"}, default_factory=lambda: "")
    ]
    document_schema_version: Annotated[
        IntegralInt, Field(ge=1, default_factory=lambda: 1)
    ]
    producer: Producer
    source_identity: ArtifactSourceIdentity
    provenance: Provenance
    sensitivity: Literal["PUBLIC", "PROJECT", "RESTRICTED", "SECRET_DERIVED"]
    retention_class: Literal["EPHEMERAL", "PIPELINE", "AUDIT", "LEGAL_HOLD"]
    created_at: UtcTimestampRef
    manifest_digest: Sha256Ref


class CapabilityProfile(BaseModel):
    """``runtime/capability-profile/v1`` — Stage Capability Profile."""

    model_config = ConfigDict(
        extra="forbid", strict=True, title="Stage Capability Profile"
    )

    schema_id: Literal[
        "https://schemas.hermes-pipeline.dev/runtime/capability-profile/v1"
    ]
    schema_version: FixedV1Integer
    profile_id: Annotated[str, Field(pattern=r"^cap_[A-Za-z0-9_-]+$")]
    profile_revision: Annotated[IntegralInt, Field(ge=1)]
    stage_type: Literal["PRD", "ARCHITECTURE", "DEVELOPMENT", "E2E", "ACCEPTANCE"]
    filesystem: Filesystem
    executables: Annotated[
        list[str],
        AfterValidator(unique_values),
        Field(json_schema_extra={"uniqueItems": True}),
    ]
    network: Network
    secrets: Annotated[
        list[str],
        AfterValidator(unique_values),
        Field(json_schema_extra={"uniqueItems": True}),
    ]
    browser: Literal["NONE", "CHROME_DEVTOOLS_MCP"]
    resources: Resources
    side_effects: Annotated[
        list[Literal["NONE", "LOCAL_BUILD", "LOCAL_TEST", "BROWSER_TEST"]],
        AfterValidator(unique_values),
        Field(json_schema_extra={"uniqueItems": True}),
    ]
    content_hash: Sha256Ref


class CommandReceipt(BaseModel):
    """``runtime/command-receipt/v1`` — Command Receipt."""

    model_config = ConfigDict(extra="forbid", strict=True, title="Command Receipt")

    schema_id: Literal["https://schemas.hermes-pipeline.dev/runtime/command-receipt/v1"]
    schema_version: FixedV1Integer
    command_id: str
    status: Literal["ACCEPTED", "REJECTED", "CONFLICT", "DEDUPLICATED"]
    pipeline_id: str
    observed_revision: Annotated[IntegralInt, Field(ge=0)]
    event_ids: list[str] = Field(default_factory=list)
    error: CommandError = Field(
        default_factory=lambda: CommandError(
            code="INTERNAL_ERROR", message="", retryable=False
        )
    )
    recorded_at: UtcTimestampRef
    correlation_id: str


class ControllerCommand(BaseModel):
    """``runtime/controller-command/v1`` — Controller Command."""

    model_config = ConfigDict(extra="forbid", strict=True, title="Controller Command")

    schema_id: Literal[
        "https://schemas.hermes-pipeline.dev/runtime/controller-command/v1"
    ]
    schema_version: FixedV1Integer
    command_id: Annotated[str, Field(pattern=r"^cmd_[A-Za-z0-9_-]+$")]
    idempotency_key: Annotated[str, Field(min_length=16, max_length=160)]
    workspace_id: Annotated[str, Field(pattern=r"^ws_[A-Za-z0-9_-]+$")]
    project_id: Annotated[str, Field(pattern=r"^prj_[A-Za-z0-9_-]+$")]
    pipeline_id: Annotated[str, Field(pattern=r"^pl_[A-Za-z0-9_-]+$")]
    expected_revision: Annotated[IntegralInt, Field(ge=0)]
    actor: Actor
    ingress: Literal["CLI", "HERMES_FEISHU", "SYSTEM_RECONCILER", "GITHUB_RECONCILER"]
    command_type: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]+$")]
    payload: dict[str, Any]
    correlation_id: str
    causation_id: str = Field(default_factory=lambda: "")
    submitted_at: UtcTimestampRef


class EvidenceBundle(BaseModel):
    """``runtime/evidence-bundle/v1`` — Evidence Bundle."""

    model_config = ConfigDict(extra="forbid", strict=True, title="Evidence Bundle")

    schema_id: Literal["https://schemas.hermes-pipeline.dev/runtime/evidence-bundle/v1"]
    schema_version: FixedV1Integer
    bundle_id: Annotated[str, Field(pattern=r"^evb_[A-Za-z0-9_-]+$")]
    pipeline_id: Annotated[str, Field(pattern=r"^pl_[A-Za-z0-9_-]+$")]
    stage_attempt_id: Annotated[str, Field(pattern=r"^att_[A-Za-z0-9_-]+$")]
    execution_run_id: Annotated[str, Field(pattern=r"^run_[A-Za-z0-9_-]+$")]
    lease_generation: Annotated[IntegralInt, Field(ge=1)]
    source_identity: Annotated[
        EvidenceSourceIdentity, Field(json_schema_extra={"minProperties": 1})
    ]
    contract_revision: Annotated[IntegralInt, Field(ge=1)]
    artifacts: Annotated[list[ArtifactReferenceRef], Field(min_length=1)]
    created_at: UtcTimestampRef
    bundle_digest: Sha256Ref


class PipelineEvent(BaseModel):
    """``runtime/pipeline-event/v1`` — Pipeline Event."""

    model_config = ConfigDict(extra="forbid", strict=True, title="Pipeline Event")

    schema_id: Literal["https://schemas.hermes-pipeline.dev/runtime/pipeline-event/v1"]
    schema_version: FixedV1Integer
    event_id: Annotated[str, Field(pattern=r"^evt_[A-Za-z0-9_-]+$")]
    workspace_id: str
    project_id: str
    pipeline_id: str
    pipeline_revision: Annotated[IntegralInt, Field(ge=1)]
    event_type: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]+$")]
    event_schema_version: Annotated[IntegralInt, Field(ge=1)]
    actor_id: str
    authorization_decision_id: str
    command_id: str
    correlation_id: str
    causation_id: str = Field(default_factory=lambda: "")
    payload: dict[str, Any]
    occurred_at: UtcTimestampRef
    recorded_at: UtcTimestampRef
    previous_event_hash: Sha256Ref | None
    event_hash: Sha256Ref


# The runtime contract models in committed registry order.
RUNTIME_MODELS: dict[str, type[BaseModel]] = {
    "runtime/artifact-manifest": ArtifactManifest,
    "runtime/capability-profile": CapabilityProfile,
    "runtime/command-receipt": CommandReceipt,
    "runtime/controller-command": ControllerCommand,
    "runtime/evidence-bundle": EvidenceBundle,
    "runtime/pipeline-event": PipelineEvent,
}

__all__ = [
    "RUNTIME_MODELS",
    "ArtifactManifest",
    "CapabilityProfile",
    "CommandReceipt",
    "ControllerCommand",
    "EvidenceBundle",
    "PipelineEvent",
]
