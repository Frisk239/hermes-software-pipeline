# Slice 05-14 — publish through gh CLI

Status: **READY**. Branch: `feat/slice-05-14-github-push`.

## Must

After `pipeline approve`, if `admin --github-repo` is set and host `gh auth status` is ok, the shim pushes the worktree and opens one PR. No PAT in git. Isolated runtime still has no credentials. Missing `gh` leaves local FakeDelivery only.

## Out

Approve/merge, GitHub App JWT, putting `gh` inside the isolated runtime.
