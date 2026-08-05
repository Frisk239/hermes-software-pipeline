---
status: accepted
---

# Use Pydantic models and committed JSON Schemas for contracts

Version 1 defines Controller Commands and receipts, Events, artifacts, evidence, capability profiles, Adapter messages, and Engineering Phase/Slice handoffs as versioned Pydantic 2 models. Those models are the sole authoring source and deterministically generate committed JSON Schemas and OpenAPI. Python callers use the typed models, non-Python tools validate the committed Schemas, and CI fails on generated drift or compatibility regression. A contract change edits the Pydantic source first, regenerates the boundary artifacts, and updates fixtures and compatibility evidence in the same change; generated Schema files are never edited independently. Markdown remains a human projection rather than the machine contract.
