# Insider Turning Engine — HANDOFF

_Last updated: 2026-09-16_

This is the operational continuation point for a new ChatGPT/Codex session. Read this file first, then `docs/research-log.md` and `docs/research-predeclared-spec.md` for the research evidence, R-IDs, and frozen/predeclared test definitions.

## FIRST ACTIONS IN A NEW CHAT

1. Open GitHub repository `Garrincha077/insider-turning-engine`, branch `main`.
2. Read this file and `docs/research-log.md`.
3. Treat **2016-2022 original-buy PIT hydration as COMPLETE**. Reference workflow run: **34974573538** (`Continue SEC PIT hydration 2016-2022`).
4. Verify the separate warm-up workflow **`Build SEC PIT warm-up 2013-2015`**, run **35060455633**, before doing new owner-history work.
5. Keep sealed OOS **2023+ unopened**.
6. Do **not** change production scoring, weights, thresholds, signal states, alerts, or production methodology unless the owner explicitly asks. Research-only data/acquisition tooling is authorized.

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
- `docs/research-log.md`, this handoff, and research specifications;
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

## CURRENT VERIFIED DATA STATUS

### 2016-2022 development/validation original-buy PIT history — PASS

Workflow run: **34974573538**  
Workflow: **`Continue SEC PIT hydration 2016-2022`**  
Persistent release: **`research-sec-pit-v1`**

Verified status:

- **28/28 quarters PASS** from 2016 Q1 through 2022 Q4;
- every quarter packaged as a persistent `sec-pit-YYYYqQ.tar.gz` release asset;
- final job **`Original-buy PIT history completeness gate`** passed;
- full-history index `sec-pit-2016-2022-index.json` was produced;
- PIT clock gate remains `knowledge_at == SEC accepted_at`;
- `oosOpened = false`;
- `amendmentsReconciled = false`;
- `marketDataJoined = false`;
- `canonicalReady = false`;
- `signalReady = false`.

This means the original-buy acceptance-time acquisition gate is complete. It does **not** mean Phase 0 is complete or that the engine is ready for performance claims.

### Important historical fix retained

2016 Q1 exposed a quarter-end archive-discovery edge case. The final research-only solution uses verified `REPORTINGOWNER.RPTOWNERCIK` evidence to construct audited accession-archive fallback paths. The fallback is explicit in provenance and remains fail-closed. The generic 2016-2022 continuation workflow subsequently passed all quarters with that reporting-owner enrichment path.

Do not revert to accession-prefix or issuer-CIK archive-directory guessing.

---

## WARM-UP HISTORY — ACTIVE NEXT GATE

Historical-behaviour features require history before 2016.

Required period: **2013-2015**, warm-up only.

Reasons:

- `FIRST_BUY_3Y` requires earlier purchase visibility;
- canonical Cohen-Malloy-Pomorski routine/opportunistic classification uses about three previous years;
- canonical CMP classification is fundamentally reporting-owner/trader history across issuers, not merely same owner + issuer history.

Warm-up must never be silently converted into an additional tuning period.

### Warm-up workflow

Workflow: **`Build SEC PIT warm-up 2013-2015`**  
File: `.github/workflows/research-sec-warmup-2013-2015.yml`  
Initial run: **35060455633**  
Commit introducing it: **37ccb7251df2491a6080b49f673e1c876012ca1b**  
Persistent release: **`research-sec-warmup-v1`**

The workflow is intentionally separate from `research-sec-pit-v1` and performs:

1. official SEC quarterly bulk staging for 2013, 2014, 2015;
2. bounded P/S candidate construction;
3. reporting-owner CIK enrichment from `REPORTINGOWNER.parquet`;
4. exact acceptance-time hydration using the audited fallback-aware quarter runner;
5. per-quarter fail-closed PIT audits;
6. persistent warm-up quarter archives;
7. final 12-quarter completeness gate and warm-up index.

Expected successful terminal status:

`ORIGINAL_BUY_PIT_WARMUP_2013_2015_PASS`

At handoff time, run **35060455633** had successfully created the warm-up release and started **Build warm-up source 2013**; 2014 and 2015 were queued.

---

## PIT / QUALITY CONTRACT

For both warm-up and development/validation history:

- exact candidate-accession coverage;
- zero remaining failures;
- unique canonical transaction IDs;
- unique revision IDs;
- unique exact SEC row identities;
- `knowledge_at == accepted_at` for all canonical rows;
- actual retrieval time retained separately from historical knowledge time;
- explicit source/fallback provenance;
- OOS unopened;
- no signal readiness implied by acquisition success.

Passing quarter archives contain:

- `quarter-summary.json`
- `checksums.json`
- `raw-manifest.jsonl`
- `canonical-research.jsonl`
- `failures.jsonl`

Durable PASS evidence belongs in release assets, not large git history.

---

## AMENDMENT POLICY — NEXT AFTER WARM-UP

Historical `4/A` / `5/A` handling must stay deterministic and PIT-safe.

Rules:

- original record remains effective until an amendment becomes public;
- corrected state becomes effective only from amendment `accepted_at`;
- never rewrite historical state as if the later correction was known earlier;
- predecessor linkage should rely on explicit evidence such as `dateOfOriginalSubmission`, issuer/owner identity, and exact row evidence;
- ambiguous predecessor links go to quarantine rather than fuzzy matching.

After warm-up completes, build amendment reconciliation and report linked, unlinked, and quarantined amendment rates.

---

## MARKET DATA GATE

Formal benchmark claims still require a historical market dataset with:

- adjusted daily OHLCV;
- delisted securities;
- historical ticker/security identity;
- split/dividend basis;
- missing/stale bar accounting;
- SPY benchmark;
- delayed-entry and MAE capability;
- trailing dollar ADV;
- PIT market-cap support or explicit market-cap-missing policy.

Do not use current market cap historically and do not silently drop firms that later delisted.

Architecture direction remains vendor-neutral:

`historical market provider -> canonical market CSV -> existing backtester`

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

Diagnostics include raw return, SPY excess, mean/median, win rate, downside tail, MAE, event count, attrition, missing outcomes, and delisting-aware outcomes.

Simple benchmark family includes any qualified purchase, predefined dollar buckets, unique buyer count, independent-owner clusters, company-level aggregated buying, and canonical opportunistic buying once warm-up history is ready.

---

## DEVELOPMENT / VALIDATION / OOS BOUNDARY

- warm-up: **2013-2015** history only
- development: **2016-2020**
- validation: **2021-2022**
- sealed OOS: **2023+**

Do not open OOS until transaction eligibility, transforms, benchmark family, feature definitions, weights/thresholds, deduplication policy, inference, execution rule, missing-data policy, and OOS subgroup reports are frozen.

---

## NEXT EXECUTION SEQUENCE

1. Monitor run **35060455633** and require all 2013-2015 source-build jobs to pass.
2. Require all **12 warm-up quarter** hydration jobs to pass and persist release assets under `research-sec-warmup-v1`.
3. Verify the warm-up completeness gate and `sec-pit-warmup-2013-2015-index.json` with `oosOpened = false`.
4. Add deterministic **PIT amendment reconciliation** and quantify quarantine/unlinked rates.
5. Finalize historical security identity and adjusted/delisted market-data join.
6. Build the predeclared simple insider benchmarks on development 2016-2020 and confirm them on validation 2021-2022.
7. Only after simple baselines are credible, run the insider-information feature tournament.
8. Then test one-at-a-time turning/technical overlays and dependence-aware statistical robustness.
9. Freeze methodology before any request to inspect 2023+ OOS.

---

## DO NOT DO

- Do not inspect 2023+ filings, outcomes, or performance without explicit owner authorization.
- Do not tune production `config/scoring.v1.yaml` or `config/scoring.v1.lock.json` from exploratory results.
- Do not treat hydration PASS as evidence of alpha.
- Do not classify missing historical 10b5-1 structured data as confirmed non-plan trading.
- Do not use current ticker or market-cap mappings as historical truth.
- Do not skip failed quarters to keep a workflow green; acquisition remains fail-closed.
