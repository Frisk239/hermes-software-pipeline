# Slice 05-05 — delivery record

Status: **READY**. Branch: `feat/slice-05-05-delivery-record`.

## Must

`hermes pipeline deliver --sha <integration>` records one namespaced PR (`hermes/<project>/<pipeline>`). Same SHA is idempotent. New SHA updates the same PR `head_sha`. `pipeline read` shows branch / pr / head. Fake never talks to Git or GitHub. No approve or merge.

## Out

Real GitHub App, tokens, merge queue, protected checks, Feishu PR cards.
