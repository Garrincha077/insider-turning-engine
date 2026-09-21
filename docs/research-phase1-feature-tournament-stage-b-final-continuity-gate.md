# Phase-1 feature tournament Stage-B final continuity contract gate

Frozen: 2026-09-21 after all performance-blind continuity research stages
completed and before feature-tournament discovery outcomes are opened.

## Purpose

Merge every Stage-B continuity decision into one immutable 210-row resolution
contract and prove exact coverage of the original frozen unresolved scope.

This is the final performance-blind gate.

## Frozen source scope

Release:
`research-phase1-feature-tournament-stage-b-unresolved-scope-v1`.

Asset:
`stage-b-unresolved-scope.json`.

SHA-256:
`sha256:4882e009646ea117d123b5f95ae41ea700203dd470d3b24be2cd1592eebe9afd`.

Rows: **210**.

## Resolution groups

The final union must contain exactly:

- **175** safe prior-evidence economic matches;
- **1** POPE primary-evidence adjudication;
- **17** exact provider-action resolutions;
- **7** exact-gap evidence-equivalence resolutions;
- **10** new primary-SEC resolutions.

Total: **210**.

No row may occur in more than one group and no source-scope key may be missing.

## Immutable resolution sources

### Prior overlap v2

- release:
  `research-phase1-feature-tournament-prior-continuity-overlap-v2`;
- asset: `prior-continuity-overlap-v2.json`;
- SHA-256:
  `sha256:1a67ed7d265f8d2d073c5a717cf5aed897f6ee86d6f3287e6056fd8261121741`;
- safe rows: 175.

For each safe row the merger must reconstruct the full original B1/B3 evidence
row rather than trusting only the summarized overlap fingerprint.

B3 is preferred when the same historical key exists in both B1 and B3; B1 is
used when it is the only frozen prior source. The selected original row must
reproduce the exact overlap economic fingerprint and schema labels.

### B1 frozen continuity

Repository:
`research/b1-security-continuity-resolution-v1.json`.

SHA-256:
`sha256:88325d71dd9da1f18bdc2c2695933860e087addd586def8b4271ed768d121430`.

### B3 final continuity

- release: `research-phase1-b3-final-continuity-contract-v1`;
- asset: `b3-final-continuity-contract.json`;
- SHA-256:
  `sha256:22e1af6713eb0c0f73604a150787ac9248f044eef63e1f88b70b31697aede163`.

### POPE

- release:
  `research-phase1-feature-tournament-pope-adjudication-v1`;
- asset: `pope-adjudication.json`;
- SHA-256:
  `sha256:8c87c27a3689c1aa10c5d8881cf91de0bb078e97d6133968f1c7d0528afd18a4`.

### Provider17

- release:
  `research-phase1-feature-tournament-provider17-resolution-v1`;
- asset: `provider17-resolution.json`;
- SHA-256:
  `sha256:b439ff00ab99fb77dd81f929d078a9e1f4966bcc3800f4a21896700c1efc99c9`.

### Long-gap7

- release:
  `research-phase1-feature-tournament-long-gap7-resolution-v1`;
- asset: `long-gap7-resolution.json`;
- SHA-256:
  `sha256:45422f3d291ce188005eeaddd9e6dac4ad440d9a27324809fbf36ed118ad9e67`.

### New-primary10

- release:
  `research-phase1-feature-tournament-new-primary10-resolution-v1`;
- asset: `new-primary10-resolution.json`;
- SHA-256:
  `sha256:0062bf09ee7dc882e0b1d2829aa165ea6b9d34db14705716d3f5941cd89897d3`.

## Multi-component preservation rule

The overlap contains exactly one safe prior multi-component row:

- current event: 23611;
- ticker: `NBA.U`;
- horizon: 252;
- result:
  `TRANSFORMED_MULTI_COMPONENT_CONSIDERATION`;
- basket components:
  - MIMO common stock;
  - MIMO WS public warrant.

The final merger must reconstruct that original B3 basket and fail if the
basket disappears, is collapsed to one symbol or changes component identity.

## Required final invariants

The final contract must prove:

- source unresolved rows = 210;
- classified rows = 210;
- unresolved rows = **0**;
- 210 unique current event-horizon keys;
- exact current key-set equality with the frozen Stage-B unresolved scope;
- source group counts = 175 + 1 + 17 + 7 + 10;
- every row has a non-empty resolution decision and result state;
- the NBA.U multi-component basket remains intact;
- performanceRead=false;
- priceFieldsRead=[];
- featureOutcomesRead=false;
- validationOpened=false;
- oosOpened=false;
- productionScoringChanged=false.

## Progression rule

Only after this contract is published successfully may feature-tournament
**discovery** outcomes be opened.

That permission does not open validation or OOS:

- discovery/development feature outcomes may be opened only under the already
  frozen tournament design;
- 2021-2022 validation remains selection-blind until the discovery selection is
  frozen;
- 2023+ OOS remains sealed;
- production scoring remains unchanged.
