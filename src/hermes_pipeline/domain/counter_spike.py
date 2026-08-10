"""Frozen CounterSpike oracle (slice-00-04, AC-01).

This module is the one Slice 00-04 spike component permitted to be retained
as a non-public candidate (AC-14). SPIKE-EXPERIMENTAL marker:
DISPOSITION: RETAIN_NON_PUBLIC_CANDIDATE
# (domain oracle only; adoption by a later Slice still requires its own review).

Frozen semantics (Slice Contract revision 7):

- the initial state is strictly ``(value=0, revision=0)``;
- from any state ``(value=v, revision=r)``, accepting ``Increment(delta=1)``
  transitions strictly to ``(v+1, r+1)`` and produces the unique domain
  Event ``CounterIncremented`` whose payload exactly contains the new
  ``value`` and the new ``revision`` (command identity is carried by the
  existing Controller envelope, never by the domain);
- any ``delta != 1`` returns the typed ``INVALID_DELTA`` result, leaves the
  state completely unchanged, and produces no domain Event;
- expected-revision conflict handling remains the Controller persistence
  layer's responsibility, not the domain's.

The evaluator imports no framework, I/O, clock, identity, randomness, or
provider package and is fully deterministic. It uses only the standard
library and domain value types (architecture rule ARCH-05).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# The only accepted delta; everything else is a typed rejection.
ACCEPTED_DELTA = 1


@dataclass(frozen=True)
class CounterState:
    """The frozen oracle state pair ``(value, revision)``.

    Both fields are plain integers; ``revision`` counts accepted increments
    and is the domain's expected-revision target for the Controller.
    """

    value: int
    revision: int


@dataclass(frozen=True)
class CounterIncremented:
    """The unique domain Event produced by an accepted increment.

    The payload exactly contains the new ``value`` and the new ``revision``
    after the transition; there are no other payload fields.
    """

    value: int
    revision: int

    def payload(self) -> dict[str, int]:
        """The exact event payload: new value and new revision only."""
        return {"value": self.value, "revision": self.revision}


#: Typed outcome of one evaluator application.
CounterOutcome = Literal["ACCEPTED", "INVALID_DELTA"]


@dataclass(frozen=True)
class CounterSpikeResult:
    """The typed result of applying one delta to a CounterState.

    ``state`` is the state after the attempt: for ``ACCEPTED`` it is the
    strictly incremented state; for ``INVALID_DELTA`` it is the completely
    unchanged input state. ``event`` is the unique domain Event for an
    accepted increment and ``None`` otherwise.
    """

    state: CounterState
    outcome: CounterOutcome
    event: CounterIncremented | None


@dataclass(frozen=True)
class CounterSpike:
    """The frozen CounterSpike oracle evaluator.

    The evaluator has no I/O, clock, identity, randomness, or framework
    dependency; identical inputs always produce identical results.
    """

    @property
    def initial_state(self) -> CounterState:
        """The strict initial state ``(value=0, revision=0)``."""
        return CounterState(value=0, revision=0)

    def apply(self, state: CounterState, delta: object) -> CounterSpikeResult:
        """Apply one ``Increment(delta)`` attempt to ``state``.

        Only the built-in integer ``1`` transitions strictly to
        ``(v+1, r+1)`` and emits the unique domain Event.  ``bool`` and
        floating-point lookalikes are rejected at this trust boundary; any
        other delta returns ``INVALID_DELTA`` with the state completely
        unchanged and no domain Event.
        """
        if type(delta) is not int or delta != ACCEPTED_DELTA:
            return CounterSpikeResult(state=state, outcome="INVALID_DELTA", event=None)
        new_state = CounterState(value=state.value + 1, revision=state.revision + 1)
        event = CounterIncremented(value=new_state.value, revision=new_state.revision)
        return CounterSpikeResult(state=new_state, outcome="ACCEPTED", event=event)


__all__ = [
    "ACCEPTED_DELTA",
    "CounterIncremented",
    "CounterOutcome",
    "CounterSpike",
    "CounterSpikeResult",
    "CounterState",
]
