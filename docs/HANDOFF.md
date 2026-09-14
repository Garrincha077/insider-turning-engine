# Insider Turning Engine — HANDOFF

_Last updated: 2026-09-14_

This file is the operational continuation point for a new ChatGPT/Codex session. Read this file first, then `docs/research-log.md` for the detailed research evidence and R-IDs.

## FIRST ACTIONS IN A NEW CHAT

1. Connect to GitHub and open repository `Garrincha077/insider-turning-engine`, branch `main`.
2. Read this file and `docs/research-log.md`.
3. Refresh GitHub Actions run **34886766478** (`Hydrate full 2016 Q1 SEC buy research set`) before assuming the status below is still current.
4. If all 11 hydration shards and the completeness gate are green, perform the final 2016 Q1 audit before scaling further.
5. Keep sealed OOS **2023+ unopened**.
6. Do **not** change production scoring, weights, thresholds, signal states, alerts, or production methodology unless the owner explicitly asks. Research-only data/acquisition tooling is in scope because the owner explicitly asked to expand the dataset and continue.

---

## PROJECT GOAL

Build an empirically defensible **Insider Turning Engine** that distinguishes genuinely informative insider purchases from noise and then tests whether post-purchase turning/technical confirmation adds incremental value.

The validation order is deliberately conservative:

`clean PIT data -> simple insider baseline -> feature tournament -> turning overlay -> statistical robustness -> frozen validation -> sealed OOS -> shadow production`

The project must beat transparent simple insider benchmarks on development/validation data before the sealed OOS is opened.

---

## REPOSITORY / IMPORTANT FILES

Repository: `Garrincha077/insider-turning-engine`

Main research notebook:

- `docs/research-log.md`

Current research/data workflows:

- `.github/workflows/research-sec-history.yml`
- `.github/workflows/research-sec-candidates.yml`
- `.github/workflows/research-sec-hydration-pilot.yml`
- `.github/workflows/research-sec-hydration-scale-pilot.yml`
- `.github/workflows/research-sec-hydration-v2-pilot.yml`
- `.github/workflows/research-sec-hydration-2016q1.yml`

Important research hydration code:

- `scripts/research_sec_hydrate.py`

Important existing production/research architecture:

- `src/insider_turning_engine/normalization/amendments.py`
- `src/insider_turning_engine/features/opportunistic.py`
- `src/insider_turning_engine/ingestion/market/csv_provider.py`
- `src/insider_turning_engine/ingestion/market/stooq.py`
- `src/insider_turning_engine/ingestion/market/yahoo_chart.py`
- `config/scoring.v1.yaml`
- `config/scoring.v1.lock.json`

---

## OWNER'S CHANGE BOUNDARY

Original instruction was: **do not change production code/scoring, research is allowed**.

The owner later explicitly authorized:

- creating/updating `docs/research-log.md`;
- expanding the historical dataset;
- continuing research/data-enablement work.

Therefore:

### Allowed without another confirmation

- Literature/data research.
- Updating `docs/research-log.md` and this handoff.
- Research-only acquisition/hydration scripts and GitHub Actions workflows.
- Audits, manifests, hashes, PIT validation, data-quality reporting.
- Development/validation dataset preparation while OOS stays sealed.

### Not authorized without explicit owner instruction

- Changing production scoring weights or thresholds.
- Replacing current production feature logic because a research hypothesis looks better.
- Opening or tuning against 2023+ OOS.
- Enabling production alerts/signal delivery.
- Treating experimental backtests as production evidence.

---

## CURRENT DATA STATUS

### Raw SEC history 2016–2022

Research-only quarterly SEC backfill has completed successfully for the entire development + validation window:

- years: **2016–2022**
- quarters: **28/28**
- annual verified research artifacts: **7**
- approximate total artifact size: **234 MB**

This solved the raw-history acquisition problem but did **not** by itself make the data backtest-ready because quarterly bulk history does not provide exact SEC acceptance timestamps.

### Candidate universe

Candidate-universe workflow reduced the raw SEC set to economically relevant ownership filings.

Across 2016–2022:

- total P/S candidate filings: **390,314**
- filings containing purchases: **119,727**

The Phase-1 strategy is intentionally **buy-first**. Sales can be hydrated later for the dedicated sales tournament rather than slowing the first purchase benchmark.

### Amendment census

Across 2016–2022:

- amendment filings: **6,301**
- amendment filings containing buys: **2,806**

Buy amendments are only about **2.3%** of the buy universe, so amendments should be handled as a dedicated enrichment/lifecycle layer instead of blocking all original-buy hydration.

---

## EXACT PIT HYDRATION RESULTS

### 100-filing pilot

The initial exact-history hydration pilot recovered the SEC complete submission, exact `<ACCEPTANCE-DATETIME>`, primary ownership XML and canonical transactions.

Result:

- 100/100 matched in SEC daily index
- 100/100 hydrated and parsed
- 0 failures
- 0 quarantines
- all canonical rows satisfied `knowledge_at == SEC accepted_at`

Important clock rule discovered here:

> Historical public availability is **SEC `accepted_at`**. The 2026 research retrieval timestamp must remain separate as `recorded_at/retrieved_at/provenance` and must never become historical `knowledge_at`.

### 500-filing scale pilot

Initial scale result:

- 498/500 successful
- two failures were **not** SEC throttling or missing filings
- both came from a legacy valid SEC transaction-date representation such as `2016-01-04-05:00`

The production parser was **not loosened**.

A research-only historical normalizer was added with a deliberately narrow rule:

- only normalize `transactionDate` shaped `YYYY-MM-DD±HH:MM` to the date portion;
- preserve original SEC XML hash;
- preserve normalized XML hash;
- count every transformed value;
- fail closed outside that specific legacy pattern.

### 500-filing V2 pilot

Result:

- **500/500** matched
- **500/500** parsed
- **0 failures**
- **0 quarantines**
- **2,029 canonical rows**
- **1,876 open-market purchase rows**
- only **2 filings / 4 transaction-date values** needed legacy normalization
- 100% of canonical rows had `knowledge_at == accepted_at`
- observed throughput about **4.63 filings/sec** in that run

This validated the research hydration approach well enough to run a complete quarter.

---

## ACTIVE 2016 Q1 FULL HYDRATION

Workflow:

- `.github/workflows/research-sec-hydration-2016q1.yml`
- GitHub Actions run ID: **34886766478**
- run head SHA: **08df3a918254ce8f2e6576dbaceee716ec5d81af**

Universe:

- **5,482 original buy filings** in 2016 Q1
- 11 shards, maximum 500 filings each
- `max-parallel=1` intentionally limits SEC load
- each shard must pass:
  - all selected accessions matched in daily index;
  - all selected filings hydrated/parsed;
  - failure count = 0;
  - all canonical `knowledge_at == accepted_at`;
  - OOS remains unopened.

### Snapshot at creation of this handoff

- **9/11 shards completed successfully**
- shard **9** in progress
- shard **10** queued
- **0 failed shards so far**

Do not assume this snapshot is current in a later chat. **Refresh run 34886766478 first.**

---

## 2016 Q1 QUALITY AUDIT ALREADY PERFORMED

Audit of the first 2,000 hydrated filings showed:

- **8,347 canonical rows**
- **7,995 open-market purchase rows**
- **0 duplicate transaction IDs**
- **0 duplicate revision IDs**
- **0 duplicate exact SEC row identities**
- historical ticker present on about **98.6% of purchase rows**
- unresolved purchase ticker evidence concentrated in only **10 issuer CIKs**
- only **22 purchase rows** lacked price

This is encouraging: current defects look localized rather than systemic.

The filing's contemporaneous `issuerTradingSymbol` is usable as historical ticker evidence from its acceptance time onward. **CIK remains the stable issuer key; ticker is a valid-time attribute.** Do not backfill today's SEC ticker map into the past.

---

## WARM-UP HISTORY REQUIREMENT — IMPORTANT

Do not start the final research history at 2016 if testing historical-behaviour features.

At minimum add **2013–2015 ownership history as warm-up** for 2016 development events.

Why:

- `FIRST_BUY_3Y` needs three years of earlier purchase visibility.
- The canonical Cohen–Malloy–Pomorski routine/opportunistic classification uses approximately three previous years of insider trading history.
- Crucially, the canonical classification is based on an **insider's trading pattern across issuers**, whereas the current proprietary implementation in `features/opportunistic.py` uses same `owner_cik + issuer_cik` history.

Therefore, for a proper canonical CMP benchmark, warm-up acquisition must preserve **reporting-owner CIK history across all issuers**, not only earlier transactions in the same company.

2013–2015 is warm-up only. Do not treat it as a new tuning/OOS window unless methodology is explicitly changed and recorded.

---

## AMENDMENT POLICY

Existing `normalization/amendments.py` is intentionally fail-closed and requires deterministic predecessor evidence; it does not fuzzy-match corrections by price/date/share count.

Historical `4/A` enrichment should remain deterministic. SEC amendment forms expose `dateOfOriginalSubmission`, which can help narrow linkage, but an amendment should only supersede an earlier record when the predecessor relationship and exact row identity are auditable.

Any unresolved or ambiguous cross-accession correction should remain quarantined rather than silently double-counted or fuzzily merged.

Important PIT requirement:

- original row is effective until the amendment becomes public;
- corrected row becomes effective only from amendment `accepted_at` onward;
- never retroactively rewrite the historical state as though the corrected information was known from the original filing date.

---

## MARKET DATA PLAN

The current live/experimental providers are not sufficient as the sole historical research source:

- Yahoo chart adapter is intentionally experimental and requests only about 2 years.
- Stooq adapter provides unadjusted OHLCV in the current implementation.

The preferred architecture is:

`historical market provider -> canonical market CSV contract -> existing backtester`

Do **not** couple the backtester directly to one vendor.

`CsvMarketDataProvider` already supports a strict deterministic canonical contract including:

- date/ticker OHLCV
- `adj_close`
- `is_adjusted`
- `adjustment_basis`
- `split_factor`
- PIT daily availability at US session close

Current provider research direction:

- **EODHD** is the leading candidate for primary historical US price/universe data because it explicitly supports delisted symbols/history.
- **Tiingo** is a strong cross-check/alternative because it provides raw + adjusted OHLCV and split/dividend factors.
- This provider choice is **not yet a production lock**. Validate coverage, licensing, delisted handling and corporate-action consistency first.

Required market-history properties before formal benchmark claims:

- adjusted daily OHLCV
- delisted securities included
- ticker changes/security identity handled historically
- missing/stale bar accounting
- SPY benchmark
- ability to calculate delayed-entry tests and MAE
- trailing dollar ADV

Do not silently drop a signal because its company later delisted.

---

## PIT MARKET CAP / LIQUIDITY PLAN

Do not use today's market cap historically.

Planned structure:

- price/volume from the historical market provider;
- shares outstanding from a point-in-time source, with SEC Companyfacts as the preferred free CIK-keyed foundation;
- market cap = PIT shares outstanding × contemporaneous market price;
- trailing dollar ADV calculated from canonical market bars.

For SEC shares-outstanding facts, use the fact's filing/accession to recover the **actual public acceptance timestamp**. A fact filed after the market close must not leak into that day's feature snapshot.

Add sanity/quality controls because SEC shares-outstanding facts can contain tagging/scaling errors.

---

## PERSISTENT DATA STORAGE RISK

Current GitHub Actions research artifacts use finite retention (typically 90 days). That is not sufficient for reproducible long-term research.

Before calling a quarter permanently complete, create a persistent archive strategy with:

- quarter/year identifier
- source/run IDs
- row counts
- failure/quarantine counts
- SHA-256 manifest/dataset hashes
- schema version
- code/workflow commit SHA
- exact PIT clock policy
- OOS-opened = false assertion

Preferred direction: keep source code out of large git history and archive completed research datasets as durable release/object-storage assets plus small manifests in the repo. Verify the actual repository/tool permissions before implementing upload automation.

---

## PREDECLARED PHASE-1 SIMPLE BENCHMARK

Do not optimize the full Turning Engine first.

The first real benchmark should intentionally be simple and hard to manipulate.

Primary event unit:

- **issuer-session**, not transaction row, so a filing with multiple rows/insiders cannot mechanically get extra event weight.

Core eligibility:

- publicly available ownership filing
- non-derivative open-market purchase (`P`)
- information available only from SEC `accepted_at` onward
- evaluate after public availability
- baseline entry: next eligible market-session open

Horizons:

- 21 sessions
- 63 sessions
- 126 sessions
- 252 sessions

Primary diagnostics:

- raw return
- SPY excess return
- mean + median
- win rate
- downside tail
- MAE
- event count
- attrition / missing outcome rate
- delisting-aware outcome handling

Simple benchmark family should include at least:

- any qualified open-market purchase
- dollar thresholds/buckets (e.g. >$100k, >$250k, >$1m as descriptive predefined cuts)
- unique buyer count
- independent-owner cluster buys
- simple company-level aggregated buying
- canonical opportunistic benchmark when warm-up history is ready

Do not select the winning threshold after inspecting OOS.

---

## RESEARCH FINDINGS TO PRESERVE

Full details are in `docs/research-log.md` under R-001 through R-013. High-level conclusions:

- **R-001:** current opportunistic classifier is proprietary and must be compared with canonical Cohen–Malloy–Pomorski classification.
- **R-002:** CEO/CFO/director role priors are not empirically settled; role must earn its weight.
- **R-003:** cluster-buy direction is supported, exact 30-day/2-owner/3-owner thresholds are unvalidated.
- **R-004:** structured 10b5-1 coverage changes materially in 2023; pre-2023 unknown cannot be treated as confirmed non-plan.
- **R-005/R-007:** IID event bootstrap may understate uncertainty; add dependence-aware/calendar-time evidence.
- **R-006:** purchase size matters in some studies, but normalization is unresolved; run a tournament.
- **R-008:** public Form 4 alpha must survive liquidity, delayed entry and capacity tests.
- **R-009:** same-owner purchase sequences and independent-owner clusters are distinct signals.
- **R-010:** `FIRST_BUY_3Y` / re-entry floor of 90 is an unvalidated heuristic.
- **R-011:** sales should be classified; a single generic sale should not automatically act as a binary veto.
- **R-012:** market cap/liquidity are mandatory controls; do not hard-code a small-cap bonus.
- **R-013:** data readiness, not lack of indicators, is the binding research constraint.

---

## DEVELOPMENT / VALIDATION / OOS BOUNDARY

Current intended split:

- **warm-up:** 2013–2015 (history only)
- **development:** 2016–2020
- **validation:** 2021–2022
- **sealed OOS:** 2023 onward through the last complete eligible period

The sealed OOS must remain unopened until transaction eligibility, feature transforms, benchmark family, weights/thresholds, dedup policy, statistics, execution rule, missing-data policy and subgroup reports have been frozen.

A failed OOS is a valid result. Do not retune on the same OOS and relabel it as a new holdout.

---

## NEXT EXECUTION SEQUENCE

When resuming work, follow this order unless new evidence forces a documented change:

1. **Refresh run 34886766478.**
2. If 2016 Q1 all-green, run full-quarter audit across all 5,482 filings and all shard artifacts.
3. Record final Q1 counts/coverage/hash/status in `docs/research-log.md` and update this handoff.
4. Build/verify **2013–2015 warm-up ownership acquisition** across reporting-owner history.
5. Generalize/shard exact PIT hydration for remaining **2016–2022 original-buy filings** without opening OOS.
6. Add deterministic **amendment enrichment** and quantify unresolved/quarantine rate.
7. Finalize historical security/ticker/delisting identity contract.
8. Acquire/normalize adjusted historical OHLCV + delisted coverage through the canonical CSV contract.
9. Add PIT shares-outstanding / market-cap and trailing dollar-ADV layers.
10. Freeze a Phase-0 dataset manifest and persistent storage scheme.
11. Run the **Simple Insider Buy baseline** before testing any full score.
12. Only after the baseline reproduces basic insider-purchase informativeness, start the feature tournament.

---

## WHAT COUNTS AS PHASE-0 PASS

Do not declare the dataset formally research-ready until all of the following are demonstrated:

- required ownership history acquired, including warm-up;
- exact public-availability/acceptance evidence recovered;
- amendments handled point-in-time;
- historical issuer/security/ticker identity auditable;
- delisted securities represented;
- adjusted OHLCV/corporate actions reconciled;
- market cap/liquidity controls available or explicitly reported missing;
- coverage/attrition matrices produced by year and relevant universe strata;
- completed research dataset has durable hashes/manifests/storage;
- sealed OOS remains unopened.

Until then, feature results are `NOT_EVALUATED` or exploratory, not `PASS`/`FAIL` model evidence.

---

## NEW-CHAT PROMPT

If the owner starts a fresh chat, the shortest useful instruction is:

> Open `Garrincha077/insider-turning-engine`, read `docs/HANDOFF.md` and `docs/research-log.md`, refresh Actions run `34886766478`, and continue from the NEXT EXECUTION SEQUENCE. Do not open 2023+ OOS or change production scoring unless I explicitly ask.

This should be enough to continue without reconstructing the old conversation.