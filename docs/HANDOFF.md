# Insider Turning Engine — HANDOFF

_Last updated: 2026-09-18_

This is the operational continuation point for a new ChatGPT/Codex session. Read this file first, then `docs/research-log.md`, `docs/research-predeclared-spec.md`, and `docs/P0_PHASE1_IMPLEMENTATION.md`.

## FIRST ACTIONS IN A NEW CHAT

1. Open GitHub repository `Garrincha077/insider-turning-engine`, branch `main`.
2. Treat SEC original-buy PIT history 2016-2022, warm-up 2013-2015, and amendment reconciliation as completed research-data stages.
3. Treat the exact-calendar P0 market audit as the authoritative market-data gate. Current tier: **C_EXPLORATORY**.
4. Treat the first B0 development run as a descriptive/plumbing baseline only, not formal alpha evidence.
5. Keep sealed OOS **2023+ unopened**.
6. Do **not** change production scoring, weights, thresholds, signal states, alerts, or production methodology unless the owner explicitly asks.

---

## PROJECT GOAL

Build an empirically defensible **Insider Turning Engine** that distinguishes genuinely informative insider purchases from noise and then tests whether post-purchase turning/technical confirmation adds incremental value.

Validation order:

`clean PIT data -> simple insider baseline -> feature tournament -> turning overlay -> statistical robustness -> frozen validation -> sealed OOS -> shadow production`

The engine must beat transparent simple insider benchmarks on development/validation data before sealed OOS is opened.

---

## CHANGE BOUNDARY

Authorized without another confirmation:

- literature/data research;
- research docs/specifications;
- research-only acquisition/hydration scripts and GitHub Actions workflows;
- audits, hashes, manifests, PIT validation and data-quality reporting;
- development/validation dataset preparation while OOS remains sealed.

Not authorized without explicit owner instruction:

- production scoring/weight/threshold changes;
- replacing production feature logic based on research results;
- opening/tuning on 2023+ OOS;
- enabling production signal delivery;
- presenting exploratory results as production evidence.

---

## VERIFIED SEC PIT DATA STATUS

### Original-buy PIT history 2016-2022 — COMPLETE

Workflow run: **34974573538** (`Continue SEC PIT hydration 2016-2022`)  
Persistent release: **`research-sec-pit-v1`**

- 28/28 quarters PASS;
- PIT clock remains `knowledge_at == SEC accepted_at`;
- persistent quarter archives and full-history index exist;
- OOS remained closed.

### Warm-up 2013-2015 — COMPLETE

Workflow run: **35060455633** (`Build SEC PIT warm-up 2013-2015`)  
Persistent release: **`research-sec-warmup-v1`**

- all 12 quarterly jobs passed;
- completeness gate passed;
- warm-up is history context only, not an extra tuning period.

### Amendment reconciliation 2013-2022 — COMPLETE

Workflow run: **35115489296**  
Research status: PASS.

Key counts:

- original canonical rows: 573,322;
- amendment canonical rows: 102,901;
- linked amendment rows: 9,619;
- effective rows end-2022: 573,322;
- research quarantine rows: 18,916;
- resolver quarantine rows: 16.

Policy remains deterministic/PIT-safe: original state remains effective until amendment acceptance; ambiguous predecessor links are quarantined rather than fuzzily matched.

---

## 2026-09-18 B3 P/S SALE-HISTORY STATUS

B3 remains blocked on complete PIT buy/sale history. No B3 signal formula or performance has been opened.

### Frozen P/S universe and pilot

A separate original P/S PIT contract is frozen in
`docs/research-phase1-b3-ps-pit-history-gate.md`.

Universe:

- original Form 4/5 only;
- 2013-2022 only;
- priced positive-share non-derivative `P/A` buys or `S/D` sales;
- SEC `accepted_at` remains the historical knowledge clock;
- 2023+ remains sealed.

Frozen 2016 Q1 pilot:

- workflow run: **35282934646**;
- artifact: `phase1-b3-ps-pit-pilot-35282934646`;
- artifact digest:
  `sha256:0ddaff2b57329c29537146fe3ec7fb5c4c19127b543dd08f85965c5653b33aa1`;
- 13,088 / 13,088 original P/S filings hydrated;
- zero failures;
- buy accession concordance: 5,482 / 5,482 = **100%**;
- sale accession concordance: 7,664 / 7,664 = **100%**;
- predeclared threshold was >=99.5% separately for both sides;
- `oosOpened=false`;
- `productionScoringChanged=false`.

The pilot is frozen and its workflow is manual-rerun only.

### Full original P/S history

Persistent research release: **`research-sec-ps-pit-v1`**.

Source universe:

- 2013-2022 original P/S filings: **570,291**;
- buy-only: 168,334;
- sale-only: 400,230;
- mixed buy/sale: 1,727;
- sale-only filings are about 70.18% of the P/S filing universe.

This confirms the earlier buy-centric history cannot serve as a complete B3 denominator.

Persistent quarters at the latest checkpoint:

- 2013 Q1-Q4: PASS;
- 2014 Q1-Q2: PASS;
- 2016 Q1 frozen pilot quarter: PASS;
- persistent total: **7 / 40**.

The hydration matrix is resumable with `fail-fast: false`; a failed quarter no longer discards later independent work.

### 2014 Q3 discovery incident

2014 Q3 repeatedly failed the unchanged 100% coverage gate:

`P/S accession discovery is incomplete`

This is a filing-discovery/data-quality issue, not a signal/performance result.

Do not lower the 100% coverage requirement.

Recovery rule is documented in
`docs/progress-2026-09-18-b3-ps-2014q3-discovery-incident.md`.

The verified archive fallback now uses:

1. frozen quarterly-bulk **issuer CIK** as the primary archive directory;
2. distinct verified **reporting-owner CIKs** as secondary archive paths;
3. no fuzzy matching, ticker mapping, future information or market outcomes.

All recovered filings must still pass exact accession/header, issuer-CIK,
ownership-XML, SEC acceptance datetime and `knowledgeAt == acceptedAt` checks.

Recovery implementation and synthetic attempt-order tests are CI green.

Latest recovery/backfill run queued after the active resumable run:
**35363456434**, commit
`27e29d3a03a89ff480eb54ed4c0648e4bac10594`.

### Broader P/S amendment gate

Predeclared in
`docs/research-phase1-b3-ps-amendment-gate.md`.

The gate explicitly covers:

- amendments whose root is already in the P/S universe;
- qualified P/S amendments that require a supporting predecessor outside the
  original P/S universe;
- zero-transaction Form 4/A and 5/A on P/S roots;
- ambiguous chains via quarantine, never fuzzy matching.

The deterministic amendment-scope builder and tests are CI green.

Do **not** run B3 development performance until:

1. all 40 original P/S quarters pass;
2. broader P/S amendment reconciliation passes;
3. the actual B3 company-net-buying definition is separately frozen before
   observing B3 development outcomes.


---

## P0 MARKET DATA — AUTHORITATIVE EXACT-CALENDAR GATE

Authoritative workflow run: **35235518480**  
Status: **PASS_EXPLORATORY**  
Tier: **C_EXPLORATORY**

The previous audit used a stock's own available regular-bar dates and could therefore substitute a later available stock bar for a missing exact exchange session. That logic is superseded.

The authoritative v2 audit uses:

- XNYS/SPY as the exact session calendar;
- evaluation from `knowledgeAt`;
- entry on the exact next XNYS session open;
- exact 21/63/126/252-session target dates;
- no nearest/later-bar substitution;
- true study-boundary censoring only when the required XNYS session lies beyond 2022;
- terminal candidates excluded from ordinary sessions;
- missing outcomes never imputed.

### Current P0 metrics

- qualified issuer-session purchase events: **82,048**;
- identity eligible events: **79,643**;
- study-boundary censored before entry: **48**;
- assessable exact-entry events: **79,595**;
- exact entry matched: **70,547**;
- exact-entry coverage: **88.6325%**;
- missing/placeholder identity: **2.8093%**;
- identity ambiguity among usable tickered events: **0.1254%**;
- total identity problem rate: **2.9312%**;
- SPY session coverage: **100% (1,762/1,762)**;
- worst single-year exact-entry coverage: **84.8934% (2016)**.

Entry coverage by knowledge year:

- 2016: 84.8934%
- 2017: 86.2871%
- 2018: 87.9348%
- 2019: 88.1405%
- 2020: 90.6932%
- 2021: 90.0465%
- 2022: 91.8611%

### Locked tier thresholds

| Metric | A — High confidence | B — Research grade | C — Exploratory |
|---|---:|---:|---:|
| Exact-entry coverage | >=95% | >=90% | >=80% |
| Missing/placeholder identity | <=1% | <=3% | <=7.5% |
| Identity ambiguity | <=0.5% | <=1% | <=2% |
| Total identity problem | <=1.5% | <=4% | <=9% |
| Worst-year exact-entry coverage | >=90% | >=85% | >=70% |
| SPY/XNYS coverage | 100% | >=99.5% | >=99% |

Current data pass all Tier C requirements. Tier B fails on total exact-entry coverage (88.63% < 90%) and narrowly on worst-year coverage (84.89% < 85%). Do not lower thresholds based on B0 performance.

State after P0:

- `marketDataJoined = true` for exploratory research;
- `highConfidenceMarketDataJoined = false`;
- `canonicalReady = false`;
- `signalReady = false`;
- `oosOpened = false`;
- `productionScoringChanged = false`.

---

## PHASE-1 B0 DEVELOPMENT BASELINE — COMPLETE

Workflow run: **35235518475**  
Persistent release: **`research-phase1-baselines-v1`**  
Benchmark: **`B0_ANY_QUALIFIED_PURCHASE`**  
Status: **`PHASE1_B0_DEVELOPMENT_DESCRIPTIVE_COMPLETE`**

Scope:

- event cohort: 2016-2020 development only;
- market outcomes bounded to 2016-2022;
- 2021-2022 performance was not used as B0 validation;
- 2023+ remained sealed;
- exact XNYS evaluation/entry/exit sessions;
- 20-session issuer-CIK dedup;
- primary horizon: 126 sessions.

Selection:

- development identity-eligible candidates: **57,142**;
- dedup suppressed: **29,388**;
- retained after dedup: **27,754**;
- exact-entry matched: **24,192**;
- entry attrition after dedup: **3,562**;
- distinct issuers with entry: **4,729**.

### B0 descriptive outcomes

| Horizon | Matured | Raw mean | Raw median | SPY excess mean | SPY excess median | Excess win rate |
|---:|---:|---:|---:|---:|---:|---:|
| 21 | 23,902 | +2.41% | +1.40% | +0.71% | -0.46% | 47.59% |
| 63 | 23,739 | +8.55% | +3.62% | +3.42% | -1.21% | 46.47% |
| 126 | 23,504 | +15.05% | +6.38% | +5.20% | -2.80% | 44.72% |
| 252 | 22,792 | +29.18% | +10.55% | +9.57% | -7.01% | 41.45% |

Primary 126-session downside/MAE diagnostics:

- SPY excess p05: **-51.71%**;
- SPY excess p10: **-38.37%**;
- MAE observed count: **21,750**;
- MAE mean: **-20.54%**;
- MAE median: **-13.94%**.

Interpretation is intentionally limited: B0 shows a positive arithmetic mean but a negative excess-return median and sub-50% win rate at every tested horizon. That pattern is consistent with a right-skewed distribution in which a minority of large winners can lift the mean. It is **not** formal evidence of persistent alpha. Dependence-aware calendar-time/HAC and clustered robustness remain required before any formal PASS claim.

---

## PIT / QUALITY CONTRACT

For all research periods:

- exact candidate/accession provenance;
- `knowledge_at == accepted_at` for SEC-derived historical knowledge;
- actual retrieval time retained separately;
- explicit source/fallback provenance;
- historical identity cannot be inferred from current ticker/current market cap;
- missing observations remain explicit attrition;
- no signal readiness implied by data-acquisition success;
- OOS stays sealed until methodology is frozen.

---

## PHASE-1 BENCHMARK FAMILY

B0 — any qualified open-market purchase: development plumbing complete.

Next planned research baselines:

- **B2 independent-owner cluster:** primary definition 30 calendar days and >=2 distinct owner CIKs; >=3 owners secondary subgroup.
- **B1 canonical opportunistic:** implement separately from the existing custom opportunistic heuristic; do not call the current heuristic canonical Cohen-Malloy-Pomorski.
- **B4:** B1 AND B2.
- **B3 company net buying:** BLOCKED until a complete PIT sale-history contract is verified. Do not compute company buy/sell ratios from a buy-centric historical universe.

Required horizons remain 21/63/126/252 XNYS sessions, with 126 primary.

Formal inference must not rely only on IID event bootstrap. Add calendar-time equal-weight active-signal portfolio inference with HAC/Newey-West and clustered robustness before promoting a benchmark to formal evidence.

---

## DEVELOPMENT / VALIDATION / OOS BOUNDARY

- warm-up: **2013-2015** history/context only
- development: **2016-2020**
- validation: **2021-2022**
- sealed OOS: **2023+**

Do not open OOS until transaction eligibility, transforms, benchmark family, feature definitions, weights/thresholds, deduplication policy, inference, execution rule, missing-data policy, and OOS subgroup reports are frozen.

---

## NEXT EXECUTION SEQUENCE

1. Add synthetic regression tests for exact-session entry/horizon handling and tier selection; GitHub issue **#1** tracks this work.
2. Freeze the B0 event/dedup/execution/reporting contract after tests.
3. Build **B2 independent-owner cluster** on development 2016-2020 using the same exact-calendar outcome layer.
4. Implement the **canonical CMP** research classifier as B1, using 2013-2015 warm-up history where required; keep the existing heuristic separate.
5. Build B4 = B1 AND B2.
6. Verify/build a complete PIT sale-history universe before unblocking B3.
7. Add calendar-time/HAC and clustered robustness to Phase-1 baselines.
8. Freeze Phase-1 definitions before opening validation 2021-2022 performance.
9. Only after validation and methodology freeze may the owner consider authorizing sealed 2023+ OOS.

---

## DO NOT DO

- Do not inspect 2023+ filings, market outcomes, or performance without explicit owner authorization.
- Do not tune production `config/scoring.v1.yaml` or `config/scoring.v1.lock.json` from exploratory results.
- Do not treat data-gate PASS or a positive B0 mean as evidence of alpha.
- Do not classify missing historical 10b5-1 structured data as confirmed non-plan trading.
- Do not use current ticker or market-cap mappings as historical truth.
- Do not silently substitute a later bar when an exact XNYS session is missing.
- Do not silently drop missing or delisted outcomes.
