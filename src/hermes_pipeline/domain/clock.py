"""Injectable Clock Protocol for later slices.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_PHASE_01
"""

from typing import Protocol

from . import datetime


class Clock(Protocol):
    def now(self) -> datetime: ...
