# Hermes Software Pipeline

This context defines the language used by the constrained software-engineering pipeline coordinated through Hermes.

## Language

**Prod Main**:
The sole conversational operator that translates user intent into permitted Pipeline requests and reports progress back to the user.
_Avoid_: Controller, administrator, orchestrator

**Pipeline Controller**:
The sole authority that evaluates gates and changes Pipeline state according to deterministic rules.
_Avoid_: Agent, coordinator, Prod Main

**Pipeline**:
A durable instance of the software-engineering process that carries one user requirement from intake through planning, implementation, testing, and acceptance.
_Avoid_: Chat, session, task

**Controller Command**:
An immutable, authenticated request submitted to the Pipeline Controller with a globally unique identity and expected Pipeline revision. It may be rejected and is not itself a state transition or approval.
_Avoid_: Event, decision, transition, LangGraph Command

**Pipeline Event**:
An immutable, ordered business fact appended by the Pipeline Controller after accepting a Controller Command; the Event Log is the sole authoritative Pipeline history.
_Avoid_: Message, log line, checkpoint, notification

**Pipeline Revision**:
The monotonically increasing version of one Pipeline aggregate used for optimistic concurrency and command conflict detection.
_Avoid_: Artifact version, schema version, Git revision

**Workspace**:
The single team boundary served by one installed instance of the plugin; it contains the team's members and Projects. A personal installation is a Workspace with one member.
_Avoid_: Tenant, organization, account

**Workspace Member**:
A person admitted to the Workspace identity boundary; membership alone grants no access to any Project.
_Avoid_: Project Member, user, account

**Workspace Administrator**:
A Workspace governance role responsible for membership, Project registration, global policy, resource limits, audit metadata, and recovery; it grants no automatic access to Project content.
_Avoid_: Project Administrator, Host Operator, superuser

**Project**:
A registered software product or codebase within the Workspace to which Pipelines and access rights belong.
_Avoid_: Repository, workspace, Pipeline

**Project Member**:
A Workspace member who has been explicitly admitted to a specific Project and may access that Project according to an assigned Project role.
_Avoid_: Workspace Member, observer, user

**Project Administrator**:
A Project role responsible for that Project's membership, configuration, and Pipeline operations while remaining subject to Workspace-wide gates and safety policy.
_Avoid_: Workspace Administrator, Pipeline Controller, approver

**Project Viewer**:
A Project Member who may inspect Project-visible Pipeline information but cannot initiate or operate a Pipeline.
_Avoid_: Observer, Workspace Member

**Project Contributor**:
A Project Member who may initiate Pipelines and operate the Pipelines they initiated.
_Avoid_: Developer, executor, Project Administrator

**Pipeline Initiator**:
The Project Contributor who initiated a particular Pipeline and may answer its blockers or request permitted control actions for that Pipeline.
_Avoid_: Pipeline owner, administrator, Prod Main

**Stage**:
A bounded unit of Pipeline responsibility executed with its own role contract, context, attempt history, and required result.
_Avoid_: Task, session, step

**Stage Attempt**:
A semantic effort to produce one reviewable Stage result. Reviewer feedback, invalid output, changed semantic input, or verified failure creates a new Attempt.
_Avoid_: Process retry, model call, Execution Run

**Execution Run**:
One infrastructure execution of a Stage Attempt under a fixed workflow, model, tool, runtime, capability, and source configuration. Transient recovery may create another Run without changing the Attempt.
_Avoid_: Stage Attempt, Pipeline, session

**Stage Lease**:
A time-limited exclusive execution grant carrying a monotonically increasing fencing generation; results from an expired or superseded generation cannot advance the Pipeline.
_Avoid_: Project permission, lock file, approval

**Stage Capability Profile**:
An immutable, versioned declaration of the filesystem, executable, network, secret, browser, resource, and side-effect authority required by one Execution Run and enforced by its runtime.
_Avoid_: Agent prompt, Project role, tool list

**Gate**:
A deterministic evaluation between Stages that decides whether verified evidence permits a defined transition.
_Avoid_: Approval, review, Agent verdict

**Requirement Input Confirmation**:
The Pipeline Initiator's explicit confirmation of the normalized requirement used to create a Pipeline; it is an intake decision rather than a separate approval Stage.
_Avoid_: PRD approval, Solution Baseline Approval, implicit intent

**Solution Approver**:
The Project Member designated for a Pipeline to review the complete proposed solution baseline before development begins.
_Avoid_: Pipeline Initiator, Project Administrator, Codex

**Solution Baseline Approval**:
The Solution Approver's explicit acceptance of one PRD, technical design, and test-plan set as the immutable baseline for development and verification.
_Avoid_: PRD approval, Technical Approval, automatic Gate

**Approved Solution Baseline**:
The immutable PRD, technical design, and test-plan set referenced by a Solution Baseline Approval.
_Avoid_: Approved PRD, latest documents, design draft

**Merge Approver**:
The human reviewer authorized by Project delivery policy to approve and merge a Candidate through the repository's protected MR or PR workflow.
_Avoid_: Solution Approver, Pipeline Controller, Agent

**Merge Approval**:
The final human acceptance of the exact MR or PR head that passed the Pipeline's automated verification Gates.
_Avoid_: Codex Acceptance, deployment approval, automatic Gate

**Requirement Question**:
A downstream Agent's evidence-backed question about product intent that requires a human decision before the Agent can proceed reliably; it does not by itself invalidate a proposed or approved baseline.
_Avoid_: Requirement defect, rejection, automatic rework

**Requirement Decision**:
The Pipeline Initiator's response to a Requirement Question that either reopens the PRD, directs the questioning Agent under the existing baseline, or keeps the question open for further discussion.
_Avoid_: Agent recommendation, Gate verdict, clarification message

**Architecture Direction**:
A Requirement Decision that leaves product intent unchanged and gives the Architecture Stage an authoritative human instruction for resolving its question.
_Avoid_: PRD amendment, chat reply, design approval

**Managed Worktree**:
The isolated writable Git working tree created and governed by the Pipeline Controller for one Pipeline's Development lifecycle.
_Avoid_: Stage worktree, user workspace, verification sandbox

**Verification Sandbox**:
A clean, short-lived runtime bound to an exact Integration Candidate SHA for one independent E2E or Acceptance execution.
_Avoid_: Managed Worktree, shared test environment, Agent session

**User Working Copy**:
A Project Member's own Git working tree, which Pipeline Agents never use or modify.
_Avoid_: Managed Worktree, Project

**Candidate SHA**:
The Controller-created Git commit that contains a Development attempt accepted by the Development Gate and is the exact source snapshot evaluated by downstream verification Stages.
_Avoid_: Agent-reported commit, branch head, working tree

**Planning Base SHA**:
The immutable Project source commit selected when a Pipeline is created and used by PRD, Architecture, and initial Development until an authorized semantic Baseline Refresh replaces it.
_Avoid_: Integration Base SHA, target branch head, latest commit

**Integration Base SHA**:
The current protected target-branch commit against which a Candidate is prepared and validated for delivery.
_Avoid_: Planning Base SHA, Candidate SHA, moving branch name

**Integration Candidate SHA**:
The exact synthetic merge, merge-group, or merge-train commit derived from a Candidate and an Integration Base and evaluated by final required checks.
_Avoid_: Candidate SHA, branch head, proposed merge

**Baseline Refresh Request**:
A human decision request raised only when material semantic conflict requires replacing the Planning Base SHA; ordinary target drift is handled by automatic integration revalidation.
_Avoid_: Integration refresh, automatic revalidation, silent baseline mutation

**Artifact Manifest**:
An immutable, content-addressed record of an Artifact's identity, hash, schema, producer, source SHAs, execution provenance, sensitivity, and retention policy.
_Avoid_: Mutable file path, Pipeline Event, report summary

**Evidence Bundle**:
A typed set of Artifact Manifest references submitted to a Gate as proof for one exact Stage Attempt and source identity.
_Avoid_: Chat summary, mutable directory, Agent assertion

**Remote Delivery Adapter**:
The separately credentialed least-privilege Module that publishes a verified Candidate to a namespaced remote branch and creates or updates its MR or PR without approval, merge, or protection-bypass authority.
_Avoid_: Pipeline Controller, Agent Git client, Merge Approver

**Approval Attestation**:
An immutable record binding an authenticated provider actor, Project authority, exact artifact or Git head, policy version, decision, source, and time.
_Avoid_: Card click, chat reply, notification receipt

**PRD Stage**:
An independent Codex Stage that turns the confirmed requirement input into a product requirements document and testable acceptance criteria.
_Avoid_: Planning Stage, Architecture Stage

**Architecture Stage**:
An independent Codex Stage that evaluates the current PRD attempt against the codebase and produces the technical design and test plan.
_Avoid_: PRD Stage, Development Stage

**Project Access Request**:
A request by a Workspace member to be admitted to a specific Project; membership is established only after an authorized approval.
_Avoid_: Invitation, Controller Command, automatic enrollment

**Host Operator**:
The person or automation responsible for the machine, Hermes installation, and plugin runtime; this responsibility grants no automatic Project role inside the Workspace.
_Avoid_: Workspace Administrator, Project Administrator, Plugin Installer

**Plugin Installer**:
The actor that installs the plugin package; installation does not establish membership in the Workspace or ownership of a Project.
_Avoid_: Administrator, owner

## Engineering language

The terms below describe how maintainers build this repository. They are never used as aliases for runtime Pipeline records.

**Repository Governance Owner**:
The accountable maintainer identity named by repository policy to accept governance decisions, manage repository settings, and delegate maintainership. It is an accountability designation, not a runtime role, OAuth session, personal access token, or credential granted to the Pipeline.
_Avoid_: Workspace Administrator, Project Administrator, Host Operator, runtime owner

**Engineering Phase**:
A maintainer planning horizon that delivers one coherent, integrated repository capability through an approved set of Engineering Slices.
_Avoid_: Pipeline, Stage, release, sprint

**Engineering Slice**:
One independently reviewable and revertible repository change governed by an immutable Slice Contract and accepted through a fixed Candidate and Evidence Bundle.
_Avoid_: Stage, ticket, layer task, model session

**Codex Planner-Designer-Reviewer**:
The engineering role that designs Phase and Slice scope, defines Interfaces and acceptance contracts, and independently reviews Executor results without implementing rejected rework in the review turn.
_Avoid_: Executor Agent, Pipeline Controller, Prod Main

**Executor Agent**:
The independent engineering role that implements and self-verifies one approved Slice Contract without changing its design, scope, acceptance criteria, or review result.
_Avoid_: Codex Planner-Designer-Reviewer, Development Stage, Git Custodian

**Slice Contract**:
The immutable, machine-validated work order binding one Engineering Slice to its Base SHA, scope, Interfaces, authority, acceptance criteria, tests, and required evidence.
_Avoid_: Prompt, Phase Plan, PRD, chat request

**Review Verdict**:
The Codex review result bound to one Slice Contract, Candidate, and Evidence Bundle: `PASS`, `REWORK`, or `BLOCKED_CONTRACT`.
_Avoid_: Merge Approval, Gate, Agent summary
