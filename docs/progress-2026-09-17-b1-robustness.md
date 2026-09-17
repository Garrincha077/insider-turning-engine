# B1 robustness diagnostic checkpoint — 2026-09-17

This checkpoint follows the frozen contract in `docs/research-phase1-b1-robustness-gate.md` and uses only canonical B1 evidence from GitHub Actions run `35263058619`.

The diagnostic implementation first reproduced the canonical B1 horizon counts, means, medians and win rates exactly. The first execution attempt produced no diagnostic output because the boundary check incorrectly treated a valid next-session 2021 entry after a late-2020 evaluation as outside the development cohort. Before any robustness result was observed, the contract was clarified to use the canonical `evaluationSession` as the 2016–2020 cohort clock. 2023+ remains a hard failure.

## Primary 126-session tail diagnostics

Canonical B1 mature N: **5,944**.

| statistic | result |
| --- | ---: |
| canonical mean SPY excess | +9.7882% |
| canonical median SPY excess | -3.3534% |
| canonical excess win rate | 44.0612% |
| 1% two-sided trimmed mean | **-0.0603%** |
| 5% two-sided trimmed mean | **-2.1141%** |
| top 1% winners removed mean | **-0.9359%** |
| top 5% winners removed mean | **-5.5644%** |
| P01 | -78.1401% |
| P05 | -53.2457% |
| P95 | +71.3378% |
| P99 | +190.0101% |

Positive-return concentration:

- top 1% of positive observations contribute **41.94%** of aggregate positive excess;
- top 5% contribute **55.60%**;
- top 10% contribute **64.92%**;
- the ten largest winners contribute **83.57% of the total signed excess sum**.

The arithmetic mean is therefore extremely tail-sensitive. Removing only the top 1% of outcomes changes the 126-session mean from +9.79% to -0.94%.

## Issuer dependence diagnostic

Using one equal-weight observation per issuer, where each issuer observation is the mean of its mature B1 events:

- issuers: **2,140**;
- issuer-equal-weight mean: **+14.3862%**;
- issuer-equal-weight median: **-1.4636%**;
- issuer-equal-weight win rate: **47.0561%**;
- canonical event-weighted mean: +9.7882%.

Event-count concentration by issuer is moderate rather than dominant:

- maximum mature events for one issuer: 24;
- P95: 8;
- P99: 14;
- top 1% of issuers by event count contain **6.31%** of mature events.

The high event-level mean does not disappear under issuer equal weighting.

## Same-entry-session dependence diagnostic

Using one equal-weight observation per entry session:

- distinct entry sessions: **1,201**;
- session-equal-weight mean: **+18.9881%**;
- session-equal-weight median: **-1.7428%**;
- session-equal-weight win rate: **45.9617%**;
- canonical event-weighted mean: +9.7882%.

Signal-count concentration by entry session:

- maximum mature signals on one entry session: 45;
- P95: 11;
- P99: 21;
- busiest 1% of entry sessions contain **6.26%** of mature events.

The high mean also does not disappear when simultaneous signals receive one equal-weight session observation.

## Development-year stability

Year is defined by the canonical `evaluationSession` cohort clock.

| evaluation year | N | mean SPY excess | median | win rate |
| ---: | ---: | ---: | ---: | ---: |
| 2016 | 999 | +6.3343% | +1.6984% | 53.95% |
| 2017 | 989 | -1.1447% | -4.8500% | 39.74% |
| 2018 | 1,221 | -2.0696% | -3.0715% | 43.57% |
| 2019 | 1,189 | -6.7992% | -8.8482% | 31.37% |
| 2020 | 1,546 | **+41.1360%** | +0.6291% | 50.58% |

Only **2 of 5** development years have a positive mean, and only 2 of 5 have a positive median. The max-minus-min yearly mean spread is approximately **47.94 percentage points**. The full-period arithmetic mean is therefore heavily influenced by 2020.

## Frozen gate result

Two predeclared warning conditions fired:

- `top1PctRemovedMeanNonPositive = true`;
- `fewerThanThreePositiveMeanYears = true`.

The other three warning conditions did not fire:

- issuer-equal-weight mean remains positive;
- entry-session-equal-weight mean remains positive;
- top 1% of positive observations contribute less than the 50% warning threshold.

Therefore **`blockingWarningPresent = true`**.

This blocks progression toward opening 2023+ OOS. It does not prove B1 has no information content; rather, it shows that the attractive full-period arithmetic mean is not robust to a minimal top-tail removal and is not stable across development years.

## Research status after this gate

- `researchOnly=true`;
- `oosOpened=false`;
- `productionScoringChanged=false`;
- `formalAlphaClaim=false`;
- `oosEligible=false`;
- P0 remains `C_EXPLORATORY`;
- B4 remains an informative negative intersection result and is not retuned.

## Next action

Do **not** open OOS and do not optimize around 2020. The next development-only work should explain the 2020/tail concentration using pre-specified diagnostics that do not change the canonical signal: identify which issuers/events dominate the top tail, test whether those winners cluster by industry/market regime/market-cap proxy where available, and determine whether the extreme outcomes reflect valid corporate events, data artifacts, or economically coherent B1 behavior.

Any subsequent test must be specified before inspecting its detailed subgroup results. A true daily-path calendar-time/HAC inference stage remains deferred until the tail/year instability is understood.
