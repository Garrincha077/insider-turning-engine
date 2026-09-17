# B1/B4 development run results — 2026-09-17

## Run and evidence status

GitHub Actions run `35263058619` completed successfully on 2026-09-17.

The full `Run B1 and B4 development cohorts` job completed with all gates green:

- bounded research evidence downloaded;
- bounded CMP classifier history view built and asserted;
- authoritative P0 exact-calendar tier recomputed;
- exploratory-or-better P0 gate passed;
- canonical B1 development cohort completed;
- B1 research-boundary assertions passed;
- predeclared B4 intersection development cohort completed;
- B4 research-boundary assertions passed;
- workflow artifact uploaded;
- B1/B4 research evidence persisted to `research-phase1-baselines-v1`.

The authoritative run artifact is `phase1-b1-b4-development` from run `35263058619`.

Research flags remain:

- `researchOnly=true`;
- `oosOpened=false`;
- `productionScoringChanged=false`;
- `canonicalReady=false`;
- `signalReady=false`;
- P0 data-quality tier: `C_EXPLORATORY`.

## Research boundaries remain locked

- development cohort: 2016–2020;
- outcome window: through 2022;
- 2023+ remains sealed OOS;
- production scoring is unchanged;
- B3 remains blocked until a complete PIT sale-history contract exists;
- B4 remains the exact same-issuer + same-XNYS-session intersection of B1 and B2 before issuer-level 20-session deduplication.

No definition was loosened in response to empirical performance or sample size.

## Bounded CMP classifier-history audit

Frozen CMP history in `research-cmp-history-v1` remains immutable. The derived bounded view used by this run produced:

| result | rows |
| --- | ---: |
| kept | 337,410 |
| excluded: outside predeclared 2013–2019 classifier history | 3,056 |
| excluded: impossible future trade month relative to filing month | 66 |
| total excluded | 3,122 |

Any filing date in 2023+ remains a hard failure rather than a filter. The successful run therefore did not open sealed OOS evidence.

## B1 selection

Canonical B1 (`CMP trader-level opportunistic qualified purchase`) produced:

- retained after issuer-level dedup: **6,775**;
- exact entries matched: **6,094**;
- missing exact entries: **681**;
- distinct issuers with entry: **2,175**.

### B1 descriptive outcomes

| horizon | matured N | raw mean | raw median | SPY excess mean | SPY excess median | excess win rate | MAE mean | MAE median |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 21 | 6,037 | +1.84% | +1.22% | -0.06% | -0.69% | 46.46% | -10.81% | -6.70% |
| 63 | 6,001 | +12.59% | +3.50% | +6.88% | -1.65% | 45.44% | -16.54% | -11.30% |
| **126** | **5,944** | **+20.45%** | **+6.38%** | **+9.79%** | **-3.35%** | **44.06%** | **-21.77%** | **-15.15%** |
| 252 | 5,772 | +39.24% | +10.94% | +18.38% | -7.31% | 41.61% | -29.39% | -22.82% |

The predeclared primary horizon is 126 XNYS sessions.

## B4 selection

Predeclared B4 (`B1 ∩ B2`, exact issuer + exact XNYS evaluation session) produced:

- joint events before common dedup: **6,177**;
- retained after issuer-level dedup: **3,816**;
- exact entries matched: **3,475**;
- missing exact entries: **341**;
- distinct issuers with entry: **1,533**.

### B4 descriptive outcomes

| horizon | matured N | raw mean | raw median | SPY excess mean | SPY excess median | excess win rate | MAE mean | MAE median |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 21 | 3,443 | +2.42% | +1.21% | +0.20% | -0.69% | 46.85% | -11.68% | -7.48% |
| 63 | 3,418 | +11.13% | +3.94% | +4.88% | -1.43% | 46.55% | -17.52% | -12.51% |
| **126** | **3,383** | **+15.22%** | **+6.23%** | **+4.04%** | **-3.55%** | **43.96%** | **-22.88%** | **-17.14%** |
| 252 | 3,291 | +30.73% | +10.94% | +9.12% | -7.56% | 41.75% | -30.93% | -24.69% |

## Primary 126-session comparison

B0 and B2 values below are reconstructed from the exact comparison deltas stored in the same B1/B4 run summaries; B1 and B4 are the direct cohort outputs.

| cohort | matured N | SPY excess mean | SPY excess median | excess win rate |
| --- | ---: | ---: | ---: | ---: |
| B0 | 23,502 | +5.20% | -2.80% | 44.72% |
| **B1** | **5,944** | **+9.79%** | **-3.35%** | **44.06%** |
| B2 | 11,238 | +4.14% | -3.05% | 44.48% |
| B4 | 3,383 | +4.04% | -3.55% | 43.96% |

### Exact primary-horizon deltas

B1 versus B0 at 126 sessions:

- mean SPY-excess delta: **+4.5904 percentage points**;
- median SPY-excess delta: **-0.5582 pp**;
- excess-win-rate delta: **-0.6626 pp**.

B4 versus B1 at 126 sessions:

- mean SPY-excess delta: **-5.7445 pp**;
- median SPY-excess delta: **-0.1917 pp**;
- excess-win-rate delta: **-0.1062 pp**.

B4 versus B2 at 126 sessions:

- mean SPY-excess delta: **-0.0956 pp**;
- median SPY-excess delta: **-0.4983 pp**;
- excess-win-rate delta: **-0.5279 pp**.

## Interpretation frozen before the next test

### B1

B1 has the strongest **mean** SPY-excess return among the four descriptive cohorts at the primary 126-session horizon: approximately **+9.79%**, versus approximately +5.20% for B0 and +4.14% for B2.

That mean result is **not** enough to claim a broad or validated edge. B1's 126-session median excess remains negative (-3.35%), its excess win rate is only 44.06%, and both are slightly worse than B0. Together with the large positive mean, this is consistent with a right-skewed/tail-driven return distribution in which a smaller set of large winners can lift the arithmetic mean.

This is a descriptive hypothesis for the next robustness gate, not a formal alpha finding.

### B4

The predeclared B4 intersection does **not** strengthen B1 at the primary horizon. It removes roughly 43% of B1's mature 126-session observations while reducing mean excess from +9.79% to +4.04%. It is also slightly weaker than B2 on mean, median and win rate at 126 sessions.

This is an informative negative result. The B4 definition must remain unchanged and must not be relaxed or retuned post hoc to improve its outcome.

### Long horizon

At 252 sessions B1 still shows a large positive mean SPY-excess return (+18.38%), but its median is -7.31% and excess win rate 41.61%. B4 is +9.12% mean with a -7.56% median and 41.75% win rate. These long-horizon arithmetic means are especially sensitive to overlapping events, dependence and tail observations and therefore do not change readiness status.

## Next research gate

Before any OOS opening or production-scoring decision, test whether the B1 mean effect survives dependence-aware robustness work on the still-sealed development evidence. At minimum the next gate should address:

1. overlapping event windows and repeated issuers;
2. issuer-clustered uncertainty;
3. calendar-time aggregation so simultaneous signals do not masquerade as independent observations;
4. tail sensitivity / trimmed or winsorized diagnostics without replacing the predeclared primary statistic;
5. confidence intervals or HAC-style inference appropriate to the calendar-time series;
6. stability by development year and concentration of total excess return in the largest winners.

The purpose is to determine whether B1's high arithmetic mean reflects a persistent signal or a small number of dependent extreme winners. **Do not open 2023+ OOS until this development-only gate is specified, implemented and frozen.**
