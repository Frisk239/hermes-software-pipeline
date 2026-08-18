---
status: accepted
---

# Additional bindable CLI runtimes

**Status: accepted.** Repository owner authorized this on 2026-08-18: Stage roles may bind to more host CLIs than Codex and OpenCode.

ADR-0032 still holds: Stage duties stay fixed; a binding is runtime family + model. This ADR adds `claude`, `cursor`, `kiro`, and `grok` as bindable families beside `fake`, `codex`, and `opencode`.

The host probes PATH (or `HERMES_<FAMILY>_PATH`). A pinned path that is not a file is a hard miss. Isolated runtime uses only those pins. Families without a dedicated Adapter may spawn the pinned executable in the managed worktree and still fail closed if the binary is missing or the process fails. This does not add a claim/daemon queue and does not treat Hermes Agent as a worker CLI.
