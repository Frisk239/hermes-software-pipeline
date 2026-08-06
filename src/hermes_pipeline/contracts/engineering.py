"""Engineering contract authoring models (``schemas/engineering/*.json``).

Seven root contracts governing the repository's own Codex-planned,
Executor-implemented workflow. Every model config sets ``extra="forbid"``
and ``strict=True`` so model acceptance cannot widen the committed JSON
Schema contracts; conditional ``allOf`` semantics that JSON Schema expresses
imperatively are enforced by ``model_validator`` blocks.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, cast

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    model_validator,
)
from pydantic_core import core_schema

from .definitions import (
    DEFINITIONS_ID,
    ArtifactReferenceRef,
    EngineeringRiskRef,
    FileReference,
    FixedV1Integer,
    GitShaRef,
    IntegralInt,
    RelativePathRef,
    Sha256Ref,
    UtcTimestampRef,
    unique_values,
)

_STRICT_CONFIG = ConfigDict(extra="forbid", strict=True)

SLICE_ID_PATTERN = r"^slice-[0-9]{2,}-[0-9]{2,}$"
EC_PATTERN = r"^EC-[0-9]{2,}-[0-9]{2,}$"
ADR_PATTERN = r"^ADR-[0-9]{4}$"

# Shared item shapes -------------------------------------------------------


class FileReferenceRef(str):
    """Absolute reference to the ``fileReference`` definition."""

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: object, handler: Any
    ) -> dict[str, object]:
        return {"$ref": f"{DEFINITIONS_ID}#/$defs/fileReference"}

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[object], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            _validate_file_reference, _object_schema()
        )


def _object_schema() -> core_schema.CoreSchema:
    """A strict JSON-object core schema (validation happens in the model)."""
    return core_schema.dict_schema(
        core_schema.str_schema(strict=True),
        core_schema.any_schema(),
        strict=True,
    )


def _validate_file_reference(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("fileReference must be an object")
    value = cast(dict[str, Any], value)
    FileReference.model_validate(value)
    return value


class AllowedVerdicts(list[str]):
    """``{"const": ["PASS", "REWORK", "BLOCKED_CONTRACT"]}`` exact value."""

    ALLOWED = ("PASS", "REWORK", "BLOCKED_CONTRACT")

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: object, handler: Any
    ) -> dict[str, object]:
        return {"const": list(cls.ALLOWED)}

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[object], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            _validate_allowed_verdicts,
            core_schema.list_schema(core_schema.str_schema(strict=True), strict=True),
        )


def _validate_allowed_verdicts(value: list[str]) -> list[str]:
    if value != list(AllowedVerdicts.ALLOWED):
        raise ValueError("must equal the allowed verdicts constant")
    return value


class SliceItem(BaseModel):
    """One ``slices`` entry of a Phase Plan."""

    model_config = _STRICT_CONFIG

    slice_id: Annotated[str, Field(pattern=SLICE_ID_PATTERN)]
    title: Annotated[str, Field(min_length=1)]
    depends_on: Annotated[
        list[Annotated[str, Field(pattern=SLICE_ID_PATTERN)]],
        AfterValidator(unique_values),
        Field(json_schema_extra={"uniqueItems": True}),
    ]
    owns_exit_criteria: Annotated[
        list[Annotated[str, Field(pattern=EC_PATTERN)]],
        AfterValidator(unique_values),
        Field(json_schema_extra={"uniqueItems": True}),
    ]
    demonstration: Annotated[str, Field(min_length=1)]


class AcceptanceDimensions(BaseModel):
    """The five required acceptance dimensions of a Phase Plan."""

    model_config = _STRICT_CONFIG

    testing: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]
    migration: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]
    security: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]
    documentation: Annotated[
        list[Annotated[str, Field(min_length=1)]], Field(min_length=1)
    ]
    demonstration: Annotated[
        list[Annotated[str, Field(min_length=1)]], Field(min_length=1)
    ]


class ExitCriterion(BaseModel):
    """One ``exit_criteria`` entry of a Phase Plan."""

    model_config = _STRICT_CONFIG

    criterion_id: Annotated[str, Field(pattern=EC_PATTERN)]
    observable_result: Annotated[str, Field(min_length=1)]
    owner_slice_ids: Annotated[
        list[Annotated[str, Field(pattern=SLICE_ID_PATTERN)]],
        AfterValidator(unique_values),
        Field(min_length=1, json_schema_extra={"uniqueItems": True}),
    ]


class PhaseGate(BaseModel):
    """The immutable Phase Gate configuration."""

    model_config = _STRICT_CONFIG

    reviewer_role: Literal["CODEX_PLANNER_DESIGNER_REVIEWER"]
    required_evidence: Annotated[
        list[Annotated[str, Field(min_length=1)]],
        AfterValidator(unique_values),
        Field(min_length=1, json_schema_extra={"uniqueItems": True}),
    ]
    allowed_verdicts: AllowedVerdicts


class HumanApproval(BaseModel):
    """Human approval record inside a Phase Plan."""

    model_config = _STRICT_CONFIG

    required: bool
    status: Literal["NOT_REQUIRED", "PENDING", "APPROVED", "REJECTED"]
    attestation_id: str = Field(default_factory=lambda: "")


class CommandResult(BaseModel):
    """One ``command_results`` entry of an Execution Report."""

    model_config = _STRICT_CONFIG

    command_id: str
    exit_code: IntegralInt
    started_at: UtcTimestampRef
    duration_ms: Annotated[IntegralInt, Field(ge=0)]
    output_artifact: ArtifactReferenceRef


class Axes(BaseModel):
    """The four review axes of a Review Verdict."""

    model_config = _STRICT_CONFIG

    spec: Literal["PASS", "FAIL", "BLOCKED"]
    standards: Literal["PASS", "FAIL", "BLOCKED"]
    evidence: Literal["PASS", "FAIL", "BLOCKED"]
    scope_safety: Literal["PASS", "FAIL", "BLOCKED"]


class Finding(BaseModel):
    """One review finding."""

    model_config = _STRICT_CONFIG

    finding_id: Annotated[str, Field(pattern=r"^F-[0-9]{2,}$")]
    severity: Literal["BLOCKER", "MAJOR", "MINOR"]
    axis: Literal["SPEC", "STANDARDS", "EVIDENCE", "SCOPE_SAFETY"]
    evidence: Annotated[str, Field(min_length=1)]
    requirement_ref: Annotated[str, Field(min_length=1)]
    required_correction: Annotated[str, Field(min_length=1)]


class Implications(BaseModel):
    """The five implication categories of a Slice Contract."""

    model_config = _STRICT_CONFIG

    data: list[Annotated[str, Field(min_length=1)]]
    migration: list[Annotated[str, Field(min_length=1)]]
    compatibility: list[Annotated[str, Field(min_length=1)]]
    security: list[Annotated[str, Field(min_length=1)]]
    documentation: list[Annotated[str, Field(min_length=1)]]


class AcceptanceCriterion(BaseModel):
    """One ``acceptance_criteria`` entry of a Slice Contract."""

    model_config = _STRICT_CONFIG

    criterion_id: Annotated[str, Field(pattern=r"^AC-[0-9]{2,}$")]
    trace_ids: Annotated[
        list[Annotated[str, Field(min_length=1)]],
        AfterValidator(unique_values),
        Field(min_length=1, json_schema_extra={"uniqueItems": True}),
    ]
    observable_result: Annotated[str, Field(min_length=1)]
    verification_command_ids: Annotated[
        list[Annotated[str, Field(min_length=1)]],
        AfterValidator(unique_values),
        Field(min_length=1, json_schema_extra={"uniqueItems": True}),
    ]


class VerificationCommand(BaseModel):
    """One ``verification_commands`` entry of a Slice Contract."""

    model_config = _STRICT_CONFIG

    command_id: Annotated[str, Field(min_length=1)]
    argv: Annotated[list[str], Field(min_length=1)]
    working_directory: RelativePathRef
    timeout_ms: Annotated[IntegralInt, Field(ge=1000, le=3_600_000)]


class Fact(BaseModel):
    """One ``facts`` entry of a Context Manifest."""

    model_config = _STRICT_CONFIG

    name: str
    # JSON Schema ``integer`` accepts finite integral JSON numbers such as
    # ``3.0``; keep the authoring type on that same boundary (revision 6).
    value: str | IntegralInt | bool
    source: str


# Root contracts -----------------------------------------------------------


class Closeout(BaseModel):
    """``engineering/closeout/v1`` — Engineering Closeout."""

    model_config = ConfigDict(extra="forbid", strict=True, title="Engineering Closeout")

    schema_id: Literal["https://schemas.hermes-pipeline.dev/engineering/closeout/v1"]
    schema_version: FixedV1Integer
    closeout_id: Annotated[str, Field(pattern=r"^close_[A-Za-z0-9_-]+$")]
    scope_kind: Literal["SLICE", "PHASE"]
    scope_id: str
    base_sha: GitShaRef
    accepted_sha: GitShaRef
    delivered: Annotated[list[str], Field(min_length=1)]
    evidence: Annotated[list[ArtifactReferenceRef], Field(min_length=1)]
    residual_debt: list[str]
    next_prerequisites: list[str]
    closed_at: UtcTimestampRef
    content_hash: Sha256Ref


class ContextManifest(BaseModel):
    """``engineering/context-manifest/v1`` — Engineering Context Manifest."""

    model_config = ConfigDict(
        extra="forbid", strict=True, title="Engineering Context Manifest"
    )

    schema_id: Literal[
        "https://schemas.hermes-pipeline.dev/engineering/context-manifest/v1"
    ]
    schema_version: FixedV1Integer
    manifest_id: Annotated[str, Field(pattern=r"^ctx_[A-Za-z0-9_-]+$")]
    role: Literal["PLANNER", "EXECUTOR", "REVIEWER"]
    slice_id: str
    base_sha: GitShaRef
    assembled_at: UtcTimestampRef
    files: Annotated[list[FileReferenceRef], Field(min_length=1)]
    facts: list[Fact]
    content_hash: Sha256Ref


class ContractChangeRequest(BaseModel):
    """``engineering/contract-change-request/v1``."""

    model_config = ConfigDict(
        extra="forbid", strict=True, title="Engineering Contract Change Request"
    )

    schema_id: Literal[
        "https://schemas.hermes-pipeline.dev/engineering/contract-change-request/v1"
    ]
    schema_version: FixedV1Integer
    request_id: Annotated[str, Field(pattern=r"^ccr_[A-Za-z0-9_-]+$")]
    slice_id: str
    contract_revision: Annotated[IntegralInt, Field(ge=1)]
    base_sha: GitShaRef
    stop_condition: Annotated[str, Field(min_length=1)]
    evidence: Annotated[list[str], Field(min_length=1)]
    requested_decision: Annotated[str, Field(min_length=1)]
    scope_impact: Literal[
        "CLARIFICATION", "SCOPE_CHANGE", "INTERFACE_CHANGE", "ADR_CHANGE", "UNKNOWN"
    ]
    submitted_at: UtcTimestampRef
    content_hash: Sha256Ref


class ExecutionReport(BaseModel):
    """``engineering/execution-report/v1`` — Engineering Execution Report."""

    model_config = ConfigDict(
        extra="forbid", strict=True, title="Engineering Execution Report"
    )

    schema_id: Literal[
        "https://schemas.hermes-pipeline.dev/engineering/execution-report/v1"
    ]
    schema_version: FixedV1Integer
    report_id: Annotated[str, Field(pattern=r"^exec_[A-Za-z0-9_-]+$")]
    slice_id: str
    contract_revision: Annotated[IntegralInt, Field(ge=1)]
    attempt: Annotated[IntegralInt, Field(ge=1)]
    base_sha: GitShaRef
    candidate_sha: GitShaRef
    context_manifest_hash: Sha256Ref
    changed_paths: Annotated[
        list[RelativePathRef],
        AfterValidator(unique_values),
        Field(json_schema_extra={"uniqueItems": True}),
    ]
    command_results: list[CommandResult]
    artifact_refs: list[ArtifactReferenceRef]
    self_assessment: Literal["READY_FOR_REVIEW", "BLOCKED"]
    risks: list[str] = Field(default_factory=list)
    submitted_at: UtcTimestampRef
    content_hash: Sha256Ref


class PhasePlan(BaseModel):
    """``engineering/phase-plan/v1`` — Engineering Phase Plan."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        title="Engineering Phase Plan",
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {
                            "status": {
                                "enum": [
                                    "APPROVED",
                                    "EXECUTING",
                                    "REVIEWING",
                                    "COMPLETE",
                                ]
                            }
                        }
                    },
                    "then": {
                        "properties": {
                            "human_approval": {
                                "required": ["attestation_id"],
                                "properties": {
                                    "required": {"const": True},
                                    "status": {"const": "APPROVED"},
                                },
                            }
                        }
                    },
                }
            ]
        },
    )

    schema_id: Literal["https://schemas.hermes-pipeline.dev/engineering/phase-plan/v1"]
    schema_version: FixedV1Integer
    document_revision: Annotated[IntegralInt, Field(ge=1)]
    phase_id: Annotated[str, Field(pattern=r"^phase-[0-9]{2,}$")]
    title: Annotated[str, Field(min_length=1, max_length=160)]
    status: Literal[
        "DRAFT", "APPROVED", "EXECUTING", "REVIEWING", "COMPLETE", "BLOCKED"
    ]
    owner: Annotated[str, Field(min_length=1, max_length=128)]
    base_sha: GitShaRef
    outcome: Annotated[str, Field(min_length=1)]
    prerequisites: Annotated[
        list[Annotated[str, Field(min_length=1)]],
        AfterValidator(unique_values),
        Field(min_length=1, json_schema_extra={"uniqueItems": True}),
    ]
    accepted_adrs: Annotated[
        list[Annotated[str, Field(pattern=ADR_PATTERN)]],
        AfterValidator(unique_values),
        Field(json_schema_extra={"uniqueItems": True}),
    ]
    module_boundaries: Annotated[
        list[Annotated[str, Field(min_length=1)]],
        AfterValidator(unique_values),
        Field(min_length=1, json_schema_extra={"uniqueItems": True}),
    ]
    slices: Annotated[list[SliceItem], Field(min_length=1)]
    invariants: Annotated[
        list[Annotated[str, Field(min_length=1)]], Field(min_length=1)
    ]
    acceptance_dimensions: AcceptanceDimensions
    exit_criteria: Annotated[list[ExitCriterion], Field(min_length=1)]
    exclusions: list[str]
    risks: Annotated[list[EngineeringRiskRef], Field(min_length=1)]
    stop_conditions: Annotated[
        list[Annotated[str, Field(min_length=1)]], Field(min_length=1)
    ]
    phase_gate: PhaseGate
    human_approval: HumanApproval
    content_hash: Sha256Ref

    @model_validator(mode="after")
    def _approval_conditional(self) -> PhasePlan:
        """JSON Schema ``allOf``: approved/executing phases require attestation."""
        if self.status in ("APPROVED", "EXECUTING", "REVIEWING", "COMPLETE"):
            approval = self.human_approval
            if not approval.required or approval.status != "APPROVED":
                raise ValueError(
                    "human_approval must be required and APPROVED for an "
                    "approved/executing phase"
                )
            if "attestation_id" not in approval.model_fields_set:
                raise ValueError("human_approval.attestation_id is required")
        return self


class ReviewVerdict(BaseModel):
    """``engineering/review-verdict/v1`` — Engineering Review Verdict."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        title="Engineering Review Verdict",
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"verdict": {"const": "PASS"}}},
                    "then": {
                        "properties": {
                            "findings": {"maxItems": 0},
                            "axes": {
                                "properties": {
                                    "spec": {"const": "PASS"},
                                    "standards": {"const": "PASS"},
                                    "evidence": {"const": "PASS"},
                                    "scope_safety": {"const": "PASS"},
                                }
                            },
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "verdict": {"enum": ["REWORK", "BLOCKED_CONTRACT"]}
                        }
                    },
                    "then": {"properties": {"findings": {"minItems": 1}}},
                },
            ]
        },
    )

    schema_id: Literal[
        "https://schemas.hermes-pipeline.dev/engineering/review-verdict/v1"
    ]
    schema_version: FixedV1Integer
    verdict_id: Annotated[str, Field(pattern=r"^review_[A-Za-z0-9_-]+$")]
    slice_id: str
    contract_revision: Annotated[IntegralInt, Field(ge=1)]
    review_attempt: Annotated[IntegralInt, Field(ge=1)]
    base_sha: GitShaRef
    candidate_sha: GitShaRef
    context_manifest_hash: Sha256Ref
    evidence_bundle_hash: Sha256Ref
    verdict: Literal["PASS", "REWORK", "BLOCKED_CONTRACT"]
    axes: Axes
    findings: list[Finding]
    reviewed_at: UtcTimestampRef
    content_hash: Sha256Ref

    @model_validator(mode="after")
    def _verdict_conditionals(self) -> ReviewVerdict:
        """JSON Schema ``allOf``: PASS requires empty findings and all-PASS axes."""
        if self.verdict == "PASS":
            if self.findings:
                raise ValueError("a PASS verdict must have no findings")
            if any(
                value != "PASS"
                for value in (
                    self.axes.spec,
                    self.axes.standards,
                    self.axes.evidence,
                    self.axes.scope_safety,
                )
            ):
                raise ValueError("a PASS verdict requires every axis to be PASS")
        elif not self.findings:
            raise ValueError("REWORK and BLOCKED_CONTRACT verdicts require findings")
        return self


class SliceContract(BaseModel):
    """``engineering/slice-contract/v1`` — Engineering Slice Contract."""

    model_config = ConfigDict(
        extra="forbid", strict=True, title="Engineering Slice Contract"
    )

    schema_id: Literal[
        "https://schemas.hermes-pipeline.dev/engineering/slice-contract/v1"
    ]
    schema_version: FixedV1Integer
    document_revision: Annotated[IntegralInt, Field(ge=1)]
    slice_id: Annotated[str, Field(pattern=SLICE_ID_PATTERN)]
    phase_id: Annotated[str, Field(pattern=r"^phase-[0-9]{2,}$")]
    status: Literal[
        "DRAFT", "READY", "EXECUTING", "SUBMITTED", "ACCEPTED", "REWORK", "BLOCKED"
    ]
    predecessors: Annotated[
        list[Annotated[str, Field(pattern=SLICE_ID_PATTERN)]],
        AfterValidator(unique_values),
        Field(json_schema_extra={"uniqueItems": True}),
    ]
    base_sha: GitShaRef
    assigned_worktree: Annotated[str, Field(min_length=1, max_length=1024)]
    operator_path: Annotated[str, Field(min_length=1)]
    must_scope: Annotated[
        list[Annotated[str, Field(min_length=1)]], Field(min_length=1)
    ]
    out_of_scope: list[str]
    interfaces: list[Annotated[str, Field(min_length=1)]]
    binding_adrs: Annotated[
        list[Annotated[str, Field(pattern=ADR_PATTERN)]],
        AfterValidator(unique_values),
        Field(json_schema_extra={"uniqueItems": True}),
    ]
    permitted_paths: Annotated[list[str], Field(min_length=1)]
    prohibited_actions: Annotated[list[str], Field(min_length=1)]
    implications: Implications
    acceptance_criteria: Annotated[list[AcceptanceCriterion], Field(min_length=1)]
    required_tests: Annotated[
        list[Annotated[str, Field(min_length=1)]],
        AfterValidator(unique_values),
        Field(min_length=1, json_schema_extra={"uniqueItems": True}),
    ]
    demonstration: Annotated[str, Field(min_length=1)]
    verification_commands: Annotated[list[VerificationCommand], Field(min_length=1)]
    required_evidence: Annotated[
        list[str],
        AfterValidator(unique_values),
        Field(min_length=1, json_schema_extra={"uniqueItems": True}),
    ]
    risks: list[EngineeringRiskRef]
    retry_budget: Annotated[IntegralInt, Field(ge=0, le=10)]
    stop_conditions: Annotated[list[str], Field(min_length=1)]
    content_hash: Sha256Ref


# The engineering contract models in committed registry order.
ENGINEERING_MODELS: dict[str, type[BaseModel]] = {
    "engineering/closeout": Closeout,
    "engineering/context-manifest": ContextManifest,
    "engineering/contract-change-request": ContractChangeRequest,
    "engineering/execution-report": ExecutionReport,
    "engineering/phase-plan": PhasePlan,
    "engineering/review-verdict": ReviewVerdict,
    "engineering/slice-contract": SliceContract,
}

__all__ = [
    "ENGINEERING_MODELS",
    "Closeout",
    "ContextManifest",
    "ContractChangeRequest",
    "ExecutionReport",
    "PhasePlan",
    "ReviewVerdict",
    "SliceContract",
]
