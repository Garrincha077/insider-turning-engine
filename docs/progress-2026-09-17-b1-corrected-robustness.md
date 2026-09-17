# B1 continuity-corrected robustness checkpoint — 2026-09-17

This checkpoint applies the unchanged diagnostic and warning semantics from `docs/research-phase1-b1-robustness-gate.md` to the frozen continuity-corrected B1 outcome artifact. The corrected application contract was frozen in `docs/research-phase1-b1-corrected-robustness-gate.md` before this run.

## Source and run identity

Corrected-performance source:

- run: `35277369958`
- artifact: `phase1-b1-continuity-corrected-performance-35277369958`
- artifact digest: `sha256:d750c85b6019740ad381b2f53a9d6ceb379a5665cf8b43f0c70e799484bfa775`

Successful corrected robustness run:

- run: `35278014787`
- artifact: `phase1-b1-corrected-robustness-35278014787`
- artifact digest: `sha256:28d2eb64b07e3c0365a57117bb278a5e2834042c8ab73d35c3164e5d545ef0f0`
- workflow head SHA: `bbacd059a799a6eaa5ff3fe22e79d64649941ecf`

The first workflow attempt (`35277937286`) stopped in a synthetic unit fixture because the fixture covered only one development year while the already frozen year-stability helper correctly requires all five. No corrected source artifact was opened in that failed attempt. The fixture was corrected to cover 2016–2020; no diagnostic rule or threshold changed.

## Boundaries preserved

- B1 definition unchanged.
- Development clock: canonical `evaluationSession`, 2016–2020.
- Outcomes through 2022 only.
- 2023+ OOS remains sealed.
- Horizons remain 21 / 63 / 126 / 252 sessions.
- Primary horizon remains 126 sessions.
- `researchOnly=true`.
- `oosOpened=false`.
- `productionScoringChanged=false`.
- `formalAlphaClaim=false`.
- `oosEligible=false`.
- `calendarTimeHacStageOpened=false`.

The workflow reproduced the corrected source N/mean/median/win-rate exactly before computing robustness diagnostics.

## Primary 126-session corrected tail diagnostics

Corrected B1 mature N: **5,965**.

| statistic | corrected result |
| --- | ---: |
| corrected mean SPY excess | +3.0841% |
| corrected median SPY excess | -3.2967% |
| corrected excess win rate | 44.0905% |
| 1% two-sided trimmed mean | **-0.0074%** |
| 5% two-sided trimmed mean | **-2.0863%** |
| top 1% winners removed mean | **-0.8816%** |
| top 5% winners removed mean | **-5.5406%** |
| P01 | -78.1630% |
| P05 | -53.2947% |
| P95 | +71.6242% |
| P99 | +189.8724% |

Positive-return concentration after continuity correction:

- top 1% of positive observations contribute **17.05%** of aggregate positive excess;
- top 5% contribute **36.62%**;
- top 10% contribute **49.89%**;
- the ten largest winners contribute **46.77% of the total signed excess sum**.

Security-continuity correction therefore substantially reduced the earlier extreme positive-tail concentration, but the mean remains sensitive enough that removing the top 1% of observations still makes it negative.

## Issuer dependence

At 126 sessions:

- issuers: **2,145**;
- issuer-equal-weight mean: **+4.5464%**;
- issuer-equal-weight median: **-1.4854%**;
- issuer-equal-weight win rate: **46.85%**;
- corrected event-weighted mean: **+3.0841%**.

Event-count concentration by issuer:

- maximum mature events for one issuer: 24;
- P95: 8;
- P99: 14;
- top 1% of issuers by event count contain **6.30%** of mature events.

The issuer-equal-weight mean remains positive, so the repeated-issuer warning does not fire.

## Same-entry-session dependence

At 126 sessions:

- distinct entry sessions: **1,202**;
- entry-session-equal-weight mean: **+3.0885%**;
- median: **-1.7391%**;
- win rate: **46.01%**;
- corrected event-weighted mean: **+3.0841%**.

Signal-count concentration:

- maximum mature signals on one entry session: 45;
- P95: 11;
- P99: approximately 21;
- busiest 1% of entry sessions contain **6.25%** of mature events.

The same-entry-session equal-weight mean remains positive, so that warning does not fire.

## Development-year stability

Year remains defined by the canonical `evaluationSession`.

| evaluation year | N | corrected mean SPY excess | median | win rate |
| ---: | ---: | ---: | ---: | ---: |
| 2016 | 999 | +6.3343% | +1.6984% | 53.95% |
| 2017 | 989 | -2.2281% | -4.8500% | 39.74% |
| 2018 | 1,221 | -2.0696% | -3.0715% | 43.57% |
| 2019 | 1,190 | -6.8390% | -8.8963% | 31.34% |
| 2020 | 1,566 | +15.9245% | +0.6896% | 50.64% |

Only **2 of 5** development years have positive mean corrected excess and only 2 of 5 have positive median corrected excess. Max-minus-min yearly mean spread is approximately **22.76 percentage points**.

Continuity correction materially reduces the earlier 2020 mean magnitude (canonical robustness diagnostic was approximately +41.14%), but 2020 remains the strongest positive development year and the full-period result remains unstable across years.

## Frozen warning result

The unchanged warning conditions produce:

- `issuerEqualWeightMeanNonPositive = false`
- `entrySessionEqualWeightMeanNonPositive = false`
- `top1PctRemovedMeanNonPositive = true`
- `fewerThanThreePositiveMeanYears = true`
- `top1PctPositiveTailAtLeastHalf = false`

Therefore:

- **`blockingWarningPresent = true`**
- progression: **`BLOCK_HAC_AND_OOS`**
- `calendarTimeHacStageOpened=false`
- `oosEligible=false`

## Interpretation and next allowed work

The continuity correction resolves a large part of the original positive-tail artifact: positive-tail concentration is much less extreme, and the 2020 mean is far lower than before correction. It does **not**, however, clear the predeclared robustness gate. The corrected B1 mean still turns negative after removing only the top 1% of outcomes and only two development years have positive mean excess.

Accordingly, do not open 2023+ OOS and do not execute a HAC/calendar-time inference stage yet. The next permitted work remains development-only attribution of the residual corrected top tail and year instability using diagnostics that were frozen before detailed subgroup results are inspected. No B1/B2/B4 signal definition or production scoring change is authorized by this result.
