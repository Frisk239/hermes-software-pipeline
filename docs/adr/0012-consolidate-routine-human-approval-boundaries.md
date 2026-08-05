---
status: accepted
---

# Consolidate routine human approval at the solution and merge boundaries

The standard Pipeline has two scheduled human approval boundaries: one Solution Baseline Approval covering the PRD, technical design, and test plan before development, and one repository-native Merge Approval after all automated verification passes. PRD and Architecture remain independent Codex Stages, while requirement questions, material baseline conflict, permission escalation, conflicting evidence, and exhausted retry budgets trigger conditional human intervention instead of adding routine approval stops. Ordinary target-branch drift triggers automatic integration revalidation rather than a human approval.
