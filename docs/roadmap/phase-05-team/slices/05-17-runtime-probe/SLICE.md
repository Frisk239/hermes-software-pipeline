# Slice 05-17 — host runtime probe and extra CLI families

Status: **READY**. Branch: `feat/slice-05-17-runtime-probe`.

## Must

Host probes `opencode`, `codex`, `claude`, `cursor`, `kiro`, `grok`. Bind any of them to a Stage role + model. Dedicated adapters for fake/OpenCode/Codex; others spawn the pinned CLI in the worktree. Env override that is not a file is a hard miss. Isolated runtime uses pins only.

## Out

Multica claim/daemon, login-shell PATH, full 22-CLI catalog, Hermes-as-worker.
