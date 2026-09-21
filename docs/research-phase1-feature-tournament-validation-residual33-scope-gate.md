# Phase-1 F2 validation residual-33 continuity scope gate

Frozen: 2026-09-21 after immutable exact-action prior-evidence resolution and
before any validation outcome is read.

## Inputs

Prior-evidence audit:
- release: `research-phase1-insider-feature-tournament-validation-prior-evidence-v1`;
- asset: `validation-prior-evidence-audit.json`;
- SHA-256:
  `sha256:6d261d773a47b311b18827fece4307105788be17ac6ece16d38daa4b27974361`.

Exact-action resolution:
- release:
  `research-phase1-insider-feature-tournament-validation-exact-action-resolution-v1`;
- asset: `validation-exact-action-prior-resolution.json`;
- SHA-256:
  `sha256:6e238d29f9e8a31b388b84cb5f11964079f81b68985b44cf28b290e1fbb29bdc`;
- resolved rows: 8;
- resolved semantic-key SHA-256:
  `sha256:fbd00d6952afad146499ae0cc998c1c79bee8ab15084eae4bdd45899bab8cb34`.

## Frozen subtraction rule

Start from all 41 rows in the immutable prior-evidence audit and subtract only
the exact 8 semantic keys present in the immutable exact-action resolution.

No category, ticker, date, action ID, gap value or evidence label may be edited
during subtraction.

Expected residual:
- rows: **33**;
- semantic-key SHA-256:
  `sha256:9ee5091b18344e67b58fe567b92ce99d3f923e4df2829af935158947bdcae2a2`.

Frozen residual categories:
- `PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED`: **22**;
- `LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED`: **10**;
- `LONG_GAP_PRIOR_SECURITY_CANDIDATE`: **1**.

There must be zero
`PROVIDER_EXACT_ACTION_PRIOR_CANDIDATE` rows after subtraction.

## Next evidence split

The one prior-security long-gap candidate is HSDT. It is not resolved by this
scope freeze. It requires an interval-specific evidence audit against the exact
validation gap dates.

The remaining 32 rows require new primary evidence and should be processed in
target-specific waves. Same ticker, same issuer or same SPAC family does not
itself establish continuity.

## Boundary

This scope is performance-blind:
- researchOnly=true;
- performanceRead=false;
- priceFieldsRead=[];
- featureOutcomesRead=false;
- validationOpened=false;
- validationPerformanceOpened=false;
- oosOpened=false;
- productionScoringChanged=false.

Validation performance remains blocked until residual continuity is zero.
