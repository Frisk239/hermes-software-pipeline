# Slice 01-01 Closeout — Domain Kernel

Status: `ACCEPTED`

Contract revision: `2`

Base SHA: `e778a5246c4bec3f6a54aec2fdb315ab66ca756e`

Candidate SHA: `d193e30639fd7c1dc779f0659f4a285a87373a24`

Integrated SHA: `cdf0872078151af8b4f84319c4a30c196bdbc8e3`

Pull Request: [#20 — feat: add fake-pipeline domain kernel](https://github.com/Frisk239/hermes-software-pipeline/pull/20)

Closed: 2026-08-13

## Accepted capability

- pure `apply(state, command)` for fake Pipeline states `UNCONFIRMED` / `OPEN` / `REJECTED`;
- empty input → `EMPTY_REQUIREMENT`; illegal transition → `INVALID_TRANSITION`; no event, state unchanged;
- `Clock` Protocol exists and is unused by `apply`;
- `counter_spike` unchanged.

## Evidence

- review `PASS` bound to `5d4b80d`; CI flake fix `d193e30`;
- PR #20 merged as `cdf0872078151af8b4f84319c4a30c196bdbc8e3`.

## Residual debt

- domain is not persisted; 01-02 must rewrite 00-04 SQLite onto this aggregate;
- `clock.py` imports `datetime` via the package re-export.

## Next prerequisites

- Slice 01-02 Base is `cdf0872078151af8b4f84319c4a30c196bdbc8e3`.
