# Slice 05-04 — hook uses event actor

Status: **READY**. Branch: `feat/slice-05-04-hook-actor`.

## Must

Intake cards take `principal_id` from the event sender (`sender_id` / `user_id` / source). JSON cannot spoof the actor. Missing sender still skips Prod Main but does not submit.

## Out

Feishu token verification, GitHub identity.
