# Phase-1 feature tournament residual34 evidence audit gate

Frozen: 2026-09-21 after the exact 34-row post-POPE residual scope was
published and before any feature outcome was opened.

## Purpose

This stage does not classify returns and does not apply continuity resolutions.
It only asks whether each residual34 row already has reusable frozen
performance-blind evidence at one of two narrower levels:

1. exact corporate-action identity; or
2. same issuer + same historical security with a unanimous frozen B3
   continuity fingerprint.

The second class is only a **candidate** for reuse and must still pass
date/security coverage before it can be applied.

## Immutable residual34 source

- release: `research-phase1-feature-tournament-residual34-scope-v1`;
- asset: `residual34-scope.json`;
- SHA-256:
  `sha256:2e1642f23add5de232488b0bb4d657b7e4a95a42256ead8f1bfa78a5775550fe`;
- rows: **34**;
- unique issuer events: **19**;
- unique issuers/tickers: **14**;
- source split: 17 provider + 17 long-internal-gap.

The Stage-B unresolved audit is also pinned only to recover the already-frozen
corporate-action IDs and gap diagnostics for these same rows:

- release:
  `research-phase1-feature-tournament-stage-b-unresolved-scope-v1`;
- asset: `stage-b-unresolved-scope.json`;
- SHA-256:
  `sha256:4882e009646ea117d123b5f95ae41ea700203dd470d3b24be2cd1592eebe9afd`.

## Frozen prior evidence

B3 final continuity contract:

- release: `research-phase1-b3-final-continuity-contract-v1`;
- asset: `b3-final-continuity-contract.json`;
- SHA-256:
  `sha256:22e1af6713eb0c0f73604a150787ac9248f044eef63e1f88b70b31697aede163`;
- 264 / 264 classified;
- zero unresolved;
- performanceRead=false.

B1 frozen continuity resolution:

- repository file: `research/b1-security-continuity-resolution-v1.json`;
- SHA-256:
  `sha256:88325d71dd9da1f18bdc2c2695933860e087addd586def8b4271ed768d121430`;
- 54 rows;
- performanceRead=false.

## Audit rules

### Provider rows

An action-level reuse candidate requires:

- same issuer CIK;
- same historical ticker;
- exact same frozen corporate-action ID set.

B3 has priority when such an exact action identity exists because its final
contract preserves richer normalized economic terms.

B1 may be used as an action-level fallback only for
`STOCK_DIVIDEND_QUANTITY`. No merger/election semantics may be inferred from
a B1 row merely because the issuer is the same.

### Long-gap rows

A long-gap row becomes only a `LONG_GAP_PRIOR_SECURITY_CANDIDATE` when:

- issuer CIK matches;
- historical ticker matches;
- all matching B3 rows have one unanimous normalized economic fingerprint.

This is not yet a resolution. The next stage must prove that the frozen B3
primary documents cover the residual row's actual gap interval/security
identity.

## Frozen audit partition

The performance-blind audit is expected to partition the 34 rows as follows:

- **16** `PROVIDER_ACTION_REUSE_B3`;
- **1** `PROVIDER_ACTION_REUSE_B1_STOCK_DIVIDEND`;
- **7** `LONG_GAP_PRIOR_SECURITY_CANDIDATE`;
- **10** `LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED`.

Therefore:

- provider action-level reusable candidates: **17 / 17**;
- long-gap prior-security candidates: **7 / 17**;
- rows requiring genuinely new primary evidence: **10**.

The ten new-primary rows are expected only in:

- HMG: 2 rows;
- OAS: 3 rows;
- AVGR: 3 rows;
- SNES: 2 rows.

These counts are evidence-coverage facts, not performance-selected thresholds.

## Progression boundary

This stage is audit-only:

- no continuity resolution is applied;
- no return/excess-return/MAE field is read;
- no feature discovery outcome is opened;
- validation remains untouched;
- 2023+ OOS remains sealed;
- production scoring remains unchanged.

After a successful audit, the next authorized step is to resolve the 17 exact
provider-action rows and independently validate date/security coverage for the
7 long-gap prior-security candidates. Only the irreducible 10-row scope should
require new primary-source research.
