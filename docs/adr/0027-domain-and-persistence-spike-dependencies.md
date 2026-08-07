---
status: accepted
---

# Restrict the domain and persistence spike dependencies to development dependencies

Slice 00-04 admits `SQLAlchemy Core`, `Alembic`, `LangGraph`, and `langgraph-checkpoint-sqlite` with their complete transitive dependency shape (including `sqlite-vec`) as a development/CI-only feasibility-spike dependency family, declared in the `dev` dependency group of `pyproject.toml` and frozen in `uv.lock`; `[project].dependencies` stays empty. The Hermes plugin entry, `--version`, and the normal runtime path never import these packages; they exist only so the Slice 00-04 spike can produce written feasibility evidence for the Controller transaction, SQLite load/recovery, and LangGraph replay boundaries. The Controller database and the LangGraph checkpoint database remain physically separate files, no cross-database transaction exists, and `SqliteSaver` serves only as local feasibility evidence — it never becomes the authority for business state, which remains the Controller Event Log under ADR-0014. Any future path that moves these dependencies into an isolated managed runtime, or otherwise changes the runtime dependency rule in `docs/development/ci-and-testing.md`, requires a later, separately human-approved ADR and Slice; this decision does not authorize a runtime dependency.
