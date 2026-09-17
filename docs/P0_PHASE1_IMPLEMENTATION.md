# P0 data-quality tiers and Phase-1 B0 implementation

_Last updated: 2026-09-17_

Research-only specification. Production scoring, thresholds, signal states and alerts are unchanged. Sealed OOS 2023+ remains unopened.

## 1. Data-quality tiers

The market-data gate is no longer a single pass/fail threshold. The audit must report the highest tier that passes all criteria below.

| Metric | A — High confidence | B — Research grade | C — Exploratory |
|---|---:|---:|---:|
| Eligible exact-entry coverage | >= 95% | >= 90% | >= 80% |
| Missing/placeholder identity | <= 1% | <= 3% | <= 7.5% |
| Identity ambiguity among usable tickered events | <= 0.5% | <= 1% | <= 2% |
| Total identity problem rate | <= 1.5% | <= 4% | <= 9% |
| Worst single-year exact-entry coverage | >= 90% | >= 85% | >= 70% |
| SPY/XNYS benchmark-session coverage | 100% | >= 99.5% | >= 99% |

Tier assignment must be determined before inspecting Phase-1 performance. A later improvement in historical identity or market coverage can move a dataset upward, but a threshold must never be lowered because a performance result is attractive.

### Non-tiered invariants

These never relax for A, B or C:

- `knowledgeAt` is the public-information clock; SEC acceptance-time PIT rules stay intact;
- 2023+ outcomes remain sealed;
- current ticker/current market cap must not be used as historical truth;
- missing returns are never imputed as zero or silently dropped;
- `terminal_candidate` rows are never ordinary sessions;
- ambiguous identity remains explicit attrition;
- research tiers do not change production scoring or alerts.

## 2. Exact-calendar correction required before final tier assignment

The existing event-level market audit currently searches each security's own regular-bar dates for a later available bar. That is not identical to the locked backtester, which uses SPY/XNYS as the session calendar and requires the stock bar on the exact session.

The audit must therefore be corrected as follows:

1. Determine `evaluationSession` from `knowledgeAt` using XNYS.
2. Define `entrySession` as the **exact next XNYS session**.
3. Count entry as matched only when a non-terminal, positive-volume, positive-trade-count stock bar exists on that exact session.
4. Define 21/63/126/252 outcomes from the XNYS/SPY session index, not from the stock's own list of available bars.
5. `STUDY_BOUNDARY_RIGHT_CENSORED` is allowed only when the required target XNYS session lies after 2022-12-31.
6. If the target XNYS session is within 2016-2022 but the stock bar is absent, classify it as missing exact-session market history or terminal/delisted attrition; do not call it boundary censoring.

This can lower or raise the previously reported 91.16% coverage. The post-correction audit is the authoritative P0 tier result.

## 3. Phase-1 B0 baseline

B0 asks a deliberately simple question: do PIT-valid open-market insider purchases have useful forward returns before any insider sophistication or technical-turning feature is added?

### Eligibility

- public ownership filing;
- non-derivative transaction;
- transaction code `P`;
- acquired/disposed = `A`;
- economic classification = `OPEN_MARKET_PURCHASE`;
- historical issuer CIK + historical filing-time ticker identity;
- no 2023+ information.

### Event and execution clock

- research event source unit: issuer CIK + eligible XNYS evaluation session;
- evaluation: first eligible XNYS close after `knowledgeAt`;
- entry: exact next XNYS session open;
- benchmark: SPY on the same exact entry/exit sessions;
- horizons: 21, 63, 126 and 252 XNYS sessions;
- primary horizon: 126 sessions.

### Development-only first run

The first B0 result must use **2016-01-01 through 2020-12-31 only**. Validation 2021-2022 remains untouched until B0 plumbing and reporting are frozen.

Use a 20-session issuer-level deduplication window for B0 exposure so repeated filings do not create overlapping pseudo-independent events. The deduplication rule is frozen before validation.

### Required outputs

For each horizon report at minimum:

- eligible events;
- exact-entry matched events and attrition;
- matured outcome count;
- raw stock return mean and median;
- SPY excess return mean and median;
- excess-return win rate;
- 5th and 10th percentile downside tail;
- MAE where the complete exact-session path exists;
- distinct issuer count;
- annual event/coverage table.

The first B0 run is a **plumbing/descriptive development result**, not a formal PASS claim. Dependence-aware inference (calendar-time active portfolio/HAC and clustered robustness) is added before a benchmark can be promoted to formal evidence.

## 4. Phase-1 sequence after B0 plumbing

1. Correct exact-calendar P0 audit and assign A/B/C tier.
2. Run B0 development 2016-2020.
3. Freeze B0 event/dedup/execution/output definitions.
4. Build B2 independent-owner cluster baseline (30 calendar days, >=2 distinct owner CIKs; >=3 as subgroup).
5. Implement a separate canonical Cohen-Malloy-Pomorski research classifier for B1; do not relabel the existing heuristic as canonical.
6. B4 = B1 AND B2.
7. B3 company net buying remains blocked until a complete PIT sale-history contract is verified.
8. Freeze the Phase-1 family, then open only validation 2021-2022.
9. Keep 2023+ sealed until the full research methodology is frozen.

## 5. State flags

Every P0/Phase-1 artifact must include:

- `researchOnly = true`
- `oosOpened = false`
- `productionScoringChanged = false`
- `canonicalReady = false` until the relevant gate is explicitly promoted
- `signalReady = false`
