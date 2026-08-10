"""Stage Executor boundary spike (slice-00-04, AC-02/AC-11).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

The Stage Executor (and the LangGraph graph spike) imports only domain
values and ``ControllerCommandPort``; it never imports the private
persistence port, a persistence Adapter, SQLAlchemy, or database files
(AC-02/AC-11, positive and negative import-boundary tests). Business state
is reachable only through ``ControllerCommandPort.submit``.

This module is intentionally tiny: it exists as the positive import-boundary
fixture and as the place where a future Stage Executor Adapter would live.
"""

from __future__ import annotations

from dataclasses import dataclass

from hermes_pipeline.contracts.runtime import CommandReceipt, ControllerCommand
from hermes_pipeline.controller._command_port import ControllerCommandPort
from hermes_pipeline.domain.counter_spike import CounterState


@dataclass(frozen=True)
class StageBoundaryResult:
    """Bounded typed result of one Stage-side submit through the boundary."""

    receipt: CommandReceipt | None = None
    observed: CounterState | None = None


class StageExecutorBoundary:
    """Deterministic Stage-side boundary that reaches state only via the port.

    ``controller`` is injected as ``ControllerCommandPort``; the class never
    imports or touches the private persistence surface.
    """

    def __init__(self, controller: ControllerCommandPort) -> None:
        self._controller = controller

    def submit_via_controller(self, command: ControllerCommand) -> StageBoundaryResult:
        """Submit one command through the accepted Interface only."""
        receipt = self._controller.submit(command)
        return StageBoundaryResult(receipt=receipt)


__all__ = ["StageBoundaryResult", "StageExecutorBoundary"]
