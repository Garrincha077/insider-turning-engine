# Phase-1 B1 continuity-corrected dependence and tail-robustness gate

Frozen: 2026-09-17, after the performance-blind security-continuity resolution reached zero unresolved rows and after the first continuity-corrected B1 performance artifact was persisted, but **before running any robustness diagnostic on the corrected outcome series**.

This gate does not introduce new thresholds. It reapplies, unchanged, the already frozen diagnostic and warning semantics from `docs/research-phase1-b1-robustness-gate.md` to the continuity-corrected B1 outcome series. The purpose is to determine whether security-identity/holder-basis correction changes the earlier dependence/tail warning state without selecting a new test after seeing the corrected mean.

## Frozen source

The only corrected-performance source authorized for this gate is:

- GitHub Actions run `35277369958`;
- artifact `phase1-b1-continuity-corrected-performance-35277369958`;
- artifact digest `sha256:d750c85b6019740ad381b2f53a9d6ceb379a5665cf8b43f0c70e799484bfa775`;
- source status `PHASE1_B1_CONTINUITY_CORRECTED_PERFORMANCE_COMPLETE`;
- source result class `research/descriptive`.

The corrected source itself is downstream of the frozen zero-unresolved continuity artifact from run `35275669277`.

## Boundaries

- B1 signal/event definition: unchanged.
- Development cohort clock: canonical `evaluationSession`, 2016-01-01 through 2020-12-31.
- A valid late-2020 evaluation may have an entry session in 2021.
- Outcomes: through 2022 only.
- 2023+ OOS: sealed and forbidden.
- Horizons: 21 / 63 / 126 / 252 XNYS sessions.
- Primary horizon: 126 sessions.
- `researchOnly=true`.
- `oosOpened=false`.
- `productionScoringChanged=false`.
- No B1/B2/B4 definition may be changed.
- No continuity rule, holder factor, or event may be altered in response to these diagnostics.
- MAE is outside this corrected robustness gate because corrected-performance stage did not recompute MAE.

## Diagnostic semantics — unchanged from the original frozen B1 robustness gate

For corrected SPY-excess outcomes, compute the same four families:

1. **Tail concentration** at every horizon: mean, median, win rate, 1%/5% two-sided trimmed means, top-1%/top-5%-removed means, P01/P05/P95/P99, positive-tail contribution shares, and ten-largest-winners share of signed excess.
2. **Repeated issuer dependence** at 126 sessions: equal-weight each issuer's mean corrected `excess_126`, plus event-count concentration.
3. **Same-entry-session dependence** at 126 sessions: equal-weight each entry-session cohort's mean corrected `excess_126`, plus signal-count concentration.
4. **Development-year stability** using canonical `evaluationSession` year: N/mean/median/win rate for 2016–2020 and counts of positive-mean/positive-median years.

Tail-cut and quantile arithmetic must be exactly the same as in the original frozen gate. The existing `research_phase1_b1_robustness.py` helper semantics are authoritative for these calculations.

## Warning conditions — copied unchanged

The corrected gate is blocked if **any** of the same predeclared conditions is true:

- corrected 126-session issuer-equal-weight mean <= 0;
- corrected 126-session entry-session-equal-weight mean <= 0;
- corrected 126-session top-1%-removed mean <= 0;
- fewer than 3 of the 5 development years have positive corrected 126-session mean excess;
- top 1% of positive corrected-return observations contribute >= 50% of aggregate positive excess.

These thresholds are not re-estimated from corrected performance.

## HAC/calendar-time progression rule

A true daily-path equal-weight active-position calendar-time/HAC design remains deferred exactly as in the original gate.

- If `blockingWarningPresent=true`, do **not** proceed to HAC/OOS; record the corrected diagnostic result and investigate within development evidence only.
- If `blockingWarningPresent=false`, that still does not establish alpha. It only permits freezing a separate daily-path calendar-time/HAC design before execution.

No irregular event-horizon observation series may be mislabeled as a daily calendar-time portfolio.

## Required machine-readable output

The run must record:

- exact source run/artifact/digest;
- exact reproduction of corrected B1 horizon N/mean/median/win rate from the source summary;
- all four diagnostic families above;
- the five unchanged warning booleans;
- `blockingWarningPresent`;
- `formalAlphaClaim=false`;
- `oosEligible=false`;
- `calendarTimeHacStageOpened=false` unless a later, separately frozen gate explicitly authorizes it;
- `researchOnly=true`;
- `oosOpened=false`;
- `productionScoringChanged=false`.

Tests must lock source validation, 2023+ hard-fail behavior, long-format horizon parsing, reproduction checks, and unchanged warning semantics before the real corrected artifact is evaluated.
