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

## Repository checks

The bootstrap checks are dependency-free and fully offline. Run them from the repository root on Windows or Linux:

```text
python scripts/check_documentation.py
python scripts/check_schemas.py
python scripts/check_schemas.py --self-test-negative
python scripts/check_documentation.py --check-workflow
```

`scripts/check_documentation.py` validates governed text files: strict UTF-8 decoding, absence of replacement characters, balanced Markdown fences, resolvable local Markdown links confined to the repository root, terminal ADR status in `docs/adr/`, and the required root entry point files. `scripts/check_schemas.py` validates every committed Schema: JSON parsing, unique `$id` values under `https://schemas.hermes-pipeline.dev/`, resolution of every local or absolute `$ref` and JSON Pointer fragment, and an exact match of the declared `$id` set against the locked 14 bootstrap Schemas. Full Draft 2020-12 meta-schema validation is owned by slice-00-03. `--check-workflow` parses the workflow YAML with a strict grammar (rejecting unparsed trailing content, unterminated quotes, and unknown constructs) and verifies read-only `permissions: contents: read`, no persisted checkout credentials, an exact `matrix.os` axis bound to `runs-on: ${{ matrix.os }}`, and exactly the required offline commands on both Windows and Linux. `--self-test-negative` executes the checkers against deliberately broken fixtures, asserting stable nonzero exits, and all diagnostic output is sanitized and bounded.

Line endings are normalized to LF by the [.gitattributes](.gitattributes) policy, and CI runs the same commands on Windows and Linux via [documentation-contracts.yml](.github/workflows/documentation-contracts.yml).

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
