"""operations Module — public health/reconcile/backup/restore Interface.

Health, reconciliation, backup, and restore operational interfaces.
The Module boundary is fixed by
``docs/architecture/system-and-module-design.md``. doctor/health uses
the Operations.health fake.
"""

from hermes_pipeline.operations.fake import FakeOperations
from hermes_pipeline.operations.ports import (
    HealthReport,
    OperationsPort,
    OperationsRequest,
    OperationsResult,
)

__all__ = [
    "FakeOperations",
    "HealthReport",
    "OperationsPort",
    "OperationsRequest",
    "OperationsResult",
]
