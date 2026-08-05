"""controller Module skeleton (slice-00-02).

The sole authority that evaluates gates and changes Pipeline state.
The Module boundary is fixed by ``docs/architecture/system-and-module-design.md``;
this skeleton deliberately carries no business behavior. controller
never depends on transport, LangGraph, SQLAlchemy, subprocess, or
concrete filesystem Adapters.
"""
