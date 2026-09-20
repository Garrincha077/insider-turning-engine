# Phase-1 B3 residual-43 continuity checkpoint — 2026-09-20

## Status

The multi-class/reorganization primary-source gate is complete and green, and
the exact remaining continuity work queue is frozen at 43 rows.

### Multi-class/reorganization resolution

- workflow run: **35508859857** — SUCCESS
- release: `research-phase1-b3-multiclass-reorg-primary-resolution-v1`
- asset: `b3-multiclass-reorg-primary-resolution.json`
- asset SHA-256:
  `sha256:a844ea830b9503a045b55a490c30b9e3cd77456974b741a696f16617caf75969`
- resolution-key SHA-256:
  `sha256:d9103eb5d9b5e04e18f955f4f6361ba39932ad285dff823a1046f72b613c2e91`
- resolved rows: **12**

Frozen decisions:

- GGO: 8 same-security common-share rows
- TAGS: 1 same-series security row
- EAGL: 2 one-for-one same-security domestication/symbol-change rows to WSC
- FMCIU: 1 `DISCONTINUOUS_NO_COMPLETE_VALUATION` row because the unit
  separated into multiple economic legs including a warrant not representable
  by the frozen successor-share-plus-cash schema

Decision totals:

- `SAME_SECURITY_CONTINUITY`: 9
- `SYMBOL_CHANGED_SAME_SECURITY`: 2
- `DISCONTINUOUS_NO_COMPLETE_VALUATION`: 1

### Residual-43 scope

- workflow run: **35508922204** — SUCCESS
- release: `research-phase1-b3-residual43-scope-v1`
- asset: `b3-residual43-scope.json`
- asset SHA-256:
  `sha256:eeb929e959cfe606764d251ad9f9a262c80336e79f395a6c701b84fdbed4cbe3`
- rows: **43**
- issuer/tickers: **19**
- residual-key SHA-256:
  `sha256:be82164c63ed8c8528017ff3201d5172e818655e5c7a8fa48bd7576c7cb02cd6`

## Aggregate continuity progress

Starting unresolved event-horizon rows: **264**.

Deterministically classified/candidate rows now: **221 / 264**.

Remaining unresolved: **43 / 264**.

Corrected B3 performance remains closed.

## Residual-43 structure

Largest issuer/ticker counts:

- PAVM: 6
- TWLVU: 4
- UNAM: 3
- APDN: 3
- HSDT: 3
- ARWA: 3
- AAPC: 3
- WYIG: 3
- SGBX: 2
- ATACU: 2
- TZACU: 2
- ZGYHU: 2
- CYCC, LMFA, TPGE, GIG.U, LOACU, SRACU, NBA.U: 1 each

The remaining cases split broadly into:

1. SPAC/unit life-cycle cases requiring target-specific primary evidence;
2. ordinary/common-share cases where ticker evidence persists but SEC security
   title strings overlap/change around a market-data gap.

No generic same-ticker or same-CIK rule is permitted.

## Guardrails

- development cohort 2016-2020
- evidence/outcomes through 2022 only
- 2023+ OOS sealed
- horizons 21/63/126/252 unchanged, 126 primary
- `performanceRead=false`
- `priceFieldsRead=[]`
- `oosOpened=false`
- `productionScoringChanged=false`
- final continuity contract not created
- corrected performance closed
