# Insider Turning Engine — HANDOFF

_Last updated: 2026-09-20_

This is the operational continuation point for a new ChatGPT/Codex session. Read this file first, then `docs/research-log.md`, `docs/research-predeclared-spec.md`, and `docs/P0_PHASE1_IMPLEMENTATION.md`.

## FIRST ACTIONS IN A NEW CHAT

1. Open GitHub repository Garrincha077/insider-turning-engine, branch research/b3-ps-pit-history.
2. Read this HANDOFF first. Treat older dated progress files as historical audit trail unless this file explicitly points to them as the current gate.
3. Treat the exact-calendar P0 market audit as the authoritative market-data gate. Current tier: **C_EXPLORATORY**.
4. Treat Phase-1 B0, B1, B2 and B4 development outputs as completed descriptive/research benchmarks, not production evidence.
5. Treat the B3 P/S history, B3 amendment reconciliation, and B3 definition freeze as completed data/methodology gates.
6. Current active task: finish the performance-blind B3 security-continuity resolution for the frozen 43-row residual scope. Provider ambiguity, two SPAC-unit waves, one-sided identity, and the first multi-class/reorganization subset are resolved; corrected B3 performance stays closed until the final unresolved count is zero.
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

B3 development performance and the frozen robustness diagnostic have now been completed. The robustness progression is **BLOCK_HAC_AND_OOS**; corrected performance remains closed while security-continuity resolution is unfinished.

### Raw B3 development signal universe — COMPLETE

Recovery workflow run: 35500436177 — **SUCCESS**.

Persisted release: research-phase1-b3-signal-input-v1.

- raw performance-blind candidates: **147,164**;
- distinct issuers: **5,606**;
- 2016: 30,038 candidates;
- 2017: 24,053;
- 2018: 31,166;
- 2019: 30,553;
- 2020: 31,354;
- primary window: 30 calendar days;
- marketDataJoined=false;
- returnsRead=false;
- developmentPerformanceComputed=false;
- validationPerformanceComputed=false;
- oosOpened=false;
- productionScoringChanged=false.

Persistent asset:
b3-raw-signal-inputs-2016-2020.tar.gz
SHA-256:
c39c704bd59e861397be42f8b9a40fa5a6674d68e1cf088372f2f2fdf983ec87.

### B3 exact-XNYS pre-outcome event construction — PASS

Workflow run: 35501673775.

- 147,164 source raw candidates;
- 147,138 map to the 2016-2020 evaluation-session development cohort;
- 26 excluded by the evaluation-session boundary;
- 111,309 suppressed by the frozen <=20-session issuer dedup;
- **35,829 retained pre-outcome events**;
- **5,606 distinct issuers**;
- no market prices or returns read;
- 2023+ remains sealed.

Persistent release: research-phase1-b3-event-construction-v1.
Final event asset SHA-256:
839326d9ce1d3000a476b1d483a71a6501921c58d8012ba4daba4a09cd3d2610.

### B3 PIT identity attachment — PASS

Workflow run: 35501855162.

- frozen source events: **35,829**;
- exact signal-state lineage: **verified**;
- identity-eligible events: **34,472**;
- identity coverage: **96.2126%**;
- distinct eligible issuers: **5,420**;
- identity quarantine: **1,357**;
  - missing real ticker: 1,248;
  - multiple real tickers: 89;
  - ticker/session CIK collision: 20;
- current-ticker fallback: false;
- fuzzy mapping: false;
- market prices/returns read: false.

Persistent release: research-phase1-b3-identity-v1.
Identity asset SHA-256:
be808447f2f76bf34904f1950a0639a4b515a7a241165b4ea6267aaacc2a4d91.

### Current active gate — B3 performance-blind continuity resolution

B3 development run 35502095184 is complete at coverage tier C_EXPLORATORY.
Primary 126-session SPY excess mean is +4.09%, median -2.73%, win rate 44.84%.

The frozen robustness gate is also complete. Latest green run 35502779482
returns `BLOCK_HAC_AND_OOS` because the 126-session top-1%-removed mean is
non-positive (-0.1974%). Do not retune this warning after seeing the result.

Security-continuity work is therefore a data-validity correction, not a route
around the robustness block.

Authoritative continuity state:

- ledger run 35502394856: 264 unresolved event-horizon rows;
- deterministic candidate run 35502978548: 102 candidates / 162 residual;
- bounded P/S PIT, successor-action, SEC-title and all-Form345 evidence runs:
  35503316854 / 35503492411 / 35503698067 / 35504002615;
- strict multi-source synthesis run 35507255962: **71 new candidates**;
- residual-91 scope freeze run 35507445541: **91 rows / 35 issuer-tickers**;
- provider primary-source resolution run 35507604004: **4 / 4 provider ambiguities resolved**;
- residual-87 scope freeze run 35507696537: **87 rows / 33 issuer-tickers**;
- SPAC-unit resolution run 35507997799: **4 rows resolved**;
- one-sided identity resolution run 35508257853: **20 rows resolved**;
- residual-63 scope freeze run 35508340176: **63 rows / 27 issuer-tickers**;
- second SPAC-unit resolution run 35508586692: **8 rows resolved**;
- multi-class/reorganization resolution run 35508859857: **12 rows resolved**;
- residual-43 scope freeze run 35508922204: **43 rows / 19 issuer-tickers**;
- deterministic continuity candidates/resolutions: **221 / 264**;
- residual-43 key SHA-256:
  `sha256:be82164c63ed8c8528017ff3201d5172e818655e5c7a8fa48bd7576c7cb02cd6`;
- release: `research-phase1-b3-residual43-scope-v1`;
- final resolution contract: not created;
- corrected performance: not opened;
- 2023+ OOS: sealed;
- production scoring: unchanged.

Current work must remain performance-blind and resolve/classify the exact
43-row residual scope before a final overlay can be frozen.

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
| **B3** | company net buying using complete PIT buy/sale history | development + robustness complete; continuity resolution active at 43 frozen residual rows; HAC/OOS blocked |
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

1. Preserve the exact **43-row B3 residual continuity scope**.
2. Split remaining cases into target-specific SPAC/unit life-cycle cases and
   ordinary-share title-normalization/market-gap cases.
3. Resolve each identity from pinned primary SEC/issuer/exchange evidence only,
   without reading realized performance.
4. Do not create the final B3 continuity contract until every frozen residual
   row is deterministically classified and the unresolved count is zero.
5. Only after that zero-unresolved gate, recompute corrected B3 development
   performance with the already frozen 21/63/126/252 horizons and 126 primary.
6. Reapply the already frozen robustness semantics; do not change warning
   thresholds after the result.
7. Keep HAC/OOS blocked while the frozen progression result requires it.
8. Compare B0/B1/B2/B3/B4 only after B3 data validity is corrected.
9. Move to the insider feature tournament only after the simple benchmark
   family is understood.
10. Test the Turning overlay only after the insider-only model is defensible.
11. Freeze methodology before 2021-2022 validation.
12. Keep 2023+ sealed until explicit owner authorization after all prior gates.

---

## DO NOT DO

- Do not inspect 2023+ filings, market outcomes, or performance without explicit owner authorization.
- Do not tune production `config/scoring.v1.yaml` or `config/scoring.v1.lock.json` from exploratory results.
- Do not treat data-gate PASS or a positive B0 mean as evidence of alpha.
- Do not classify missing historical 10b5-1 structured data as confirmed non-plan trading.
- Do not use current ticker or market-cap mappings as historical truth.
- Do not silently substitute a later bar when an exact XNYS session is missing.
- Do not silently drop missing or delisted outcomes.
