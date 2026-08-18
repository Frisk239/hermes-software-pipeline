# Slice 03-02 — PRD Stage and automatic Gate

Status: **READY**. Branch: `feat/slice-03-02-prd-stage` from 03-01 tip.

## Must

After 03-01 intake opens a Pipeline, `PrdStage.run(pipeline_id, workspace_id, project_id)` resolves `planner` from `BindingTable` (fake or opencode+model). Missing binding is fail-closed and writes no artifact. A resolved binding puts fixed PRD bytes into `LocalCasArtifacts` and records `artifact_id`. `PrdGate.evaluate(...)` PASSes only when the Pipeline is still OPEN and that artifact `verify`s; missing artifact, verify failure, or a non-OPEN Pipeline FAILs. A new store instance on the same CAS root still PASSes.

## Out

Live models, Architecture Stage, Solution Approval, Managed Worktree, LangGraph.
