# Hermes Software Pipeline

Hermes Software Pipeline is a planned Hermes plugin and managed local runtime for carrying one software requirement through confirmed intake, independent product and architecture planning, constrained implementation, isolated verification, and a protected pull-request merge.

## Status

**Design baseline in preparation — no runnable product exists yet.**

The architecture and version 1 technology decisions are accepted. Phase 00 will establish the repository, contract toolchain, Python runtime skeleton, Hermes Shim, platform-security feasibility, and reproducible Windows/Linux checks. Do not install this repository expecting production Pipeline behavior.

See:

- [domain language](CONTEXT.md);
- [repository constitution](AGENTS.md);
- [documentation map](docs/README.md);
- [engineering roadmap](docs/roadmap/ROADMAP.md);
- [capability and verification traceability](docs/roadmap/TRACEABILITY.md);
- [Phase 00 plan](docs/roadmap/phase-00-foundation/PHASE.md);
- [development readiness audit](docs/development/development-readiness-audit.md).

## Product promise

The target product will:

- preserve an immutable, auditable record of Pipeline decisions and evidence;
- keep Agent execution separate from deterministic Pipeline authority;
- constrain every Agent Run with explicit, enforceable capabilities;
- isolate planning, development, and verification source boundaries;
- bind approvals and test evidence to exact artifacts and Git object identities;
- leave final approval and merge under protected repository-native human authority;
- recover deterministically from duplicate delivery, process crashes, stale workers, and target-branch drift.

## Trust limits

Version 1 is a local, single-Workspace product. It does not promise:

- defense against a malicious host administrator;
- VM-grade containment of arbitrary native code;
- multiple active Controller replicas or high-availability failover;
- automatic approval, merge, deployment, or branch-protection bypass;
- a remotely exposed Controller service;
- hard multi-tenant isolation on a shared hostile machine.

Repository content, Agent output, chat content, browser pages, provider callbacks, and model-generated tool arguments are untrusted data. See the [threat model](docs/security/threat-model-and-trust-boundaries.md).

## Planned installation shape

The public operator interface is the plugin-owned `hermes pipeline` command tree. The Python distribution is `hermes-pipeline`, its import package is `hermes_pipeline`, and the managed runtime uses the internal `hermes-pipeline-runtime` entry point.

The intended source-install flow is:

```text
hermes plugins install Frisk239/hermes-software-pipeline --enable
hermes pipeline setup
hermes pipeline doctor
hermes gateway restart
```

These commands do not exist in the repository yet. Phase 00 must prove the exact Hermes installation and lifecycle contract before they are documented as supported.

## Development model

Development proceeds one approved Engineering Slice at a time:

1. Codex plans and reviews against accepted ADRs and the current exact Base SHA.
2. An independent Executor implements one immutable Slice Contract.
3. A trusted Git Custodian validates scope and creates the Candidate.
4. Review binds its verdict to the exact Candidate and Evidence Bundle.

The Roadmap is not an implementation work order. No Agent may implement a future Phase directly from Roadmap bullets.

## Contributing and support

Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing a change. Security concerns follow [SECURITY.md](SECURITY.md); general support boundaries are in [SUPPORT.md](SUPPORT.md). Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and [GOVERNANCE.md](GOVERNANCE.md).

## License

Licensed under the [Apache License 2.0](LICENSE).
