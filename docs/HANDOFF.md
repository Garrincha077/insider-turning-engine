# Insider Turning Engine — HANDOFF

_Last updated: 2026-09-20_

This is the operational continuation point for a new ChatGPT/Codex session. Read this file first, then `docs/research-log.md`, `docs/research-predeclared-spec.md`, and `docs/P0_PHASE1_IMPLEMENTATION.md`.

## FIRST ACTIONS IN A NEW CHAT

1. Open GitHub repository Garrincha077/insider-turning-engine, branch research/b3-ps-pit-history.
2. Read this HANDOFF first. Treat older dated progress files as historical audit trail unless this file explicitly points to them as the current gate.
3. Treat the exact-calendar P0 market audit as the authoritative market-data gate. Current tier: **C_EXPLORATORY**.
4. Treat Phase-1 B0, B1, B2 and B4 development outputs as completed descriptive/research benchmarks, not production evidence.
5. Treat the B3 P/S history, B3 amendment reconciliation, and B3 definition freeze as completed data/methodology gates.
6. Current active task: complete the performance-blind B3 raw-signal input build, then map it to exact XNYS execution sessions before any B3 development performance is read.
7. Keep sealed OOS **2023+ unopened**.
8. Do **not** change production scoring, weights, thresholds, signal states, alerts, or production methodology unless the owner explicitly asks.

---

## PROJECT / GITHUB SYNCHRONIZATION

When this repository is used through a ChatGPT Project, uploaded Project files
are context snapshots rather than a live mirror.

Before continuing work, compare the Project snapshot with the live
`research/b3-ps-pit-history` branch, this live HANDOFF, and relevant GitHub
Actions/releases.

Conflict rule:

- verified live GitHub wins for current code, workflow/release status and current operational state;
- this live HANDOFF wins for current research progress/status;
- frozen/predeclared specs and gates remain authoritative for the methodology they froze;
- newer code or summaries must not silently override a frozen methodology after results are known;
- dated progress/result files remain historical audit trail;
- stale Project copies never justify rerunning, skipping or reinterpreting a gate.

See `CHATGPT_PROJECT_SYNC_POLICY.md` for the full rule.

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

## B3 COMPANY NET BUYING — CURRENT STATUS 2026-09-20

B3 is no longer blocked by missing sale history.

### Original P/S PIT history — COMPLETE

Persistent release: research-sec-ps-pit-v1.

- original Form 4/5 P/S universe, 2013-2022: **570,291 filings**;
- 40 / 40 quarters PASS;
- buy-only: 168,334;
- sale-only: 400,230;
- mixed buy/sale: 1,727;
- historical clock remains knowledgeAt == acceptedAt;
- 2023+ remained sealed.

The 2014 Q3 discovery incident is resolved. The final recovery run was
35469045909, including the bounded verified archive fallback.

### B3 amendment scope — COMPLETE

Workflow run: 35471756336.

Frozen scope results:

- 39,817 transaction-bearing amendments;
- 2,174 zero-transaction amendments observed;
- 1,551 unique supporting predecessor filings required;
- 596 zero-transaction amendments on P/S roots;
- ambiguous/unresolved evidence remains explicit quarantine rather than fuzzy matching.

### Supporting evidence hydration — COMPLETE

Workflow run: 35472366209.

- supporting predecessors: **1,551 / 1,551 hydrated**;
- zero-transaction amendments: **596 / 596 hydrated**;
- failures: **0**;
- all historical knowledge clocks remain SEC acceptance-time based.

### P/S lifecycle reconciliation — PASS

Workflow run: 35499189795.

- issuer-safe reconciliation shards: **8 / 8 PASS**;
- deterministic merge: **PASS**;
- status: B3_PS_AMENDMENT_RECONCILIATION_PASS;
- linked amendment rows: **31,048**;
- reconciled revision rows: **2,320,279**;
- effective qualified P/S rows at end-2022: **1,570,066**;
- research quarantine rows: **23,986**;
- resolver quarantine rows: **28**;
- all 596 zero-transaction amendments on P/S roots were explicitly classified;
- amendmentsReconciledForPsUniverse=true;
- oosOpened=false;
- productionScoringChanged=false.

### B3 definition — FROZEN BEFORE PERFORMANCE

Persistent release: research-phase1-b3-definition-v1.

Frozen primary definition:

- 30-calendar-day company window;
- qualified non-derivative priced P/A buys and S/D sales;
- buy/sale dollars = shares × price;
- net dollars = buy dollars - sale dollars;
- gross dollars = buy dollars + sale dollars;
- net-buying intensity = net / gross;
- raw positive-net candidate requires buy dollars > 0 and net dollars > 0;
- no role, direct/indirect, or 10b5-1 score weighting;
- downstream 20-XNYS-session issuer dedup remains required;
- development period 2016-2020;
- outcome data may not exceed 2022-12-31;
- 2023+ remains sealed.

No B3 development performance has been opened yet.

### Current active step

The first raw-signal build hit GitHub runner-memory limits after reconciliation
had already passed. The recovery implementation streams by issuer and reuses
the persisted reconciliation and frozen definition rather than recomputing the
eight shards.

Current recovery workflow: Recover Phase-1 B3 raw signal inputs.
The next gate after a PASS is exact XNYS evaluation/entry mapping plus the
frozen 20-session issuer dedup, still without reading development outcomes.

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

The current frozen/research benchmark family is:

| Benchmark | Definition | Current state |
| --- | --- | --- |
| **B0** | any qualified open-market purchase | development descriptive run complete |
| **B1** | canonical CMP-style opportunistic purchase | development run + continuity-corrected robustness/tail/year/temporal-clustering work complete; formal OOS still blocked |
| **B2** | independent-owner cluster, primary 30 days and >=2 owner CIKs | development run complete |
| **B3** | company net buying using complete PIT buy/sale history | data gate PASS, definition frozen, raw development signal construction in progress |
| **B4** | exact same-issuer + same-XNYS-session intersection of B1 and B2 | development run complete |

Primary horizons remain 21/63/126/252 XNYS sessions, with 126 primary.

Known development-only descriptive comparison at 126 sessions before B3:

- B0 mean SPY excess: about +5.20%;
- B1 mean SPY excess: about +9.79%;
- B2 mean SPY excess: about +4.14%;
- B4 mean SPY excess: about +4.04%.

These are not sufficient production-alpha evidence. B1 remains right-tail
sensitive, which is why corrected robustness and temporal-clustering gates were
added.

Formal inference must remain dependence-aware; no benchmark is promoted from an
IID event bootstrap alone.

---

## DEVELOPMENT / VALIDATION / OOS BOUNDARY

- warm-up: **2013-2015** history/context only
- development: **2016-2020**
- validation: **2021-2022**
- sealed OOS: **2023+**

Do not open OOS until transaction eligibility, transforms, benchmark family, feature definitions, weights/thresholds, deduplication policy, inference, execution rule, missing-data policy, and OOS subgroup reports are frozen.

---

## NEXT EXECUTION SEQUENCE

1. Finish and persist the **performance-blind B3 raw signal universe** for 2016-2020.
2. Map B3 raw candidates to the exact XNYS evaluation/entry clock and apply the frozen **20-session issuer dedup**, still without outcomes.
3. Freeze/assert the final B3 event construction artifact.
4. Run the first B3 development performance on **2016-2020 only**, with outcomes bounded through 2022.
5. Run B3 dependence-aware robustness: calendar-time/HAC, issuer clustering, tail sensitivity, year stability and concentration diagnostics.
6. Compare B0/B1/B2/B3/B4 as a Phase-1 benchmark family without post-hoc threshold changes.
7. Move into the insider **feature tournament** only after the simple benchmark family is understood.
8. After feature selection, test the **Turning overlay** incrementally against the insider-only model.
9. Freeze the complete methodology before opening validation 2021-2022.
10. Keep 2023+ sealed until development/validation methodology is frozen and the owner explicitly authorizes the OOS step.

---

## DO NOT DO

- Do not inspect 2023+ filings, market outcomes, or performance without explicit owner authorization.
- Do not tune production `config/scoring.v1.yaml` or `config/scoring.v1.lock.json` from exploratory results.
- Do not treat data-gate PASS or a positive B0 mean as evidence of alpha.
- Do not classify missing historical 10b5-1 structured data as confirmed non-plan trading.
- Do not use current ticker or market-cap mappings as historical truth.
- Do not silently substitute a later bar when an exact XNYS session is missing.
- Do not silently drop missing or delisted outcomes.
