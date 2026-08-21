# Slice 05-65 — read publishes PR when verify is READY

Status: **READY**. Branch: `feat/slice-05-65-read-publish-pr`.

## Must

`hermes pipeline read` on a READY pipeline with no `pr_url` runs host `gh` publish. Worker/approve poll abort no longer skips the PR. Fake path and missing github.json stay empty.

## Out

Tokens in the sidecar. Changing Outbox effect payload.
