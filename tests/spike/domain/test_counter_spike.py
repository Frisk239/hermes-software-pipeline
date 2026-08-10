"""CounterSpike oracle tests (slice-00-04, AC-01).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Positive: the initial state is exactly ``(value=0, revision=0)``; multi-step
``Increment(delta=1)`` sequences transition ``(v, r) -> (v+1, r+1)`` and
emit ``CounterIncremented`` carrying the exact new value and revision;
property tests over generated command sequences keep forbidden states
unreachable; a domain import of SQLAlchemy, LangGraph, ``sqlite3``,
filesystem, or time fails the import-boundary scan.

Negative: ``Increment(delta=0)``, ``Increment(delta=2)``, and any other
delta return the typed ``INVALID_DELTA`` result with the state completely
unchanged and no domain Event.
"""

from __future__ import annotations

import ast
from pathlib import Path

from hermes_pipeline.domain.counter_spike import (
    CounterIncremented,
    CounterSpike,
    CounterState,
)


def test_initial_state_is_strictly_zero_zero() -> None:
    spike = CounterSpike()
    assert spike.initial_state == CounterState(value=0, revision=0)


def test_multi_step_increment_transitions_strictly() -> None:
    spike = CounterSpike()
    state = spike.initial_state
    for step in range(1, 6):
        result = spike.apply(state, 1)
        assert result.outcome == "ACCEPTED"
        expected = CounterState(value=step, revision=step)
        assert result.state == expected
        assert result.event == CounterIncremented(value=step, revision=step)
        assert result.event is not None
        assert result.event.payload() == {"value": step, "revision": step}
        state = result.state


def test_event_payload_exactly_contains_new_value_and_revision() -> None:
    spike = CounterSpike()
    result = spike.apply(spike.initial_state, 1)
    assert result.event is not None
    assert set(result.event.payload()) == {"value", "revision"}
    assert result.event.payload() == {"value": 1, "revision": 1}


def test_delta_zero_returns_invalid_delta_unchanged() -> None:
    spike = CounterSpike()
    result = spike.apply(spike.initial_state, 0)
    assert result.outcome == "INVALID_DELTA"
    assert result.state == CounterState(value=0, revision=0)
    assert result.event is None


def test_delta_two_returns_invalid_delta_unchanged() -> None:
    spike = CounterSpike()
    result = spike.apply(spike.initial_state, 2)
    assert result.outcome == "INVALID_DELTA"
    assert result.state == CounterState(value=0, revision=0)
    assert result.event is None


def test_other_deltas_rejected_with_state_unchanged() -> None:
    spike = CounterSpike()
    for delta in (-1, 3, 10, 1000, -1000):
        result = spike.apply(spike.initial_state, delta)
        assert result.outcome == "INVALID_DELTA"
        assert result.state == spike.initial_state
        assert result.event is None


def test_boolean_and_float_lookalikes_are_rejected_at_the_domain_boundary() -> None:
    """``True`` and ``1.0`` compare equal to ``1`` in Python, but are not
    the frozen integer ``Increment(delta=1)`` input accepted by the oracle."""
    spike = CounterSpike()
    for delta in (True, 1.0):
        result = spike.apply(spike.initial_state, delta)
        assert result.outcome == "INVALID_DELTA"
        assert result.state == spike.initial_state
        assert result.event is None


def test_rejection_after_progress_leaves_state_completely_unchanged() -> None:
    spike = CounterSpike()
    state = spike.initial_state
    for _ in range(3):
        state = spike.apply(state, 1).state
    before = state
    result = spike.apply(state, 0)
    assert result.outcome == "INVALID_DELTA"
    assert result.state == before
    assert result.event is None


def test_forbidden_states_unreachable_by_generated_sequences() -> None:
    """Property-style scan over generated command sequences.

    For every reachable state, applying any delta keeps the state in the
    (value >= 0, revision >= 0, value == revision) invariant, and every
    accepted step increments by exactly one.
    """
    spike = CounterSpike()
    state = spike.initial_state
    deltas = (-3, -1, 0, 1, 2, 5)
    for _ in range(20):
        for delta in deltas:
            result = spike.apply(state, delta)
            assert result.state.value >= 0
            assert result.state.revision >= 0
            assert result.state.value == result.state.revision
            if result.outcome == "ACCEPTED":
                assert delta == 1
                assert result.event is not None
                assert result.state == CounterState(
                    value=state.value + 1, revision=state.revision + 1
                )
            else:
                assert result.state == state
                assert result.event is None
        state = spike.apply(state, 1).state


def _domain_files() -> list[Path]:
    root = Path(__file__).resolve().parents[3]
    domain_dir = root / "src" / "hermes_pipeline" / "domain"
    return sorted(path for path in domain_dir.rglob("*.py"))


def test_domain_imports_only_stdlib_and_domain_value_types() -> None:
    """AC-01 import-boundary scan: no framework, I/O, clock, identity,
    randomness, or provider import in any domain module."""
    forbidden_tops = {
        "sqlalchemy",
        "langgraph",
        "alembic",
        "sqlite3",
        "os",
        "sys",
        "pathlib",
        "time",
        "datetime",
        "random",
        "subprocess",
        "requests",
        "json",
        "socket",
        "uuid",
        "importlib",
    }
    violations: list[str] = []
    for path in _domain_files():
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".", 1)[0]
                    if top in forbidden_tops:
                        violations.append(
                            f"{path.name}:{node.lineno}: import {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".", 1)[0]
                if top in forbidden_tops and node.level == 0:
                    violations.append(
                        f"{path.name}:{node.lineno}: import {node.module}"
                    )
    assert violations == [], f"forbidden domain imports: {violations}"


def test_domain_imports_hermes_only_domain_or_contracts() -> None:
    """Domain modules may reference hermes_pipeline only for domain or
    contracts value types."""
    violations: list[str] = []
    for path in _domain_files():
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                parts = node.module.split(".")
                if parts[0] == "hermes_pipeline" and (
                    len(parts) < 3
                    or parts[1] not in ("domain", "contracts")
                    or len(parts) > 3
                ):
                    violations.append(f"{path.name}:{node.lineno}: {node.module}")
    assert violations == [], f"out-of-boundary domain imports: {violations}"
