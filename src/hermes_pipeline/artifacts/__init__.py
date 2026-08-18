"""artifacts Module — public put/open/verify Interface.

Content-addressed artifact storage and integrity verification. The
Module boundary is fixed by ``docs/architecture/system-and-module-design.md``.
"""

from hermes_pipeline.artifacts.fake import FakeArtifacts
from hermes_pipeline.artifacts.local_cas import (
    ArtifactNotFound,
    LocalCasArtifacts,
    assemble_evidence,
)
from hermes_pipeline.artifacts.ports import (
    ArtifactPutRequest,
    ArtifactRecord,
    ArtifactsPort,
    ArtifactVerification,
)

__all__ = [
    "ArtifactNotFound",
    "ArtifactPutRequest",
    "ArtifactRecord",
    "ArtifactVerification",
    "ArtifactsPort",
    "FakeArtifacts",
    "LocalCasArtifacts",
    "assemble_evidence",
]
