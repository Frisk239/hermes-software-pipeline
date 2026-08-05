---
status: accepted
---

# Enforce versioned Stage capability profiles

Every Execution Run receives one immutable Stage Capability Profile covering filesystem, executable, network, secret, browser, resource, and external-side-effect authority. Runtime Adapters must declare and enforce all required hard controls; unsupported isolation fails closed instead of degrading to prompt instructions.

Capability escalation is a durable policy request. If approved, it creates a new profile version and normally a new Execution Run. An Agent cannot widen the authority of a live sandbox.
