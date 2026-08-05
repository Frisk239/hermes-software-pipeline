---
status: accepted
---

# Store immutable content-addressed artifacts and evidence

Durable Stage outputs are stored through an Artifact Store and identified by immutable Artifact Manifests containing content hash, schema, producer, source identities, execution provenance, sensitivity, and retention policy. Gates consume typed Evidence Bundles referencing exact Artifact identities.

Files exported into Git are collaboration projections, not authoritative identities. Large logs, transcripts, screenshots, and secrets are kept outside Pipeline Events under Project access and retention policy.
