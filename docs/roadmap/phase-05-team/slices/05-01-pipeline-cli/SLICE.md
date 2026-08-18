# Slice 05-01 — pipeline submit/read CLI

Status: **READY**. Branch: `feat/slice-05-01-pipeline-cli`.

## Must

`hermes pipeline submit` and `read` exist. Loopback `/v1/commands` with a `text` payload confirms a requirement through Kernel + intake. `op=read` returns UNCONFIRMED|OPEN|REJECTED. Runtime unavailable is fail-closed. Legacy fake envelopes still delegate to the disposable receipt store.

## Out

Feishu cards, GitHub PR, installing the plugin on the user's live Hermes.
