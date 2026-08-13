"""Stage-facing Controller command port (slice-00-04 spike).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE

``ControllerCommandPort`` is the accepted external Controller Interface and
the only Interface the Stage Executor may call. It retains the accepted
signature ``submit(command: ControllerCommand) -> CommandReceipt`` and uses
the existing ``CommandReceipt`` status/error model, including the safe
non-durable ``REJECTED``/``INTERNAL_ERROR`` receipt with fixed message
``persistence unavailable`` and ``retryable=true`` for persistence
unavailability or ``SQLITE_FULL``. Raw ``sqlite3``, SQLAlchemy, or driver
exceptions never cross this Interface.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hermes_pipeline.contracts.runtime import CommandReceipt, ControllerCommand


@runtime_checkable
class ControllerCommandPort(Protocol):
    """The accepted external Controller Interface (Stage Executor only).

    The signature is fixed by the Slice Contract:
    ``submit(command: ControllerCommand) -> CommandReceipt``.
    """

    def submit(self, command: ControllerCommand) -> CommandReceipt:
        """Submit one immutable Controller Command and return its receipt."""
        raise NotImplementedError


__all__ = ["ControllerCommandPort"]
