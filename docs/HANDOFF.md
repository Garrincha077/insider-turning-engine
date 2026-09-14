# Insider Turning Engine — HANDOFF

_Last updated: 2026-09-14_

This is the operational continuation point for a new ChatGPT/Codex session. Read this file first, then `docs/research-log.md` for the detailed research evidence and R-IDs.

## FIRST ACTIONS IN A NEW CHAT

1. Open GitHub repository `Garrincha077/insider-turning-engine`, branch `main`.
2. Read this file and `docs/research-log.md`.
3. Refresh GitHub Actions run **34892106121** (`Hydrate full 2016 Q1 SEC buy research set`). This is the current fallback-aware reference Q1 run.
4. Do **not** use old run **34886766478** as a successful reference. It failed safely on shard 10 because 65 valid 2016-03-31 accessions were not found by the bounded daily-index discovery path.
5. If run 34892106121 completes successfully, verify that workflow **`Continue SEC PIT hydration 2016-2022`** auto-started. It should persist Q1 and then process 2016 Q2 through 2022 Q4 sequentially.
6. Keep sealed OOS **2023+ unopened**.
7. Do **not** change production scoring, weights, thresholds, signal states, alerts, or production methodology unless the owner explicitly asks. Research-only data/acquisition tooling is authorized.

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
- `docs/research-log.md` and this handoff;
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

## CORE RESEARCH FILES

Research notebook:

- `docs/research-log.md`

Operational handoff:

- `docs/HANDOFF.md`

Research SEC workflows:

- `.github/workflows/research-sec-history.yml`
- `.github/workflows/research-sec-candidates.yml`
- `.github/workflows/research-sec-hydration-pilot.yml`
- `.github/workflows/research-sec-hydration-scale-pilot.yml`
- `.github/workflows/research-sec-hydration-v2-pilot.yml`
- `.github/workflows/research-sec-hydration-2016q1.yml`
- `.github/workflows/research-sec-hydration-history.yml`

Research hydration scripts:

- `scripts/research_sec_hydrate.py`
- `scripts/research_sec_hydrate_with_fallback.py`
- `scripts/research_sec_hydrate_quarter.py`
- `scripts/research_sec_hydrate_quarter_v2.py`

Important existing architecture:

- `src/insider_turning_engine/normalization/amendments.py`
- `src/insider_turning_engine/features/opportunistic.py`
- `src/insider_turning_engine/ingestion/market/csv_provider.py`
- `src/insider_turning_engine/ingestion/market/stooq.py`
- `src/insider_turning_engine/ingestion/market/yahoo_chart.py`
- `config/scoring.v1.yaml`
- `config/scoring.v1.lock.json`

---

## DATA STATUS

### Raw SEC ownership history 2016–2022

Completed successfully:

- years: **2016–2022**
- quarters: **28/28**
- verified annual research artifacts: **7**
- approximate total artifact size: **234 MB**

Raw quarterly bulk data is not sufficient for a PIT backtest because it does not provide exact public acceptance timestamps.

### Candidate universe

Candidate-universe workflow run: **34884538222**.

Across 2016–2022:

- total P/S candidate filings: **390,314**
- filings containing purchases: **119,727**

The first benchmark is intentionally buy-first. Sales are a later dedicated tournament.

### Amendments

Across 2016–2022:

- amendment filings: **6,301**
- amendment filings containing buys: **2,806**

Buy amendments are about **2.3%** of the buy universe, so they are a separate enrichment/lifecycle gate rather than a reason to block all original-buy hydration.

---

## PIT HYDRATION RESULTS SO FAR

### 100-filing pilot

- 100/100 discovered
- 100/100 hydrated/parsed
- 0 failures
- 0 quarantines
- all canonical rows: `knowledge_at == SEC accepted_at`

Clock rule:

> Historical availability is SEC `accepted_at`. The 2026 research retrieval timestamp stays separately in `recorded_at/retrieved_at/provenance` and must never become historical `knowledge_at`.

### 500-filing scale pilot

Initial result: **498/500**. Two failures were valid legacy SEC dates such as `2016-01-04-05:00`, not throttling or missing filings.

A research-only normalizer was added with a narrow rule:

- only `transactionDate` shaped `YYYY-MM-DD±HH:MM` becomes `YYYY-MM-DD`;
- preserve original XML hash and normalized XML hash;
- count every transformed value;
- fail closed outside the exact legacy pattern.

### 500-filing V2

- **500/500** parsed
- **0 failures**
- **0 quarantines**
- **2,029 canonical rows**
- **1,876 open-market purchase rows**
- only **2 filings / 4 values** normalized
- 100% `knowledge_at == accepted_at`
- observed throughput around **4.63 filings/sec**

---

## 2016 Q1 REFERENCE QUARTER — CURRENT STATUS

Universe:

- **5,482 original-buy filings**
- 11 shards of at most 500
- `max-parallel=1`

### Old run — FAILED SAFELY

Old run ID: **34886766478**.

Shards 0–9 passed. Shard 10 selected 482 filings but the original bounded daily-index discovery found only 417. There were **65 failures**, all with bulk filing date **2016-03-31**.

This was diagnosed as a quarter-end discovery edge case rather than random SEC failures. The run must remain recorded as failed; do not relabel it as PASS.

### Audited accession archive fallback

Research-only fallback added in `scripts/research_sec_hydrate_with_fallback.py`.

Primary path remains official daily index. Fallback is allowed only for the exact failure class:

- stage `DISCOVERY`
- reason `ACCESSION_NOT_FOUND_WITHIN_10_DAYS`

Fallback derives the deterministic EDGAR complete-submission archive path from the accession and still requires:

- exact accession header;
- issuer CIK matching quarterly bulk evidence;
- valid ownership XML;
- exact SEC `accepted_at`;
- canonical `knowledge_at == accepted_at`;
- actual retrieval retained separately as `recorded_at`;
- explicit fallback provenance.

Fallback provenance includes `discovery = accession_archive_fallback`; it must never be represented as a daily-index match.

### New reference run — ACTIVE

Current Q1 run ID: **34892106121**.

At the latest handoff refresh:

- shard 0: PASS
- shard 1: PASS
- shard 2: in progress
- remaining shards queued
- no failure had appeared in the new run at that snapshot

**Always refresh run 34892106121 before acting on this snapshot.**

Expected critical test is shard 10. It should be allowed to show fewer daily-index matches than selected filings only if audited archive fallback closes the gap, `discoveredFilings == selectedOriginalBuyFilings`, all filings parse, `failureCount == 0`, and the PIT clock gate remains true.

---

## AUTOMATED CONTINUATION 2016 Q2–2022 Q4

Workflow:

- `.github/workflows/research-sec-hydration-history.yml`
- name: **`Continue SEC PIT hydration 2016-2022`**
- persistent research prerelease tag: **`research-sec-pit-v1`**

Behavior:

1. Auto-triggers only when `Hydrate full 2016 Q1 SEC buy research set` completes with **success**.
2. Persists audited 2016 Q1 without re-fetching SEC.
3. Processes **2016 Q2 through 2022 Q4** in a matrix of 27 quarters.
4. `max-parallel=1` keeps only one quarter active at a time.
5. Each quarter calculates/runs bounded shards of 500 with 4 workers.
6. Each shard/quarter is fail-closed.
7. Passing quarter is packaged as `sec-pit-YYYYqQ.tar.gz`.
8. Passing quarter is uploaded as a durable GitHub Release asset under `research-sec-pit-v1`.
9. If the release asset already exists, that quarter is skipped on rerun — the pipeline is resume-safe.
10. Final completeness gate requires all **28 quarters 2016 Q1–2022 Q4** to be persistently present.
11. It creates annual manifests plus `sec-pit-2016-2022-index.json`.
12. Final original-buy status becomes `ORIGINAL_BUY_PIT_2016_2022_PASS` only when all 28 archives exist.

Important: even after that status, full Phase 0 is **not** complete. The generated index intentionally keeps:

- `amendmentsReconciled = false`
- `marketDataJoined = false`
- `canonicalReady = false`
- `signalReady = false`
- `oosOpened = false`

The workflow matrix contains **no 2023+ period**.

---

## QUARTER AUDIT / ARCHIVE CONTRACT

`research_sec_hydrate_quarter.py` / `quarter_v2.py` merge and audit the whole quarter.

Hard checks include:

- exact candidate-accession coverage;
- contiguous shard offsets;
- zero remaining failures;
- unique canonical transaction IDs;
- unique revision IDs;
- unique exact SEC row identities;
- `knowledge_at == accepted_at` for all canonical rows;
- OOS unopened;
- explicit amendment-not-yet-reconciled status.

A passing quarter emits:

- `quarter-summary.json`
- `checksums.json`
- `raw-manifest.jsonl`
- `canonical-research.jsonl`
- `failures.jsonl`

Actions artifacts remain temporary diagnostics. Durable PASS data belongs in the release archive, not large git history.

---

## Q1 QUALITY AUDIT BEFORE THE EDGE-CASE FIX

Audit of the first 2,000 successfully hydrated filings showed:

- **8,347 canonical rows**
- **7,995 open-market purchase rows**
- **0 duplicate transaction IDs**
- **0 duplicate revision IDs**
- **0 duplicate exact SEC row identities**
- historical ticker on about **98.6% of purchase rows**
- unresolved ticker evidence concentrated in only **10 issuer CIKs**
- only **22 purchase rows** lacked positive price

CIK is the stable issuer key. Ticker is a valid-time attribute. The filing's contemporaneous `issuerTradingSymbol` can be used as historical ticker evidence from `accepted_at` onward. Do not project today's SEC ticker map backwards.

---

## WARM-UP HISTORY — REQUIRED NEXT GATE

For historical-behaviour features, the research history cannot start at 2016.

Add at least **2013–2015 ownership history as warm-up**.

Reasons:

- `FIRST_BUY_3Y` requires earlier purchase visibility;
- canonical Cohen–Malloy–Pomorski routine/opportunistic classification uses approximately three previous years;
- canonical CMP is fundamentally **trader/reporting-owner level across issuers**, while the current proprietary implementation uses same `owner_cik + issuer_cik` history.

2013–2015 is warm-up only, not an added tuning/OOS window unless methodology is explicitly changed and documented.

---

## AMENDMENT POLICY

Historical `4/A`/`5/A` handling stays deterministic and PIT-safe.

Use explicit evidence such as `dateOfOriginalSubmission`, issuer/owner identity and exact row evidence. Do not fuzzy-match by approximate price/date/share count.

PIT lifecycle rule:

- original record remains effective until amendment becomes public;
- corrected state becomes effective only from amendment `accepted_at`;
- never rewrite history as if a later correction was known at original filing time;
- ambiguous predecessor links go to quarantine.

---

## MARKET DATA PLAN

Current Yahoo/Stooq paths are not sufficient as the sole research provider:

- Yahoo adapter is experimental and around 2 years;
- current Stooq implementation is unadjusted.

Keep architecture vendor-neutral:

`historical market provider -> canonical market CSV -> existing backtester`

Existing `CsvMarketDataProvider` already supports deterministic OHLCV, `adj_close`, adjustment flags/basis, split factor and PIT daily availability.

Current provider direction:

- EODHD: leading candidate for primary historical US price/universe because delisted history is explicitly available;
- Tiingo: strong cross-check/alternative for raw + adjusted OHLCV and split/dividend factors.

Required before formal benchmark claims:

- adjusted daily OHLCV;
- delisted securities;
- historical ticker/security identity;
- missing/stale bar accounting;
- SPY benchmark;
- delayed-entry/MAE capability;
- trailing dollar ADV.

Do not silently drop firms that later delisted.

---

## PIT MARKET CAP / LIQUIDITY

Do not use current market cap historically.

Planned structure:

- price/volume from historical market provider;
- shares outstanding from PIT evidence, with SEC Companyfacts as the preferred free CIK-keyed base;
- map shares facts through accession to exact public acceptance time;
- market cap = PIT shares × contemporaneous price;
- trailing dollar ADV from canonical market bars;
- add scaling/tagging sanity checks for SEC shares-outstanding facts.

---

## PREDECLARED PHASE-1 SIMPLE BENCHMARK

Do not optimize the full Turning Engine first.

Primary event unit: **issuer-session**, not transaction row.

Core eligibility:

- public ownership filing;
- non-derivative open-market purchase (`P`);
- information available only from SEC `accepted_at` onward;
- baseline entry at next eligible session open.

Horizons:

- 21 sessions
- 63 sessions
- 126 sessions
- 252 sessions

Diagnostics:

- raw return;
- SPY excess;
- mean and median;
- win rate;
- downside tail;
- MAE;
- event count;
- attrition/missing outcomes;
- delisting-aware outcomes.

Simple benchmark family includes any qualified purchase, predefined dollar buckets, unique buyer count, independent-owner cluster, simple company-level aggregated buying, and canonical opportunistic benchmark once warm-up history is ready.

---

## DEVELOPMENT / VALIDATION / OOS BOUNDARY

- warm-up: **2013–2015** history only
- development: **2016–2020**
- validation: **2021–2022**
- sealed OOS: **2023+**

Do not open OOS until transaction eligibility, transforms, benchmark family, weights/thresholds, dedup policy, inference, execution, missing-data policy and subgroup reports are frozen.

---

## NEXT EXECUTION SEQUENCE

1. Refresh **Q1 run 34892106121**.
2. If it fails, inspect and fix only the precise research/data issue; do not force continuation.
3. If it passes, verify **`Continue SEC PIT hydration 2016-2022`** auto-started.
4. Verify Q1 was finalized and persisted as `sec-pit-2016q1.tar.gz` under release tag `research-sec-pit-v1`.
5. Monitor sequential quarter PASS archives for 2016 Q2–2022 Q4; failed quarters must stop/fail closed rather than be silently skipped.
6. When all 28 are present, verify `sec-pit-2016-2022-index.json` says `ORIGINAL_BUY_PIT_2016_2022_PASS` and still says amendments/market/canonical/signal readiness are false.
7. Build **2013–2015 warm-up ownership history**.
8. Add deterministic **PIT amendment reconciliation** and report quarantine rate.
9. Finalize historical security/ticker/delisting contract.
10. Acquire and normalize adjusted/delisted market history through canonical CSV.
11. Add PIT shares outstanding / market cap / dollar ADV.
12. Freeze Phase-0 dataset manifest.
13. Run the **Simple Insider Buy baseline**.
14. Only after baseline integrity is established, begin the feature tournament.

---

## WHAT COUNTS AS FULL PHASE-0 PASS

Do not declare formal research readiness until all are demonstrated:

- ownership history including warm-up;
- exact public-availability evidence;
- amendments handled PIT;
- historical issuer/security/ticker identity auditable;
- delisted securities represented;
- adjusted OHLCV/corporate actions reconciled;
- market-cap/liquidity controls available or explicit missingness reported;
- coverage/attrition matrices by year/universe strata;
- durable hashes/manifests/storage;
- sealed OOS unopened.

Until then, model-feature results are exploratory / `NOT_EVALUATED`, not formal `PASS` or `FAIL`.

---

## NEW-CHAT PROMPT

> Open `Garrincha077/insider-turning-engine`, read `docs/HANDOFF.md` and `docs/research-log.md`, refresh Q1 Actions run `34892106121`, then continue from NEXT EXECUTION SEQUENCE. If Q1 is PASS, verify `Continue SEC PIT hydration 2016-2022` auto-started. Do not open 2023+ OOS or change production scoring unless I explicitly ask.
