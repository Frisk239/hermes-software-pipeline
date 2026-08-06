# Hermes Software Pipeline

Hermes Software Pipeline is a planned Hermes plugin and managed local runtime for carrying one software requirement through confirmed intake, independent product and architecture planning, constrained implementation, isolated verification, and a protected pull-request merge.

## Status

**Design baseline in preparation — no runnable product exists yet.**

The architecture and version 1 technology decisions are accepted. Phase 00 has established the repository baseline, the managed Python quality skeleton (`hermes-pipeline` 0.1.0 under Python 3.12 and uv 0.12.1), and the contract toolchain: the 14 bootstrap JSON Schemas, the OpenAPI catalog, and the compatibility registry are generated deterministically from versioned Pydantic v2 authoring types, with a read-only drift gate proving the committed projections match generation byte-for-byte. The Hermes Shim, platform-security feasibility, and remaining Phase 00 slices are still pending. Do not install this repository expecting production Pipeline behavior.

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
python scripts/check_documentation.py --check-workflows
python scripts/check_repository_artifacts.py
```

`scripts/check_documentation.py` validates governed text files: strict UTF-8 decoding, absence of replacement characters, balanced Markdown fences, resolvable local Markdown links confined to the repository root, terminal ADR status in `docs/adr/`, and the required root entry point files. Governed-file discovery honors the checked root's `.gitignore`, so ignored local content (`reference/` clones, `.venv`, and standard tool caches) is never scanned while unignored governed files still are. `scripts/check_schemas.py` is the untouched dependency-free bootstrap gate: JSON parsing, unique `$id` values under `https://schemas.hermes-pipeline.dev/`, resolution of every local or absolute `$ref` and JSON Pointer fragment, and an exact match of the declared `$id` set against the locked 14 bootstrap Schemas. `--check-workflows` parses both committed workflow files with a strict grammar (rejecting unparsed trailing content, unterminated quotes, and unknown constructs) and verifies read-only permissions, no persisted checkout credentials, exact Windows/Linux matrix binding, the frozen quality-command inventory, and the bundled-Node policy. `--self-test-negative` executes the checkers against deliberately broken fixtures, asserting stable nonzero exits, and all diagnostic output is sanitized and bounded. `scripts/check_repository_artifacts.py` fails if verification leaves bytecode or tool-cache artifacts in the source tree.

The managed Python 3.12 environment (ADR-0020) is frozen in `uv.lock`; the canonical quality checks are:

```text
uv sync --frozen --all-groups
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv run python -m hermes_pipeline.cli contracts check
uv run python -m hermes_pipeline.cli contracts drift-check
uv run python -m hermes_pipeline.cli architecture check
```

`contracts check` is the full read-only validator: the 14-Schema identity lock, Draft 2020-12 meta-validation, `$ref` closure, instance validation with the FORMAT_CHECKER, the f36 baseline corpus three-way gate (immutable snapshots, strict Pydantic models, generated Schemas), OpenAPI and compatibility-registry checks, canonical-hash verification, and a canary-leak scan. `contracts drift-check` regenerates every projection into a temporary directory and byte-compares it with the committed files; `contracts generate` is the only command that writes the generated artifacts, and the toolchain is lazy-imported only after the `contracts` subcommand is parsed, so `--version` and the normal runtime path stay pure standard library. `scripts/check_schemas.py` remains the dependency-free bootstrap gate and a consistency test keeps both validators aligned. `architecture check` runs the standard-library AST import-boundary checker against `src/hermes_pipeline` (stable file/line/rule diagnostics, no `import-linter`). Those default repository checks intentionally require a Hermes Pipeline source checkout; a standalone installed console supports `--version`, and `architecture check --root <path>` remains explicit-path capable. Pyright uses its lockfile-provided `nodejs-wheel-binaries` runtime instead of ambient Node. CI sets `PYTHONDONTWRITEBYTECODE=1` for every verification process so the final artifact audit observes the source tree rather than bytecode generated by the verifier. After the environment is installed, the same checks rerun offline (for example `uv sync --frozen --all-groups --offline` and `uv run --offline python -m hermes_pipeline.cli --version`) with no credentials and no further network access.

Line endings are normalized to LF by the [.gitattributes](.gitattributes) policy. CI runs the bootstrap checks on Windows and Linux via [documentation-contracts.yml](.github/workflows/documentation-contracts.yml) and the canonical quality checks via [python-quality.yml](.github/workflows/python-quality.yml).

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
