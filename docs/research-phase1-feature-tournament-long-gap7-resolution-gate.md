# Phase-1 feature tournament long-gap7 evidence-equivalence gate

Frozen: 2026-09-21 after exact Stage-B gap diagnostics and provider17
resolution, before any feature outcome is opened.

## Purpose

Resolve the seven `LONG_GAP_PRIOR_SECURITY_CANDIDATE` rows only when the
current Stage-B gap can be tied to the *same frozen evidence event* used in an
earlier B1/B3 continuity decision.

Same issuer/ticker by itself is insufficient.

## Immutable inputs

### Long-gap17 scope

- release: `research-phase1-feature-tournament-provider17-resolution-v1`;
- asset: `long-gap17-scope.json`;
- SHA-256:
  `sha256:c3ce1962084cedb419d89eb2b764ab070c6e4d368be5e1e18599770e6727728d`;
- rows: 17;
- prior-security candidates: 7;
- new-primary rows: 10.

### Stage-B exact gap diagnostics

- release:
  `research-phase1-feature-tournament-stage-b-gap-diagnostics-v1`;
- asset: `gap-diagnostics.csv`;
- SHA-256:
  `sha256:7d0bdd8e6fa4fa43ab4d7ee731a8cb00380659a89d3b2626a472ea7d0fb73afa`;
- exact unresolved long-gap rows: 155;
- priceFieldsRead=[].

### B3 final continuity

- release: `research-phase1-b3-final-continuity-contract-v1`;
- asset: `b3-final-continuity-contract.json`;
- SHA-256:
  `sha256:22e1af6713eb0c0f73604a150787ac9248f044eef63e1f88b70b31697aede163`.

### B1 continuity and gap diagnostics

- B1 resolution SHA-256:
  `sha256:88325d71dd9da1f18bdc2c2695933860e087addd586def8b4271ed768d121430`;
- B1 gap diagnostics run: `35272945732`;
- artifact: `phase1-security-gap-diagnostics-35272945732`;
- artifact digest:
  `sha256:f203552b0b52e51ec91338827ea8d87b2989fe5bbe462a4e36b3862f36ccee08`.

### One-sided primary evidence

Repository contract:
`research/b3-one-sided-primary-evidence-v1.json`.

Frozen Git blob:
`fe31929752fd0f7567455cf1bda3fbc35b06a69f`.

## Identity-specific validation rules

### CKX — 4 rows

CKX may resolve as same-security continuity only if the exact Stage-B
`firstMissingSession` equals a frozen B3
`SEC_MULTI_SOURCE_EXACT_CONTINUITY` pivot for the same issuer/ticker and the
same normalized economics.

Expected pivots:

- event 4257 / 252: **2017-06-19**;
- event 23173 / 63, 126, 252: **2020-11-04**.

The earlier B3 multisource rule required matching P/S ticker observations,
matching security-title sets and matching Form 3/4/5 ticker observations on
both sides of that exact pivot.

### NSEC — 1 row

Event 18896 / 252 must have exact Stage-B gap pivot
**2020-07-17**, matching a frozen B3
`SEC_MULTI_SOURCE_EXACT_CONTINUITY` row for CIK 0000865058 / NSEC.

### CMCT — 1 row

Event 18535 / 252 must reproduce the entire frozen B1 gap tuple:

- previous observed: 2020-07-20;
- first missing: 2020-07-21;
- last missing: 2020-08-14;
- next observed: 2020-08-17;
- missing sessions: 19.

The B1 contract must independently contain same-security CMCT continuity with
the same gap size and 1:1 / zero-cash terms.

### LOV — 1 row

Event 4603 / 252 is not treated as same-security continuity. The frozen primary
SEC evidence must show the 2017-11-02 ADS exchange:

- old Spark Networks, Inc. common share;
- 0.1 Spark Networks SE ADS per old common share;
- successor ADS ticker LOV;
- successor issuer CIK 0001705338.

The Stage-B exact gap must show **2017-11-02 as the last observed old-security
session**, with the gap beginning on 2017-11-03.

## Expected output

Exactly seven resolutions:

- CKX: 4;
- CMCT: 1;
- LOV: 1;
- NSEC: 1.

Exactly ten rows remain, all requiring new primary evidence:

- AVGR: 3;
- HMG: 2;
- OAS: 3;
- SNES: 2.

## Progression boundary

After successful long-gap7 resolution:

- 175 safe prior-evidence rows resolved;
- 1 POPE row adjudicated;
- 17 provider-action rows resolved;
- 7 exact-gap evidence-equivalence rows resolved;
- **200 / 210** continuity rows deterministically classified;
- exactly **10 / 210** remain unresolved.

No feature outcome, validation outcome or 2023+ OOS value may be opened until
those final ten rows are resolved and the merged Stage-B continuity contract
reports zero unresolved.
