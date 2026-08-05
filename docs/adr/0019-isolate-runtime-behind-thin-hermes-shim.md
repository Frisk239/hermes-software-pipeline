---
status: accepted
---

# Isolate the managed Pipeline Runtime behind a thin Hermes shim

Hermes source-plugin installation clones and imports plugin code but does not provide isolated installation of arbitrary runtime dependencies. The Hermes-loaded `plugin.yaml` and root `__init__.py` therefore remain a standard-library and Hermes-guaranteed shim that registers high-level tools and operator commands, while a separately bootstrapped and supervised local Pipeline Runtime owns LangGraph, persistence, Agent execution, artifacts, and all durable state. The shim fails closed when the runtime is unavailable and never falls back to executing Pipeline logic inside Hermes.
