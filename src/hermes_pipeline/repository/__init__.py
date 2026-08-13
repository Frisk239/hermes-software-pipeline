"""repository Module — public prepare/create_candidate/verify/cleanup Interface.

Managed Git roots, immutable snapshots, and Candidate creation. The
Module boundary is fixed by ``docs/architecture/system-and-module-design.md``.
The fake Adapter never mutates Git.
"""

from hermes_pipeline.repository.fake import FakeRepository
from hermes_pipeline.repository.ports import (
    RepositoryPort,
    RepositoryRecord,
    RepositoryRequest,
)

__all__ = [
    "FakeRepository",
    "RepositoryPort",
    "RepositoryRecord",
    "RepositoryRequest",
]
