# Slice 02-01 — Local CAS + Artifact Manifest

Status: **READY**. Branch: `feat/slice-02-01-local-cas` from 01-06 tip.

## Must

`LocalCasArtifacts(root)` implements `ArtifactsPort`. `put` stores bytes at `root/blobs/<sha256-hex>` and a sidecar `ArtifactManifest` at `root/manifests/art_<hex>.json`. Port digest stays hex; manifest `content_digest` is `sha256:<hex>`. Restart on the same root still `open`/`verify`. Same payload reuses the digest and leaves no `.tmp` files. `assemble_evidence(ids)` passes only when every id verifies.

## Out

Capability-profile compiler, real Runtime Broker, LangGraph, Codex/OpenCode adapters, RBAC, retention sweeper.
