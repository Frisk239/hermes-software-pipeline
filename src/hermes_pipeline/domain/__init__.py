"""domain Module skeleton (slice-00-02).

Pure domain values and deterministic rules. The Module boundary is
fixed by ``docs/architecture/system-and-module-design.md``; this
skeleton deliberately carries no business behavior. domain imports
only the Python standard library and contract value types.
"""

from datetime import datetime as datetime

from hermes_pipeline.domain.clock import Clock
from hermes_pipeline.domain.errors import (
    ACCEPTED,
    EMPTY_REQUIREMENT,
    INVALID_TRANSITION,
)
from hermes_pipeline.domain.pipeline import (
    ConfirmRequirement,
    PipelineResult,
    PipelineState,
    RejectRequirement,
    RequirementConfirmed,
    RequirementRejected,
    apply,
)

__all__ = [
    "ACCEPTED",
    "EMPTY_REQUIREMENT",
    "INVALID_TRANSITION",
    "Clock",
    "ConfirmRequirement",
    "PipelineResult",
    "PipelineState",
    "RejectRequirement",
    "RequirementConfirmed",
    "RequirementRejected",
    "apply",
]
