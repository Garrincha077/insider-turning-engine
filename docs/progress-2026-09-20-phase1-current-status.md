# Phase-1 current status — 2026-09-21

This is the compact live checkpoint. For operational continuation,
`docs/HANDOFF.md` remains authoritative. Older dated progress files are audit
history.

## Benchmark family

| Benchmark | Meaning | Current state |
| --- | --- | --- |
| B0 | any qualified open-market purchase | development descriptive complete |
| B1 | canonical CMP opportunistic purchase | continuity-corrected development/robustness complete; HAC/OOS blocked |
| B2 | independent-owner cluster | development complete |
| B3 | company net buying | continuity-corrected development + corrected robustness complete; BLOCK_HAC_AND_OOS |
| B4 | B1 AND B2 exact-session intersection | development complete |

## B3 data / development status

- original P/S PIT history: **40/40 quarters PASS**
- lifecycle reconciliation: **PASS**
- effective qualified P/S rows end-2022: **1,570,066**
- B3 definition: frozen before performance
- raw candidates 2016-2020: **147,164**
- exact-XNYS dedup retained events: **35,829**
- PIT identity eligible: **34,472**
- uncorrected B3 development run: **35502095184**
- exact-entry matched: **29,930**
- coverage tier: **C_EXPLORATORY**
- 126-session SPY excess mean / median: **+4.09% / -2.73%**
- 126-session win rate: **44.84%**

## Frozen uncorrected robustness

Run **35502779482**:

- event-weighted 126d mean: **+4.0915%**
- issuer equal-weight mean: **+5.0763%**
- entry-session equal-weight mean: **+3.4260%**
- positive-mean years: **3 / 5**
- top-1%-removed mean: **-0.1974%**
- progression: **BLOCK_HAC_AND_OOS**

Do not retune this rule after observing the result.

## B3 continuity resolution — COMPLETE

The original frozen continuity problem contained **264** unresolved
event-horizon rows.

Final residual resolution run **35540472056**:

- resolved final residual: **13 / 13**
- unresolved after gate: **0**
- release: `research-phase1-b3-final-residual13-resolution-v1`

Final continuity contract run **35540610883**:

- status: **SUCCESS**
- source unresolved rows: **264**
- classified rows: **264**
- unresolved rows: **0**
- classified/frozen-scope key SHA-256:
  `sha256:6125fe42a9559ce937d385b4f49d1a74d33ce1caad7f5ec8487ce72bf854082b`
- release: `research-phase1-b3-final-continuity-contract-v1`
- asset SHA-256:
  `sha256:22e1af6713eb0c0f73604a150787ac9248f044eef63e1f88b70b31697aede163`
- finalResolutionContractCreated: **true**
- correctedPerformanceOpened: **false**

Classification counts:

- same security: **180**
- symbol changed, same security: **11**
- transformed holder consideration: **71**
- transformed multi-component consideration: **1**
- discontinuous/no complete valuation: **1**

See `docs/progress-2026-09-20-b3-continuity-complete.md`.

## B3 continuity-corrected development — COMPLETE

Run **35634832574** — SUCCESS.

- release: `research-phase1-b3-continuity-corrected-development-v1`
- asset SHA-256:
  `sha256:b7b058a2e82cb072876804178e9af6e247fa9dc70b6f93a3f3c8e32ffe67c8be`
- exact-entry events: **29,930**
- event-horizon rows: **119,720**
- continuity-contract rows applied: **264**
- 126d matured: **29,072**
- 126d SPY excess mean / median: **+4.0286% / -2.7248%**
- 126d win rate: **44.8473%**
- corrected MAE recomputation: **false**
- 2023+ OOS: **sealed**
- production scoring: **unchanged**

## B3 continuity-corrected robustness — BLOCK_HAC_AND_OOS

Run **35635187501** — SUCCESS.

- event-weighted 126d mean: **+4.0286%**
- issuer equal-weight mean: **+5.0390%**
- entry-session equal-weight mean: **+3.3464%**
- positive-mean years: **3 / 5**
- top-1%-removed mean: **-0.2021%**
- blocking warning:
  `top1PctRemovedMeanNonPositive=true`
- progression: **BLOCK_HAC_AND_OOS**
- robustness semantics changed: **false**

The continuity correction does not change the substantive B3 robustness
conclusion.

See
`docs/progress-2026-09-21-b3-corrected-development-robustness.md`.

## Active next gate

Synthesize the completed B0/B1/B2/B3/B4 development benchmark family, then
freeze the insider-only feature-tournament methodology **before** reading any
new feature performance.

The feature-tournament gate must predeclare candidate features, transforms,
missingness, deduplication, comparison/stability metrics, multiple-testing
control and selection rules. Turning/technical confirmation remains a later,
separate incremental layer.

HAC/OOS remains blocked. 2023+ remains sealed.

