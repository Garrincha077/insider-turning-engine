# Phase-1 current status — 2026-09-20

This is the compact live checkpoint. For operational continuation,
`docs/HANDOFF.md` remains authoritative. Older dated progress files are audit
history.

## Benchmark family

| Benchmark | Meaning | Current state |
| --- | --- | --- |
| B0 | any qualified open-market purchase | development descriptive complete |
| B1 | canonical CMP opportunistic purchase | continuity-corrected development/robustness complete; HAC/OOS blocked |
| B2 | independent-owner cluster | development complete |
| B3 | company net buying | final 264/264 continuity contract complete; corrected development gate next |
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

## Active next gate

Freeze and implement B3 continuity-corrected development performance before
opening corrected outcomes.

Required rules:

1. consume only the immutable final continuity contract;
2. keep development cohort 2016-2020 and outcome ceiling 2022-12-31;
3. keep exact 21/63/126/252 XNYS targets, 126 primary;
4. never substitute a later market bar for a missing exact target session;
5. preserve holder quantities/cash exactly from the contract;
6. value every component of a multi-component basket at the exact target
   session or mark it incomplete;
7. keep 2023+ sealed and production scoring unchanged;
8. reapply the already frozen robustness semantics after corrected development
   results, with no retuning.

HAC/OOS remains blocked unless the corrected frozen robustness gate later
permits progression.
