# B3 development descriptive result — 2026-09-20

## Status

Workflow run `35502095184` completed successfully.

This is a **research/descriptive development result**, not formal alpha
evidence.

- development evaluation cohort: 2016–2020;
- outcomes: through 2022 only;
- validation performance: unopened;
- 2023+ OOS: sealed;
- production scoring: unchanged;
- B3 definition/event/identity rules: unchanged.

Persistent release:
`research-phase1-b3-development-v1`.

Source archive SHA-256:
`d90a2f08483d6710bb2f2715fa9049b64fd27a3979e7e63e5fb792f3c0274ae7`.

## Coverage

B3-specific frozen P0 coverage tier: **C_EXPLORATORY**.

- pre-outcome events: 35,829;
- PIT identity eligible: 34,472;
- exact-entry matched: **29,930**;
- entry attrition after identity: 4,542;
- distinct issuers with entry: 4,644;
- exact-entry coverage among identity-eligible events: **86.8241%**;
- identity missing rate: 3.4832%;
- identity ambiguity: 0.3152%;
- total identity problem rate: 3.7874%;
- worst-year exact-entry coverage: **83.9344%**;
- SPY session coverage: 100%.

Annual exact-entry coverage:

- 2016: 83.9344%;
- 2017: 85.0842%;
- 2018: 87.3450%;
- 2019: 87.5000%;
- 2020: 90.0013%.

Tier B is not met because overall exact-entry coverage is below 90%, identity
missing is above 3%, and worst-year exact-entry coverage is below 85%.
All frozen Tier C requirements pass.

## Development outcomes

| horizon | mature N | raw mean | raw median | SPY excess mean | SPY excess median | excess win rate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 21 | 29,570 | +2.62% | +1.31% | +0.81% | -0.51% | 47.34% |
| 63 | 29,390 | +8.01% | +3.75% | +2.75% | -1.17% | 46.67% |
| **126** | **29,069** | **+14.01%** | **+6.54%** | **+4.09%** | **-2.73%** | **44.84%** |
| 252 | 28,147 | +28.52% | +11.18% | +8.41% | -6.81% | 42.10% |

Primary 126-session diagnostics:

- SPY-excess P05: -52.58%;
- SPY-excess P10: -39.24%;
- MAE observed: 26,771;
- MAE mean: -20.98%;
- MAE median: -14.36%;
- missing exact exit bars: 861.

The positive arithmetic mean coexists with a negative median and a sub-50%
excess win rate, so this result has the same broad right-skew concern that
motivated the previously frozen B1 robustness diagnostics.

No B3 threshold or formula is changed from this observation.

## Next gate

Apply the same dependence/tail diagnostics and warning semantics already frozen
for B1:

- tail removal/concentration;
- issuer equal weighting;
- entry-session equal weighting;
- development-year stability.

A separate security-continuity and daily-path/HAC stage remains required before
stronger inference or any validation/OOS progression.
