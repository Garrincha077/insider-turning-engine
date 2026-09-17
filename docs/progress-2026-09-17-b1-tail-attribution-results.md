# B1 tail/year attribution results — 2026-09-17

Source workflow: `35268723798`  
Source canonical B1 run: `35263058619`  
Main commit used by the audit: `13a26d81ac09c6e5730a60a6c5cc80a52d9cd389`

This document records the frozen development-only audit from `docs/research-phase1-b1-tail-attribution-gate.md`. It does not create a new signal filter, open 2023+ OOS, or change production scoring.

## Canonical reproduction

The audit reproduced the persisted canonical B1 126-session result exactly:

- mature observations: **5,944**;
- mean SPY excess: **+9.7882%**;
- median SPY excess: **-3.3534%**;
- win rate: **44.0612%**.

## Global top-1% attribution

The predeclared top set contains the 59 largest `excess_126` observations.

- top-59 signed excess sum: **636.8848**;
- full-cohort signed excess sum: **581.8086**;
- top-59 share of full signed excess: **109.4664%**;
- therefore the remaining 5,885 mature observations have a combined signed excess of approximately **-55.0762**;
- unique issuers: **52**;
- unique tickers: **52**;
- maximum repeats for one issuer: **3**;
- maximum repeats for one ticker: **3**.

Year distribution of the top 59:

| Evaluation year | Top-59 events |
| --- | ---: |
| 2016 | 8 |
| 2017 | 5 |
| 2018 | 4 |
| 2019 | 7 |
| 2020 | 35 |

Thus **59.32%** of the global top-59 set is from 2020.

The most repeated issuer CIK in the top set is `0001561387` with 3 events (5.08% of the set). The most repeated ticker is `HIIQ` with 3 events (5.08%). There is therefore no single repeated issuer/ticker explaining the entire 59-event set.

## Extreme winner concentration

The largest observation is:

- issuer CIK: `0001486159`;
- ticker: `OAS`;
- evaluation session: 2020-10-07;
- entry session: 2020-10-08;
- exit session: 2021-04-12;
- entry open: **0.1623**;
- raw 126-session return: **388.8953**;
- SPY-excess 126-session return: **388.6855**.

That single OAS observation contributes approximately **66.81% of the entire canonical B1 signed excess sum** and **61.03% of the top-59 signed excess sum**. The deterministic sanity checks did not flag its dates, session ordering, finite-price fields, issuer CIK or ticker; therefore it cannot be removed merely because it is extreme. Its security/ticker continuity and corporate-action history require a separately frozen verification protocol.

The ten largest observations are retained as audit evidence only:

| Rank | Ticker | Issuer CIK | Eval | Entry | Exit | Entry open | Raw 126 | Excess 126 |
| ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| 1 | OAS | 0001486159 | 2020-10-07 | 2020-10-08 | 2021-04-12 | 0.1623 | 388.8953 | 388.6855 |
| 2 | AI | 0001209028 | 2020-09-24 | 2020-09-25 | 2021-03-29 | 2.6000 | 22.8500 | 22.6139 |
| 3 | OSTK | 0001130713 | 2020-03-19 | 2020-03-20 | 2020-09-18 | 4.2300 | 16.7400 | 16.3647 |
| 4 | LOV | 0001314475 | 2017-08-28 | 2017-08-29 | 2018-03-01 | 1.2600 | 10.9048 | 10.7922 |
| 5 | CRDF | 0001213037 | 2020-05-14 | 2020-05-15 | 2020-11-12 | 1.4600 | 10.6164 | 10.3545 |
| 6 | TST | 0001080056 | 2018-12-12 | 2018-12-13 | 2019-06-17 | 0.6041 | 8.9652 | 8.8680 |
| 7 | CWEI | 0000880115 | 2016-04-05 | 2016-04-06 | 2016-10-04 | 9.7700 | 7.9284 | 7.8668 |
| 8 | APPS | 0000317788 | 2020-03-18 | 2020-03-19 | 2020-09-17 | 3.7000 | 7.7432 | 7.3249 |
| 9 | PEIX | 0000778164 | 2020-07-10 | 2020-07-13 | 2021-01-11 | 0.7770 | 7.1338 | 6.9411 |
| 10 | HEAR | 0001493761 | 2017-11-17 | 2017-11-20 | 2018-05-23 | 2.3200 | 6.4741 | 6.4055 |

## 2020 attribution

2020 has 1,546 mature events:

- mean excess: **+41.1360%**;
- median excess: **+0.6291%**;
- win rate: **50.5821%**;
- signed excess sum: **635.9627**;
- top-1%-removed mean (15 observations removed): **+9.2728%**;
- 1% two-sided trimmed mean: **+10.2727%**.

The 35 global top-59 events belonging to 2020 contribute **541.0917**, or **85.0823%**, of 2020's signed excess sum.

The full B1 cohort excluding 2020 contains 4,398 mature observations and is negative:

- mean excess: **-1.2313%**;
- median excess: **-4.0888%**;
- win rate: **41.7690%**.

This is a development-period attribution result, not a justification to exclude or include 2020 post hoc.

## Within-year tail sensitivity

| Year | N | Mean excess | Median | Win rate | Top-1%-removed mean | 1% trimmed mean | Largest excess |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2016 | 999 | +6.3343% | +1.6984% | 53.9540% | +3.5829% | +4.4265% | 786.68% |
| 2017 | 989 | -1.1447% | -4.8500% | 39.7371% | -4.3412% | -3.6479% | 1,079.22% |
| 2018 | 1,221 | -2.0696% | -3.0715% | 43.5708% | -4.6618% | -3.8342% | 886.80% |
| 2019 | 1,189 | -6.7992% | -8.8482% | 31.3709% | -9.3900% | -8.6604% | 518.45% |
| 2020 | 1,546 | +41.1360% | +0.6291% | 50.5821% | +9.2728% | +10.2727% | 38,868.55% |

2016 remains positive after its top 1% is removed. 2017–2019 remain negative. 2020 remains positive after its top 1% is removed, but the year contains an exceptionally influential extreme observation and substantial concentration in its largest winners.

## Deterministic sanity result

All 59 top observations passed the frozen mechanical checks:

- required dates parsed;
- no required date was in 2023+;
- session ordering was valid;
- entry open was positive and finite;
- raw and excess returns were finite;
- issuer CIK and ticker were non-empty.

`topSetSanity.anyFailure=false` and `failureCount=0`.

This does **not** prove security continuity across bankruptcies, ticker changes/reuse, mergers, reverse splits, delistings or relistings. Those are the next audit target.

## Current interpretation

B1 remains `researchOnly=true`, `oosOpened=false`, `productionScoringChanged=false`, `formalAlphaClaim=false`, and `oosEligible=false`.

The canonical positive arithmetic mean is highly tail/year dependent. The next step is not to remove OAS, AI or any other outlier. The next step is to predeclare and execute a corporate-action/security-continuity verification protocol for influential observations, beginning with the largest events.
