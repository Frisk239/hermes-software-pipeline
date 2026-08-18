"""controller Module — public submit/read Interface.

The sole authority that evaluates gates and changes Pipeline state.
The Module boundary is fixed by ``docs/architecture/system-and-module-design.md``.
controller never depends on transport, LangGraph, SQLAlchemy, subprocess, or
concrete filesystem Adapters.
"""

from hermes_pipeline.controller.fake import FakeController
from hermes_pipeline.controller.ports import (
    ControllerPort,
    PipelineQuery,
    PipelineView,
)

__all__ = [
    "ControllerPort",
    "FakeController",
    "PipelineQuery",
    "PipelineView",
]
