"""Fake-Pipeline aggregate evaluator.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_PHASE_01
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from hermes_pipeline.domain.errors import (
    ACCEPTED,
    EMPTY_REQUIREMENT,
    INVALID_TRANSITION,
)


@dataclass(frozen=True)
class PipelineState:
    status: Literal["UNCONFIRMED", "OPEN", "REJECTED"]
    revision: int
    text: str


@dataclass(frozen=True)
class ConfirmRequirement:
    text: str


@dataclass(frozen=True)
class RejectRequirement:
    reason: str


@dataclass(frozen=True)
class RequirementConfirmed:
    text: str


@dataclass(frozen=True)
class RequirementRejected:
    reason: str


@dataclass(frozen=True)
class PipelineResult:
    state: PipelineState
    outcome: Literal["ACCEPTED", "EMPTY_REQUIREMENT", "INVALID_TRANSITION"]
    event: RequirementConfirmed | RequirementRejected | None


def apply(
    state: PipelineState, command: ConfirmRequirement | RejectRequirement
) -> PipelineResult:
    if isinstance(command, ConfirmRequirement):
        payload = command.text.strip()
    else:
        payload = command.reason.strip()
    if not payload:
        return PipelineResult(state=state, outcome=EMPTY_REQUIREMENT, event=None)
    if state.status != "UNCONFIRMED":
        return PipelineResult(state=state, outcome=INVALID_TRANSITION, event=None)
    if isinstance(command, ConfirmRequirement):
        new_state = PipelineState(
            status="OPEN", revision=state.revision + 1, text=payload
        )
        return PipelineResult(
            state=new_state,
            outcome=ACCEPTED,
            event=RequirementConfirmed(text=payload),
        )
    new_state = PipelineState(
        status="REJECTED", revision=state.revision + 1, text=state.text
    )
    return PipelineResult(
        state=new_state,
        outcome=ACCEPTED,
        event=RequirementRejected(reason=payload),
    )
