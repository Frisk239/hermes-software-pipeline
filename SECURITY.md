# Security Policy

## Project status

Hermes Software Pipeline is pre-release and has no supported runtime version. Design and foundation defects are still security-relevant, especially when they could weaken Agent isolation, authorization, Git protection, evidence integrity, secret handling, installation, or recovery.

## Reporting a vulnerability

Do not disclose a suspected vulnerability in a public issue, pull request, discussion, chat transcript, or Agent prompt.

Preferred reporting path:

1. Use GitHub private vulnerability reporting or a private Security Advisory for `Frisk239/hermes-software-pipeline` when available.
2. If that private channel is unavailable, contact the Repository Governance Owner `Frisk239` through GitHub without including exploit details, credentials, private source, or secret material; request a private coordination channel.

Include only the minimum information needed to reproduce and assess the issue:

- affected revision or exact commit SHA;
- affected platform and configuration;
- security boundary and expected behavior;
- impact and safe reproduction outline;
- whether credentials, user data, Project source, evidence, or Git history may be exposed;
- suggested containment, if known.

Never send live credentials. Replace secrets with explicit canaries and state where redaction occurred.

## Response

The Repository Governance Owner will:

- acknowledge receipt and establish a private tracking channel;
- classify affected assets and authorization boundaries;
- preserve diagnostic evidence without propagating sensitive content;
- coordinate containment, remediation, regression tests, and disclosure;
- rotate or revoke affected credentials outside the repository when necessary.

No fixed response-time SLA is promised before public preview. Status and expected follow-up timing will be communicated through the private channel.

## Supported versions

There are currently no supported releases. A version support table, coordinated disclosure targets, signed security releases, SBOM, provenance, and update instructions must exist before public preview.

## Security boundary

Version 1 will not defend against a malicious host administrator and will not claim VM-grade containment for arbitrary native code. See `docs/security/threat-model-and-trust-boundaries.md` for the complete trust model.
