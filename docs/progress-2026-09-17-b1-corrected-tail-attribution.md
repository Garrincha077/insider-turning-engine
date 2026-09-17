# B1 continuity-corrected residual tail/year attribution — 2026-09-17

This checkpoint records the frozen residual tail/year attribution audit after security-continuity correction and after the unchanged corrected robustness gate remained blocked.

## Frozen sources

Corrected-performance source:

- run `35277369958`;
- artifact `phase1-b1-continuity-corrected-performance-35277369958`;
- digest `sha256:d750c85b6019740ad381b2f53a9d6ceb379a5665cf8b43f0c70e799484bfa775`.

Canonical B1 metadata source:

- run `35263058619`;
- artifact `phase1-b1-b4-development-35263058619`;
- digest `sha256:1021de09ebaa190604bf1762714fe014ebc75e3e197b47d2d684003289ed638d`.

The audit did not download SEC data, market history, new corporate-action evidence or any 2023+ data. Canonical B1 metadata was used only to restore audit fields that are not duplicated in the corrected long-format outcome artifact.

## Successful workflow

- run: `35278458183`;
- artifact: `phase1-b1-corrected-tail-attribution-35278458183`;
- artifact digest: `sha256:22521b3f4672b98ce37c254e628f735f069166dcc32778e2d5183b2c82177192`;
- workflow head SHA: `224006749fb30730b562bffa1ad6ea3836ae77b5`.

The preceding attempt `35278305803` stopped at Ruff because of two line-length violations. No source artifacts were opened in that failed attempt. Only line wrapping was changed; the frozen audit logic and thresholds were untouched.

All successful-run gates passed:

- Ruff;
- frozen corrected-tail adapter tests;
- corrected and canonical source artifact digest checks;
- exact corrected/canonical identity/date join by frozen event order;
- exact corrected primary summary reproduction;
- top-1% cutoff/tie semantics;
- 2016–2020 year coverage;
- deterministic top-set sanity contract;
- research/OOS/HAC guardrails.

## Boundaries remain locked

- B1 definition unchanged.
- Development evaluation sessions: 2016–2020.
- Outcomes: through 2022 only.
- 2023+ OOS remains sealed.
- Primary horizon remains 126 XNYS sessions.
- `researchOnly=true`.
- `oosOpened=false`.
- `productionScoringChanged=false`.
- `formalAlphaClaim=false`.
- `oosEligible=false`.
- `calendarTimeHacStageOpened=false`.

## Corrected primary reproduction

The audit reproduces the persisted corrected B1 126-session summary exactly:

- mature N: **5,965**;
- mean SPY excess: **+3.0841%**;
- median SPY excess: **-3.2967%**;
- excess win rate: **44.09%**.

With N = 5,965, the frozen global top-1% rule `floor(N * 0.01)` yields **59 observations**.

## Global residual corrected top 1%

The 59 largest corrected 126-session SPY-excess observations have:

- signed excess sum: **236.03**;
- full mature cohort signed excess sum: **183.97**;
- signed-excess share: **128.30%** of the full signed sum;
- unique issuers: **51**;
- unique tickers: **51**;
- maximum repeats for one issuer: **3**;
- maximum repeats for one ticker: **3**.

A share above 100% is possible because the observations outside the top set have a net negative signed excess contribution.

Year distribution of the corrected top 59:

| evaluation year | top-59 events |
| ---: | ---: |
| 2016 | 8 |
| 2017 | 4 |
| 2018 | 4 |
| 2019 | 7 |
| 2020 | **36** |

Thus **61.02%** of the residual corrected top-1% set belongs to 2020.

The top set is not dominated by a single continuity treatment:

- `PRICE_CONTINUOUS_ADJUSTED`: **55**;
- `SYMBOL_CHANGED_SAME_SECURITY`: **3**;
- `TRANSFORMED_HOLDER_CONSIDERATION`: **1**.

Valuation kinds are 55 ordinary adjusted-price continuities, 3 same-security symbol changes and 1 stock-merger valuation.

## Largest corrected observations

The ten largest corrected 126-session SPY-excess observations are audit evidence only; they are not a watchlist or an exclusion set.

| rank | ticker | evaluation session | corrected raw | corrected SPY excess |
| ---: | --- | --- | ---: | ---: |
| 1 | OSTK | 2020-03-19 | +1,674.00% | +1,636.47% |
| 2 | CRDF | 2020-05-14 | +1,061.64% | +1,035.45% |
| 3 | FSDC | 2020-10-20 | +946.08% | +923.78% |
| 4 | TST | 2018-12-12 | +896.52% | +886.80% |
| 5 | CWEI | 2016-04-05 | +792.84% | +786.68% |
| 6 | APPS | 2020-03-18 | +774.32% | +732.49% |
| 7 | PEIX | 2020-07-10 | +713.38% | +694.11% |
| 8 | HEAR | 2017-11-17 | +647.41% | +640.55% |
| 9 | INO | 2020-01-13 | +633.83% | +634.50% |
| 10 | HCFT | 2020-08-18 | +648.92% | +632.92% |

No rule may be created from these identities or return magnitudes.

## Deterministic sanity

All **59/59** residual corrected top-set observations pass the frozen deterministic sanity checks:

- valid required dates;
- no 2023+ date;
- valid evaluation/entry/exit ordering;
- finite positive entry open;
- finite corrected raw and excess values;
- non-empty issuer and ticker;
- `valuationStatus=VALUED`;
- exact corrected/canonical frozen identity/date join.

Result:

- `failureCount=0`;
- `anyDeterministicSanityFailure=false`.

Therefore there is no newly identified deterministic data-validity basis for removing these residual large winners. They remain part of the corrected development sample.

## 2020 attribution

Corrected 2020 evaluation-session outcomes:

- N: **1,566**;
- mean SPY excess: **+15.9245%**;
- median: **+0.6896%**;
- win rate: **50.64%**;
- signed excess sum: **249.38**.

The 36 global top-59 observations from 2020 contribute **60.56%** of 2020's signed excess sum.

However, 2020 remains positive even after its own largest 1% is removed:

- removed observations: 15;
- top-1%-removed mean: **+9.6055%**;
- 1%-each-tail trimmed mean: **+10.5976%**.

Thus the positive 2020 result is not explained only by a tiny handful of residual extreme winners.

The full corrected cohort excluding all 2020 evaluation-session observations is:

- N: **4,399**;
- mean SPY excess: **-1.4869%**;
- median: **-4.0932%**;
- win rate: **41.76%**.

This is an attribution diagnostic only. It does not authorize excluding or selecting a year.

## Within-year tail sensitivity

| year | N | mean | top-1%-removed mean | 1% two-sided trimmed mean |
| ---: | ---: | ---: | ---: | ---: |
| 2016 | 999 | +6.3343% | **+3.5829%** | +4.4265% |
| 2017 | 989 | -2.2281% | **-4.4363%** | -3.7439% |
| 2018 | 1,221 | -2.0696% | **-4.6618%** | -3.8342% |
| 2019 | 1,190 | -6.8390% | **-9.4280%** | -8.6994% |
| 2020 | 1,566 | +15.9245% | **+9.6055%** | +10.5976% |

The residual corrected instability is therefore not well described as merely one or two bad corporate-action records or a single extreme top-tail observation. After deterministic continuity correction and top-tail removal, 2016 and 2020 remain positive while 2017–2019 remain negative.

## Interpretation

The security-continuity correction removed a substantial artificial component of the original B1 arithmetic mean and sharply reduced positive-tail concentration. The remaining top 59 are deterministically data-consistent under the frozen audit, and the strongest positive year, 2020, remains materially positive even after removing its own top 1%.

At the same time, the corrected B1 signal is not stable across development years: the corrected cohort excluding 2020 is negative, and three consecutive development years (2017–2019) have negative mean excess even after applying the same tail sensitivity diagnostics.

This supports treating the remaining issue as **development-sample year/regime instability**, not as a newly discovered continuity-resolution defect. It does not justify a year filter, regime filter or production-scoring change.

The previously frozen robustness result remains controlling:

- `blockingWarningPresent=true`;
- `BLOCK_HAC_AND_OOS`;
- `calendarTimeHacStageOpened=false`;
- `oosEligible=false`.

Do not open 2023+ OOS and do not proceed to formal HAC/calendar-time inference unless a later research gate explicitly resolves the already frozen blocking-warning progression rule without post-hoc retuning.
