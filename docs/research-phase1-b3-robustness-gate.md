# Phase-1 B3 dependence and tail-robustness gate

Status: **FROZEN BEFORE B3 ROBUSTNESS EXECUTION**  
Date: **2026-09-20**  
Scope: development-only diagnostics on the already persisted canonical B3
development outcome series.  
Validation: unopened.  
2023+ OOS: sealed.  
Production scoring: unchanged.

## Why this gate exists

The first B3 development run is descriptive and shows the familiar Phase-1
right-skew pattern: a positive arithmetic SPY-excess mean with a negative
median and sub-50% win rate at the primary 126-session horizon.

The response is **not** to tune the B3 net-buying rule.

This gate applies the exact diagnostic arithmetic and warning thresholds that
were already frozen for B1 in
`docs/research-phase1-b1-robustness-gate.md`.

No B3-specific warning threshold is selected from the observed B3 result.

## Frozen source

Only this B3 development source is permitted:

- workflow run: `35502095184`;
- release: `research-phase1-b3-development-v1`;
- asset: `b3-development-descriptive-2016-2020.tar.gz`;
- asset SHA-256:
  `d90a2f08483d6710bb2f2715fa9049b64fd27a3979e7e63e5fb792f3c0274ae7`;
- source status: `PHASE1_B3_DEVELOPMENT_DESCRIPTIVE_COMPLETE`;
- source coverage tier: `C_EXPLORATORY`.

No new SEC history, market history, validation result or OOS evidence may enter
this diagnostic.

## Diagnostic families

Use the already-frozen B1 semantics unchanged.

### A — tail concentration

For 21/63/126/252 mature SPY-excess outcomes report:

- untrimmed mean, median, win rate;
- 1% and 5% two-sided trimmed means;
- top-1%-removed and top-5%-removed means;
- P01/P05/P95/P99;
- positive-tail contribution shares for top 1%/5%/10%;
- ten-largest-winners share of signed excess.

### B — issuer dependence, primary 126

Equal-weight each issuer's mean mature `excess_126`. Report mean, median, win
rate and event-count concentration.

### C — entry-session dependence, primary 126

Equal-weight the mean mature `excess_126` for each entry session. Report mean,
median, win rate and signal-count concentration.

This is **not** a daily calendar-time portfolio.

### D — development-year stability, primary 126

Using evaluation-session year 2016–2020 report N, mean, median and win rate,
positive-mean/median year counts and max-minus-min mean spread.

No year may be excluded because its result is inconvenient.

## Warning conditions — copied unchanged from B1

A blocking warning exists if **any** of these is true:

- 126-session issuer-equal-weight mean <= 0;
- 126-session entry-session-equal-weight mean <= 0;
- 126-session top-1%-removed mean <= 0;
- fewer than 3 of 5 development years have positive 126-session mean excess;
- top 1% of positive-return observations contribute >=50% of aggregate positive
  excess.

Absence of warnings does not establish alpha. It only permits freezing a
separate daily-path calendar-time/HAC design.

If any warning is present:

- progression = `BLOCK_HAC_AND_OOS`;
- validation remains unopened;
- 2023+ remains sealed;
- B3 must not be retuned from this result.

## Required output flags

- `researchOnly=true`;
- `formalAlphaClaim=false`;
- `oosEligible=false`;
- `calendarTimeHacStageOpened=false`;
- `validationPerformanceComputed=false`;
- `oosOpened=false`;
- `productionScoringChanged=false`;
- `b3DefinitionChanged=false`.
