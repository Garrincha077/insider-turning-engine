# Phase-1 B1 continuity-corrected performance — green checkpoint (2026-09-17)

This checkpoint records the first corrected-performance run after the separately frozen, performance-blind security-continuity gate reached zero unresolved rows.

## Research boundaries preserved

- Development cohort: 2016–2020 XNYS evaluation sessions.
- Outcome market boundary: through 2022 only.
- 2023+ OOS remains sealed.
- Primary horizon remains 126 XNYS sessions.
- Secondary horizons remain 21 / 63 / 252 sessions.
- B1/B2/B4 definitions are unchanged.
- `researchOnly=true`.
- `oosOpened=false`.
- `productionScoringChanged=false`.
- Result class: `research/descriptive`.
- No formal alpha claim.
- P0 remains exploratory.
- Dependence-aware / calendar-time / HAC robustness remains incomplete.
- MAE was not recomputed in this correction stage.

## Upstream continuity gate

Required zero-unresolved continuity run:

- run: `35275669277`
- artifact: `phase1-security-continuity-resolution-35275669277`
- artifact digest: `sha256:f5d1dbbb2978bf495d439dfaa0981f4f0d987260e85e96f266866647b0d65f8c`
- `UNRESOLVED_CONTINUITY = 0`
- `sourceLedgerUntouched=true`
- `frozenScopeExpanded=false`
- `performanceRead=false`
- `priceFieldsRead=[]`
- `performanceFieldsRead=[]`

The corrected-performance workflow additionally verified the frozen upstream artifact digests before reading performance.

## Corrected-performance workflow

Successful GitHub Actions run:

- run: `35277369958`
- artifact: `phase1-b1-continuity-corrected-performance-35277369958`
- artifact digest: `sha256:d750c85b6019740ad381b2f53a9d6ceb379a5665cf8b43f0c70e799484bfa775`
- workflow head SHA: `6601d643bc28edfdf40b67a564fb095b6a982882`

All workflow gates passed:

- Ruff corrected-performance runner/tests;
- valuation regression tests;
- frozen source-continuity artifact identity/digest;
- frozen zero-unresolved resolution artifact identity/digest;
- frozen B1/B4 development artifact identity/digest;
- bounded market download 2016–2022 only;
- explicit absence of 2023 market evidence;
- zero-unresolved gate assertion before performance read;
- corrected B1 valuation;
- final research-boundary/comparison assertions;
- artifact upload.

## Corrected B1 scope

- B1 exact-entry events: **6,094**.
- Event-horizon rows: **24,376**.

Final continuity states consumed by corrected performance:

| state | rows |
| --- | ---: |
| `PRICE_CONTINUOUS_ADJUSTED` | 24,232 |
| `SYMBOL_CHANGED_SAME_SECURITY` | 66 |
| `TRANSFORMED_HOLDER_CONSIDERATION` | 75 |
| `DISCONTINUOUS_NO_COMPLETE_VALUATION` | 3 |

Valuation statuses:

| status | rows |
| --- | ---: |
| `VALUED` | 23,850 |
| `MISSING_EXACT_TERMINAL_HOLDER_BAR` | 523 |
| `MISSING_DISCONTINUOUS_NO_COMPLETE_VALUATION` | 3 |

Rows where corrected raw return differs from the frozen canonical raw return, or where canonical raw was missing: **125**.

`DISCONTINUOUS_NO_COMPLETE_VALUATION` remained missing; it was not converted to zero and was not chained to later same-ticker prices.

## B1 corrected horizons

| horizon | canonical B1 SPY excess mean | corrected B1 SPY excess mean | delta | canonical median | corrected median | canonical win rate | corrected win rate | mature N delta |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 21 | -0.06% | -0.05% | +0.00 pp | -0.69% | -0.70% | 46.46% | 46.46% | +3 |
| 63 | +6.88% | +1.81% | -5.07 pp | -1.65% | -1.66% | 45.44% | 45.39% | +9 |
| **126** | **+9.79%** | **+3.08%** | **-6.70 pp** | **-3.35%** | **-3.30%** | **44.06%** | **44.09%** | **+21** |
| 252 | +18.38% | +10.23% | -8.15 pp | -7.31% | -7.24% | 41.61% | 41.75% | +63 |

The primary 126-session corrected B1 sample contains **5,965** mature outcomes, versus 5,944 in the frozen canonical B1 result.

## Primary 126-session descriptive comparison

Only B1 is continuity-corrected in this run. B0, B2 and B4 below remain their frozen canonical research baselines.

| cohort | status | mature N | SPY excess mean | SPY excess median | excess win rate |
| --- | --- | ---: | ---: | ---: | ---: |
| B0 | canonical | 23,502 | +5.20% | -2.80% | 44.72% |
| B1 | **continuity-corrected** | **5,965** | **+3.08%** | **-3.30%** | **44.09%** |
| B2 | canonical | 11,238 | +4.14% | -3.05% | 44.48% |
| B4 | canonical | 3,383 | +4.04% | -3.55% | 43.96% |

The corrected B1 mean is therefore materially lower than the previously reported canonical B1 mean. The median and excess-win-rate move only slightly, which is consistent with the prior canonical mean being sensitive to a small number of large continuity/identity misvaluations rather than a broad shift across the distribution.

Among the largest individual return corrections are the already verified identity/holder cases:

- old Arlington `AI` must continue as `AAIC`, not later C3.ai `AI` prices;
- `LOV` must carry the documented 10 old shares -> 1 successor ADS holder transformation rather than a one-for-one same-ticker chain.

Frozen stock-dividend holder multipliers can increase some corrected holder returns; the correction framework is symmetric and is not chosen according to whether a correction raises or lowers B1 performance.

## B4 continuity-scope boundary

B4 is intersected before its own common 20-session issuer-level deduplication, so it is not a complete subset of the frozen deduplicated B1 continuity cohort.

- B4 exact-entry events: **3,475**.
- covered by frozen B1 continuity ledger: **3,111**.
- outside frozen B1 continuity ledger: **364**.
- `correctedB4Claimed=false`.

The 364 events were **not** automatically added to continuity scope after seeing corrected performance. B4 remains canonical in this checkpoint.

## Interpretation and next gate

The original high B1 arithmetic mean is substantially reduced after deterministic security-identity/holder-basis correction, especially at 63/126/252 sessions. This makes the continuity correction economically material, while the nearly unchanged medians and win rates continue to show a broad distribution with negative median excess at the primary horizon.

This is descriptive development evidence, not formal alpha. Before any 2023+ OOS opening or production decision, the next research work should remain development-only and address dependence/overlap, issuer clustering, calendar-time aggregation, tail sensitivity, and HAC-style uncertainty under the corrected B1 outcome series.

Do not reinterpret the corrected run as authority to change B1/B2/B4 definitions or production scoring.
