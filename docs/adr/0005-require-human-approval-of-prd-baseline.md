---
status: superseded by ADR-0012
---

# Require human approval of the PRD baseline

Architecture may begin only after the Pipeline Initiator explicitly approves a specific PRD attempt. Automated checks and Codex can evaluate completeness and testability but cannot establish that the document expresses the human's actual intent, so requested changes create a new preserved PRD attempt and approval binds downstream work to an immutable PRD baseline.
