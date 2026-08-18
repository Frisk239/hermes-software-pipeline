# Slice 05-13 — GitHub PR adapter

Status: **READY**. Branch: `feat/slice-05-13-github-pr`.

## Must

A GitHub adapter can open or reuse one PR for `hermes/<project>/<pipeline>`. No approve or merge. No token in records. No token in the Hermes process env allow-list. Without token or repo, local FakeDelivery still works. `admin --github-repo owner/name` stores the repo.

## Out

Pushing git objects, GitHub App JWT, merge queue, live network in CI.
