# Development Readiness Audit

Audit date: 2026-08-05

## Verdict

The repository has accepted design authority for Phase 00. It does not authorize an Agent to implement later product Phases directly from the Roadmap. Before each Phase, Codex must turn the accepted architecture and current repository evidence into that Phase's machine-valid Plan and the next Slice Contract.

This is intentional progressive elaboration, not missing design: future implementation detail must be based on accepted code and Phase Closeout evidence rather than predicted from an empty repository.

## Coverage

| Concern | Governing artifact | Readiness |
| --- | --- | --- |
| product purpose and language | `CONTEXT.md` | ready |
| human/Agent responsibility | ADR-0001–0013, Pipeline state machine | ready |
| approval frequency and question routing | ADR-0007/0012, state machine | ready |
| Workspace/Project roles | ADR-0002/0003, architecture docs | ready for Phase planning |
| Controller authority and transaction model | ADR-0014, controller architecture | accepted architecture; pending Phase 00 transaction spike |
| Stage/Attempt/Run model | context, controller architecture | ready for Phase planning |
| worktree/Git protection | ADR-0009/0010/0011/0013/0017/0018, Git design | remote-delivery and split-baseline model accepted; pending Phase 00/4 feasibility evidence |
| process topology and Module Interfaces | system and Module design | Thin Shim, managed runtime, and protected loopback transport accepted; pending Phase 00 spike |
| LangGraph boundary | ADR-0014/0023 | Controller boundary and Stage-only LangGraph accepted; pending Phase 00 replay spike |
| runtime stack | technology stack, ADR-0020–0025 | version 1 stack accepted; lockfile and Phase 00 feasibility evidence pending |
| command/event/artifact/evidence contracts | ADR-0016/0024, data contract doc and `schemas/runtime/` | immutable evidence and Pydantic-authoring model accepted; typed business payload catalog belongs to relevant product Phase |
| engineering handoff contracts | ADR-0024, operating model and `schemas/engineering/` | authoring direction accepted; Schema alignment, Pydantic source, fixtures, and tooling remain Phase 00 work |
| Agent context and permissions | ADR-0015, root/role contracts, capability schema | capability model accepted; pending Phase 00 enforcement spikes |
| threat model and trust boundaries | security design | ready for Phase 00 security spikes |
| configuration and lifecycle | operations design | ready for Phase planning |
| observability, backup, recovery | operations design | ready for Phase planning |
| CI and testing | CI/test docs, coding standard | ready for skeleton implementation |
| install and safe update | installation/update design, ADR-0008 | ready for Phase planning |
| public maintenance | root policy files, Roadmap Slice 00-01 and Phase 6 | initial license, governance, contribution, support, conduct, and security policies ready; public-preview operational commitments remain Phase 6 work |
| Phase/Slice execution model | operating model and Phase 00 plan | ready after Base SHA exists |

## Recorded governance decisions and remaining authorization

- ADR-0014 through ADR-0025 were accepted on 2026-08-05.
- Repository name `hermes-software-pipeline`, product name `Hermes Software Pipeline`, and default branch `main` were approved on 2026-08-05; the GitHub repository has been renamed and the local `origin` URL points at `Frisk239/hermes-software-pipeline`.
- Distribution name `hermes-pipeline`, import name `hermes_pipeline`, operator command tree `hermes pipeline`, and internal runtime entry point `hermes-pipeline-runtime` were standardized from the upstream Hermes plugin CLI contract.
- Apache License 2.0 and `Frisk239` as the initial Repository Governance Owner were approved on 2026-08-05.
- Creation of the initial documentation baseline commit on `main` still requires explicit authorization after the baseline audit passes.

## Evidence blocking technology finalization

The accepted stack becomes a supported implementation only after Phase 00 proves:

- Hermes source-plugin loading and lifecycle behavior;
- loopback descriptor protection and restart behavior on Windows/Linux;
- SQLite single-writer workload and crash recovery;
- LangGraph checkpoint/replay semantics;
- stable Codex/OpenCode structured invocation and cancellation;
- enforceable capability boundaries on both operating systems;
- OpenCode/Chrome DevTools MCP isolation;
- Feishu command interception and GitHub conditional polling.

Failure changes the corresponding ADR through human review. It never grants an Executor freedom to substitute technology.

## Deliberately deferred detail

The following is designed at the start of the owning Phase, before implementation:

- the complete typed Controller Command/Event payload catalog in Phase 1;
- concrete Artifact roles and retention matrix in Phase 2;
- PRD, Architecture, Development, E2E, and Acceptance input/output Schemas in Phases 2–4;
- complete RBAC command decision table and provider actor mapping in Phases 3 and 5;
- GitHub/Feishu provider payload fixtures in Phase 5;
- operational thresholds, compatibility matrix, and release signing implementation in Phase 6.

Each item is bounded by existing Interfaces, invariants, and security rules. Moving it earlier would require guessing against implementation evidence; moving it into an Executor's discretion is prohibited.

## Validation performed

- governed text files decode as UTF-8 without replacement characters and have balanced Markdown fences;
- every governed JSON file parses, all 14 current Schemas have unique `$id` values, and every local or absolute `$ref` and JSON Pointer fragment resolves;
- all local Markdown links resolve;
- all ADRs have terminal `accepted` or `superseded` status;
- root baseline policy files exist;
- CLI, health-endpoint, contract-source, webhook/polling, and provider terminology were reconciled;
- the repository baseline commit exists on `main`, and the local `origin` points at `Frisk239/hermes-software-pipeline`.

These validations are executable, dependency-free, and offline through `scripts/check_documentation.py` and `scripts/check_schemas.py` (introduced by slice-00-01), including deliberately broken bootstrap fixtures under `scripts/fixtures/`; the checkers also lock the 14 bootstrap Schema `$id` identities, require the root entry point files, confine local links to the repository root, validate the workflow YAML syntax plus read-only permissions and exact command/OS binding, and `--self-test-negative` executes them against the broken fixtures to prove stable nonzero exits with sanitized bounded output. The same commands run on Windows and Linux CI via `.github/workflows/documentation-contracts.yml`. Full Draft 2020-12 meta-schema validation and Pydantic-authoring adoption remain owned by slice-00-03.

## Readiness rule

The project is **design-ready** when the human decisions above are recorded. It is **Phase-00 execution-ready** when a Base SHA and machine-valid Phase/Slice documents exist. It is **product-implementation-ready one Phase at a time** only after the previous Phase Closeout and current Phase Plan are approved.

No claim of "fully specified" removes the need for empirical feasibility, current-repository planning, independent execution, or Codex review.
