# Phase-1 F2 frozen validation execution gate

Frozen: 2026-09-22 after the final 191-row continuity contract reached zero
unresolved rows and before any validation return was read.

This document does not create a new selection rule. It binds execution to the
validation rule already frozen in
`docs/research-phase1-feature-tournament-validation-gate.md`.

## Immutable candidate and scope

The only candidate entering validation is:

- family: F2;
- variant: `F2_DIRECT_VS_INDIRECT`;
- preferred group: `INDIRECT_ONLY`;
- complement group: `DIRECT_ONLY`;
- horizon: 126 XNYS sessions.

Confirmation source:
`research-phase1-insider-feature-tournament-confirmation-v1`,
`confirmation-results.json`,
SHA-256
`sha256:5776b17b452c23aaccf481b1484460c9ab8d860187eb554bef31f6a0387d234f`.

Validation-scope source:
`research-phase1-insider-feature-tournament-validation-scope-v1`.

Archive:
`phase1-insider-feature-tournament-validation-scope-v1.tar.gz`,
SHA-256
`sha256:fd95e01b1ca13e08f3cb5baac03dd2f695aded9805bdea5c0a4eb4aaf5a2db16`.

The scope contains 7,493 exact 126-session rows with semantic-key SHA-256
`sha256:8f2d7d09c43689007d22690d8c846cf253532d8cff15997c8def2ddde8df7bc3`.

## Immutable continuity contract

Release:
`research-phase1-insider-feature-tournament-validation-final-continuity-v1`.

Asset:
`validation-final-continuity.json`.

Asset SHA-256:
`sha256:16a9814003c232d58d9e0f70a85b72beb7e37d04c81b390dbd3cfd6199c7956a`.

The contract contains 191 affected rows, zero unresolved rows, and exact
affected-key SHA-256
`sha256:fe81e31a04a4e5f69eb07778685bc8799860eef37653af5479d79c5aefc1c18f`.

The 7,302 ordinary adjusted-price rows remain outside the overlay.

## Frozen terminal-holder valuation

For ordinary rows and `SAME_SECURITY_CONTINUITY`, use one unit of the original
ticker at the exact target adjusted close.

For `SYMBOL_CHANGED_SAME_SECURITY`, use one unit of the contract successor
ticker at the exact target adjusted close.

For `TRANSFORMED_HOLDER_CONSIDERATION`, terminal value is:

`cashPerEntryShare + successor quantity × exact-target successor adjusted close`.

Cash-only mergers use no terminal ticker.

For the exact nine `STOCK_DIVIDEND_QUANTITY` rows, the market corpus already
uses `adjustment=all`. The legal quantity factor remains provenance, but the
market valuation quantity is fixed at 1.0 to prevent double adjustment.

No nearest-bar substitution is allowed. A missing exact target holder bar or
SPY bar remains explicit missingness.

## Frozen validation PASS rule

The candidate validates only if all eight already-predeclared checks are true:

1. preferred mature N >= 150;
2. preferred distinct issuers >= 75;
3. pooled event-weighted 126-session SPY-excess increment > 0;
4. pooled issuer-equal-weight increment > 0;
5. pooled entry-session-equal-weight increment > 0;
6. pooled top-1%-removed increment > 0;
7. 2021 event-weighted increment > 0;
8. 2022 event-weighted increment > 0.

Top-1% removal reuses the exact frozen discovery/confirmation helper semantics.

There is no ADV validation check, no feature reselection, no orientation flip,
no threshold change and no replacement feature.

## Boundary after execution

The validation result may open only the frozen 2021-2022 outcome fields needed
for this decision. It does not authorize production, model fitting, a composite
or 2023+ OOS access.

Regardless of PASS or FAIL:

- `oosOpened=false`;
- `productionScoringChanged=false`;
- no new variant may be added.

A PASS may proceed only to a separately frozen post-validation/OOS gate. A FAIL
ends this frozen tournament version without replacement.
