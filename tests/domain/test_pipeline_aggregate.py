"""Fake-Pipeline aggregate tests (slice-01-01)."""

from __future__ import annotations

import ast
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from hermes_pipeline.domain.errors import (
    ACCEPTED,
    EMPTY_REQUIREMENT,
    INVALID_TRANSITION,
)
from hermes_pipeline.domain.pipeline import (
    ConfirmRequirement,
    PipelineState,
    RejectRequirement,
    RequirementConfirmed,
    RequirementRejected,
    apply,
)

_ALLOWED_STATUSES = frozenset({"UNCONFIRMED", "OPEN", "REJECTED"})
_PIPELINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "hermes_pipeline"
    / "domain"
    / "pipeline.py"
)
_FORBIDDEN_IMPORTS = frozenset(
    {"sqlalchemy", "langgraph", "sqlite3", "pathlib", "hermes_pipeline.controller"}
)


def test_accept_confirm_from_unconfirmed() -> None:
    state = PipelineState(status="UNCONFIRMED", revision=0, text="")
    result = apply(state, ConfirmRequirement(text="need a login page"))
    assert result.outcome == ACCEPTED
    assert result.state == PipelineState(
        status="OPEN", revision=1, text="need a login page"
    )
    assert isinstance(result.event, RequirementConfirmed)
    assert result.event.text == "need a login page"


def test_accept_reject_from_unconfirmed() -> None:
    state = PipelineState(status="UNCONFIRMED", revision=0, text="")
    result = apply(state, RejectRequirement(reason="out of scope"))
    assert result.outcome == ACCEPTED
    assert result.state == PipelineState(status="REJECTED", revision=1, text="")
    assert isinstance(result.event, RequirementRejected)
    assert result.event.reason == "out of scope"


def test_empty_text_and_reason_leave_state_unchanged() -> None:
    state = PipelineState(status="UNCONFIRMED", revision=0, text="")
    for command in (
        ConfirmRequirement(text=""),
        ConfirmRequirement(text="   \t\n"),
        RejectRequirement(reason=""),
        RejectRequirement(reason="  \n"),
    ):
        result = apply(state, command)
        assert result.outcome == EMPTY_REQUIREMENT
        assert result.state == state
        assert result.event is None


def test_illegal_transitions_from_open_and_rejected() -> None:
    opened = apply(
        PipelineState(status="UNCONFIRMED", revision=0, text=""),
        ConfirmRequirement(text="need a login page"),
    ).state
    rejected = apply(
        PipelineState(status="UNCONFIRMED", revision=0, text=""),
        RejectRequirement(reason="out of scope"),
    ).state
    for state in (opened, rejected):
        for command in (
            ConfirmRequirement(text="again"),
            RejectRequirement(reason="again"),
        ):
            result = apply(state, command)
            assert result.outcome == INVALID_TRANSITION
            assert result.state == state
            assert result.event is None


def test_second_confirm_is_invalid_transition_with_unchanged_revision() -> None:
    first = apply(
        PipelineState(status="UNCONFIRMED", revision=0, text=""),
        ConfirmRequirement(text="need a login page"),
    )
    second = apply(first.state, ConfirmRequirement(text="need a login page"))
    assert first.outcome == ACCEPTED
    assert first.state.status == "OPEN"
    assert second.outcome == INVALID_TRANSITION
    assert second.state == first.state
    assert second.state.revision == 1
    assert second.event is None


def test_confirm_and_reject_strip_surrounding_whitespace() -> None:
    confirmed = apply(
        PipelineState(status="UNCONFIRMED", revision=0, text=""),
        ConfirmRequirement(text="  need a login page  "),
    )
    assert confirmed.outcome == ACCEPTED
    assert confirmed.state.text == "need a login page"
    assert isinstance(confirmed.event, RequirementConfirmed)
    assert confirmed.event.text == "need a login page"
    rejected = apply(
        PipelineState(status="UNCONFIRMED", revision=0, text=""),
        RejectRequirement(reason="  out of scope  "),
    )
    assert rejected.outcome == ACCEPTED
    assert isinstance(rejected.event, RequirementRejected)
    assert rejected.event.reason == "out of scope"


@settings(database=None, derandomize=True, deadline=None, max_examples=100)
@given(
    st.lists(
        st.one_of(
            st.builds(ConfirmRequirement, text=st.text()),
            st.builds(RejectRequirement, reason=st.text()),
        ),
        max_size=12,
    )
)
def test_status_stays_in_the_three_state_set(
    commands: list[ConfirmRequirement | RejectRequirement],
) -> None:
    state = PipelineState(status="UNCONFIRMED", revision=0, text="")
    assert state.status in _ALLOWED_STATUSES
    for command in commands:
        result = apply(state, command)
        assert result.state.status in _ALLOWED_STATUSES
        if result.outcome != ACCEPTED:
            assert result.state == state
            assert result.event is None
        state = result.state


def test_pipeline_import_boundary() -> None:
    tree = ast.parse(_PIPELINE_PATH.read_text(encoding="utf-8"))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in _FORBIDDEN_IMPORTS or alias.name in (
                    "hermes_pipeline.controller",
                ):
                    violations.append(f"{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".", 1)[0]
            if top in _FORBIDDEN_IMPORTS or node.module.startswith(
                "hermes_pipeline.controller"
            ):
                violations.append(f"{node.lineno}: from {node.module}")
    source = _PIPELINE_PATH.read_text(encoding="utf-8")
    assert "datetime.now" not in source
    assert "Clock" not in source
    assert violations == [], f"forbidden pipeline imports: {violations}"


def test_errors_export_outcome_literals_only() -> None:
    from hermes_pipeline.domain import errors

    assert errors.__all__ == ["ACCEPTED", "EMPTY_REQUIREMENT", "INVALID_TRANSITION"]
    assert errors.ACCEPTED == "ACCEPTED"
    assert errors.EMPTY_REQUIREMENT == "EMPTY_REQUIREMENT"
    assert errors.INVALID_TRANSITION == "INVALID_TRANSITION"


def test_clock_protocol_exists_and_is_unused_by_apply() -> None:
    from hermes_pipeline.domain.clock import Clock

    assert callable(Clock.now)
