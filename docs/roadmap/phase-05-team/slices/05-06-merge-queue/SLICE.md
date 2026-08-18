# Slice 05-06 — merge-queue observations

Status: **READY**. Branch: `feat/slice-05-06-merge-queue`.

## Must

After a recorded PR, `pipeline deliver --event-id … --check/--review/--queue` records protected-check, review attestation, and queue state. Duplicate `event_id` is a no-op. New SHA resets those fields. `pipeline read` shows them. Still no approve or merge.

## Out

Real GitHub polling, webhooks, merge authority, Feishu cards.
