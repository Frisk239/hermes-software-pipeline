# Slice 05-16 — allow real OpenCode/Codex spawn

Status: **READY**. Branch: `feat/slice-05-16-allow-real-spawn`.

## Must

A file named `opencode` / `codex` may launch when it exists. Spawn uses the managed worktree cwd. Missing binary is UNSUPPORTED. OSError is FAILED, not a fixture write.

## Out

Long-running agent sessions, prompt/context packaging, changing capability profiles.
