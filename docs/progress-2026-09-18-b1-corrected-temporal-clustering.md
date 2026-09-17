# B1 continuity-corrected temporal clustering diagnostic — 2026-09-18

This checkpoint records the development-only temporal clustering/regime diagnostic frozen before execution in `docs/research-phase1-b1-corrected-temporal-clustering-gate.md`.

It is **not** a daily calendar-time portfolio and does not perform HAC inference. The previously frozen corrected robustness gate remains controlling and 2023+ OOS remains sealed.

## Frozen sources

Corrected-performance source:

- run `35277369958`;
- artifact `phase1-b1-continuity-corrected-performance-35277369958`;
- digest `sha256:d750c85b6019740ad381b2f53a9d6ceb379a5665cf8b43f0c70e799484bfa775`.

Canonical B1 metadata source:

- run `35263058619`;
- artifact `phase1-b1-b4-development-35263058619`;
- digest `sha256:1021de09ebaa190604bf1762714fe014ebc75e3e197b47d2d684003289ed638d`.

No new SEC evidence, market history, corporate-action evidence or 2023+ data was read.

## Successful workflow

- run: `35280513439`;
- artifact: `phase1-b1-corrected-temporal-clustering-35280513439`;
- artifact id: `10521927580`;
- artifact digest: `sha256:5fb6e19ef758a14852b87866fcac19f9f534ec08f688a3fbb63b6dee3e6f85d3`;
- workflow head SHA: `bea40c0ac21bd355e95b6b4c376a8232a780caaf`.

Pre-source execution order was preserved:

1. Ruff passed;
2. frozen synthetic/semantic tests passed;
3. exact frozen artifact identities/digests passed;
4. only then were the frozen development artifacts downloaded;
5. diagnostic execution passed;
6. all no-progression guardrails passed;
7. the result artifact was persisted.

## Corrected primary reproduction

The diagnostic exactly reproduces the persisted corrected 126-session B1 result:

- mature N: **5,965**;
- mean SPY excess: **+3.0841%**;
- median SPY excess: **-3.2967%**;
- win rate: **44.09%**.

## Event-count clustering is present but not dominant

All 60 development months and all 20 development quarters are non-empty.

Monthly event-count concentration:

- five busiest months contain **20.08%** of all mature events;
- busiest month: **458 events**, or **7.68%** of all events;
- event-count HHI: **0.02291** (uniform 60-month reference would be 0.01667).

Quarterly event-count concentration:

- five busiest quarters contain **35.36%** of all mature events;
- busiest quarter: **638 events**, or **10.70%** of all events;
- event-count HHI: **0.05508** (uniform 20-quarter reference would be 0.05000).

The five busiest months are March 2020, May 2019, August 2019, May 2020 and November 2018.

Thus the corrected result is not well described as being generated merely by one or two unusually crowded entry periods.

## Return contribution is much more temporally concentrated than event counts

The five highest signed-excess months contribute **106.78%** of the full corrected signed excess. A value above 100% is possible because the remaining months have a net negative signed contribution.

Those five months are:

- August 2020;
- May 2020;
- September 2020;
- November 2020;
- July 2020.

The five highest positive-excess months contribute **33.49%** of all positive excess; all five are in 2020 (March, May, August, September and November).

At quarterly frequency, the five highest signed-excess quarters contribute **161.67%** of the full signed excess because the remaining quarters are net negative. The five highest positive-excess quarters contribute **54.41%** of all positive excess and include all four quarters of 2020 plus 2016-Q2.

This is a much stronger concentration signal than the event-count HHI itself.

## Bucket sign stability

Monthly:

- positive-mean months: **30 / 60 = 50.0%**;
- positive-median months: **21 / 60 = 35.0%**;
- months with win rate > 50%: **20 / 60 = 33.3%**;
- longest positive-mean run: **10 months**, March–December 2020;
- longest non-positive-mean run: **7 months**, May–November 2018.

Quarterly:

- positive-mean quarters: **10 / 20 = 50.0%**;
- positive-median quarters: **6 / 20 = 30.0%**;
- quarters with win rate > 50%: **6 / 20 = 30.0%**;
- longest positive-mean run: **4 quarters**, 2016-Q1 through 2016-Q4;
- longest non-positive-mean run: **7 quarters**, 2018-Q2 through 2019-Q4.

The seven-quarter negative run followed by four positive 2020 quarters is consistent with broad temporal/regime instability rather than a single isolated outlier period.

## Quarterly corrected mean SPY excess

| quarter | N | mean SPY excess | median | win rate |
| --- | ---: | ---: | ---: | ---: |
| 2016-Q1 | 337 | +5.09% | +2.25% | 58.8% |
| 2016-Q2 | 249 | +13.59% | +4.20% | 59.4% |
| 2016-Q3 | 201 | +4.40% | -2.63% | 44.8% |
| 2016-Q4 | 212 | +1.63% | -0.81% | 48.6% |
| 2017-Q1 | 254 | -5.29% | -6.56% | 37.4% |
| 2017-Q2 | 259 | -3.26% | -4.12% | 39.4% |
| 2017-Q3 | 235 | -3.45% | -6.50% | 34.9% |
| 2017-Q4 | 241 | +3.30% | -1.05% | 47.3% |
| 2018-Q1 | 295 | +2.58% | +2.21% | 56.9% |
| 2018-Q2 | 272 | -5.84% | -5.37% | 38.2% |
| 2018-Q3 | 233 | -6.26% | -7.60% | 36.1% |
| 2018-Q4 | 421 | -0.57% | -4.39% | 41.8% |
| 2019-Q1 | 255 | -9.62% | -7.16% | 27.5% |
| 2019-Q2 | 345 | -5.40% | -7.02% | 31.3% |
| 2019-Q3 | 334 | -3.17% | -4.95% | 40.4% |
| 2019-Q4 | 256 | -10.79% | -21.07% | 23.4% |
| 2020-Q1 | 638 | +0.46% | -17.43% | 33.1% |
| 2020-Q2 | 368 | +16.20% | +2.51% | 53.8% |
| 2020-Q3 | 302 | +41.78% | +21.49% | 74.2% |
| 2020-Q4 | 258 | +23.51% | +8.93% | 62.0% |

2020-Q1 is a useful caution: its mean is slightly positive while its median and win rate remain strongly negative. The broad positive shift becomes clear in Q2–Q4.

## Leave-one-year-out attribution

| omitted year | remaining N | mean SPY excess | median | win rate |
| ---: | ---: | ---: | ---: | ---: |
| 2016 | 4,966 | +2.43% | -4.61% | 42.11% |
| 2017 | 4,976 | +4.14% | -2.83% | 44.96% |
| 2018 | 4,744 | +4.41% | -3.39% | 44.22% |
| 2019 | 4,775 | +5.56% | -1.48% | 47.27% |
| 2020 | 4,399 | **-1.49%** | **-4.09%** | **41.76%** |

Only omission of 2020 changes the full corrected development mean from positive to negative. This reproduces the earlier attribution result and shows that the overall positive mean is strongly dependent on the 2020 regime.

## Entry-session clustering consistency

The diagnostic reproduces the already known corrected robustness entry-session concentration:

- unique entry sessions: **1,202**;
- maximum events on one entry session: **45**;
- P95: **11** events;
- P99: **20.99** events;
- busiest 1% of entry sessions contain **6.25%** of events.

This again argues against same-day signal crowding being the main explanation for the corrected mean.

## Interpretation

The new diagnostic strengthens the earlier conclusion without creating a new filter:

1. **Event incidence is not extremely concentrated.** Events are spread across all 60 months and 20 quarters, and entry-session concentration is moderate.
2. **Return contribution is strongly time-dependent.** The strongest signed and positive contribution buckets are concentrated in 2020.
3. **The weakness is broad, not just one bad observation.** There is a seven-quarter non-positive-mean run from 2018-Q2 through 2019-Q4.
4. **The full positive arithmetic mean depends materially on 2020.** Excluding 2020 for attribution only leaves a -1.49% mean.

The appropriate description remains **development-sample temporal/regime instability**. This diagnostic does not identify a deterministic data defect and does not justify a 2020 filter, bull/bear filter, market-regime filter, ticker filter or any production scoring change.

## Progression remains closed

The prior corrected robustness gate remains controlling:

- `blockingWarningPresent=true`;
- `BLOCK_HAC_AND_OOS`;
- `calendarTimeHacStageOpened=false`;
- `oosEligible=false`;
- `oosOpened=false`;
- `productionScoringChanged=false`.

Do not open formal daily-path calendar-time/HAC inference or 2023+ OOS from this result.

A later, separately frozen research phase may investigate characteristics shared by the largest valid winners (technical state, insider-purchase structure, issuer fundamentals, size/liquidity, valuation and market regime), but those findings must not be used to rewrite this frozen B1 result.
