# Governance

## Initial model

Hermes Software Pipeline uses a single-maintainer governance model during its foundation phase.

The initial Repository Governance Owner is the GitHub identity `Frisk239`. This identity is accountable for:

- accepting, rejecting, or superseding architecture decisions;
- approving Engineering Phase Plans and material Phase Closeouts;
- maintaining repository settings, protected-branch policy, and release authority;
- coordinating security response and appointing additional maintainers;
- recording any transfer or delegation of governance authority.

The designation is a repository accountability record. It does not require a new login flow, grant a runtime role, or authorize the Pipeline to use the owner's browser session, OAuth grant, personal access token, SSH key, or Git credential.

## Runtime separation

Human repository administration uses GitHub's normal authenticated user interface or an explicitly operated local GitHub CLI session. Automated remote delivery, when implemented, uses a separately installed least-privilege GitHub App as defined by the accepted architecture. The GitHub App cannot approve or merge its own changes, bypass branch protection, or inherit the Repository Governance Owner's personal authority.

## Decision process

Hard-to-reverse architecture, security, dependency-family, licensing, governance, and product-scope changes require an accepted ADR or an equivalent recorded governance decision. Routine implementation decisions remain within an approved Phase Plan and Slice Contract.

Changes to governance must be reviewed by the current Repository Governance Owner and recorded in this file. If the owner is unavailable, repository-host ownership and applicable organizational policy determine recovery; the software runtime cannot appoint a replacement.

## Future delegation

Before accepting external maintainers or a public preview, this model must be expanded with:

- maintainer admission and removal criteria;
- required review counts and protected-branch settings;
- release and security-response roles;
- conflict-of-interest and recusal rules;
- a succession and inactivity policy.
