# Phase-1 development benchmark-family synthesis — 2026-09-21

This checkpoint closes the simple B0/B1/B2/B3/B4 development benchmark family
as the reference set for the next insider-feature tournament.

It does not select a production model and does not open validation or OOS.

## Frozen evidence used

### B0 — any qualified open-market purchase

Workflow run: `35235518475`.

Primary 126-session development result:

- mature N: **23,504**
- distinct issuers: **4,628**
- SPY excess mean: **+5.2004%**
- SPY excess median: **-2.7952%**
- excess win rate: **44.7243%**
- P05: **-51.7136%**
- P10: **-38.3671%**

### B1 — canonical CMP-style opportunistic purchase

Canonical B1 was materially affected by security-continuity errors. Therefore
the benchmark-family anchor is the **continuity-corrected** B1 result, not the
canonical +9.79% arithmetic mean.

Corrected-performance run: `35277369958`.

Primary 126-session corrected result:

- mature N: **5,965**
- distinct issuers: **2,145**
- SPY excess mean: **+3.0841%**
- SPY excess median: **-3.2967%**
- excess win rate: **44.0905%**
- P05: **-53.2947%**
- P10: **-40.0475%**

Corrected robustness run: `35278014787`.

Key robustness facts:

- issuer equal-weight mean: **+4.5464%**
- entry-session equal-weight mean: **+3.0885%**
- top-1%-removed mean: **-0.8816%**
- positive-mean years: **2 / 5**
- progression: **BLOCK_HAC_AND_OOS**

The positive full-period B1 mean is also temporally unstable: omitting 2020
turns the corrected development mean negative.

### B2 — independent-owner cluster

Workflow run: `35535351141`.

Primary 126-session development result:

- mature N: **11,238**
- distinct issuers: **3,288**
- SPY excess mean: **+4.1393%**
- SPY excess median: **-3.0467%**
- excess win rate: **44.4830%**
- P05: **-54.6755%**
- P10: **-41.4669%**

This remains descriptive development evidence. It has not received the same
full continuity-correction/robustness program as B1/B3.

### B3 — company net buying

Use the final **continuity-corrected** result.

Corrected development run: `35634832574`.

Primary 126-session corrected result:

- mature N: **29,072**
- SPY excess mean: **+4.0286%**
- SPY excess median: **-2.7248%**
- excess win rate: **44.8473%**
- P05: **-52.5835%**
- P10: **-39.2347%**

Corrected robustness run: `35635187501`.

Key robustness facts:

- issuer equal-weight mean: **+5.0390%**
- entry-session equal-weight mean: **+3.3464%**
- top-1%-removed mean: **-0.2021%**
- positive-mean years: **3 / 5**
- progression: **BLOCK_HAC_AND_OOS**

### B4 — opportunistic + independent-owner cluster intersection

Workflow run: `35263058619`.

Primary 126-session canonical result:

- mature N: **3,383**
- distinct issuers: **1,503**
- SPY excess mean: **+4.0436%**
- SPY excess median: **-3.5450%**
- excess win rate: **43.9551%**
- P05: **-55.2749%**
- P10: **-42.4741%**

B4 remains canonical because 364 B4 exact-entry events were outside the frozen
deduplicated B1 continuity scope. The B1 correction gate explicitly forbade
auto-expanding continuity scope after observing performance.

## Primary 126-session comparison

| benchmark | continuity basis | mature N | SPY excess mean | median | win rate |
| --- | --- | ---: | ---: | ---: | ---: |
| B0 | canonical | 23,504 | +5.2004% | -2.7952% | 44.7243% |
| B1 | continuity-corrected | 5,965 | +3.0841% | -3.2967% | 44.0905% |
| B2 | canonical | 11,238 | +4.1393% | -3.0467% | 44.4830% |
| B3 | continuity-corrected | 29,072 | +4.0286% | -2.7248% | 44.8473% |
| B4 | canonical | 3,383 | +4.0436% | -3.5450% | 43.9551% |

## What the family establishes

1. **Complexity has not yet earned its keep.** After continuity correction, no
   B1/B2/B3/B4 arithmetic mean exceeds the simple B0 development mean at the
   primary horizon.
2. **The center of the distribution is weak across the family.** Every
   benchmark has a negative 126-session SPY-excess median and a sub-45%
   excess-win rate.
3. **Arithmetic means are not sufficient selection statistics.** B1 and B3
   explicitly fail frozen robustness gates because their positive mean is
   sensitive to the right tail; B1 also shows severe temporal/regime
   instability.
4. **The next phase must search for stable separation, not a higher in-sample
   mean.** A candidate feature must improve outcomes in a way that survives
   issuer/session weighting, tail removal, time splits and liquidity/coverage
   checks.
5. **B0 is the neutral primary anchor for feature evaluation.** B1/B2/B3/B4
   remain mandatory contextual comparators/strata, but a more complicated
   feature is not credited merely for being correlated with one of them.

## Boundary for the next phase

This synthesis is development-only. It does not:

- claim formal alpha;
- promote any benchmark to production;
- authorize HAC;
- open 2021-2022 for feature tuning;
- open 2023+ OOS;
- change production scoring.

The next permitted step is to freeze the insider-feature tournament candidate
families, feature construction, missingness/coverage rules, chronological
development split, comparison metrics and advancement criteria **before** any
new feature performance is read.
