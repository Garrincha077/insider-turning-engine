# Phase-1 current status — 2026-09-20

This is the compact current-state checkpoint. For operational continuation,
docs/HANDOFF.md remains authoritative. Older dated progress files are retained
as audit history.

## Benchmark family

| Benchmark | Meaning | State |
| --- | --- | --- |
| B0 | any qualified open-market purchase | development descriptive complete |
| B1 | canonical CMP opportunistic purchase | development + corrected continuity/robustness/tail/year/temporal-clustering work complete |
| B2 | independent-owner cluster | development complete |
| B3 | company net buying | data/definition/raw/event/identity PASS; coverage-first development run active |
| B4 | B1 AND B2 exact-session intersection | development complete |

## B3 data state

- original P/S PIT history: 40/40 quarters PASS;
- original P/S filings 2013-2022: 570,291;
- amendment scope run 35471756336: PASS;
- supporting evidence run 35472366209: 1,551/1,551 supporting predecessors and 596/596 zero-transaction amendments, 0 failures;
- lifecycle reconciliation run 35499189795: 8/8 shards PASS + merge PASS;
- reconciliation status: B3_PS_AMENDMENT_RECONCILIATION_PASS;
- linked amendment rows: 31,048;
- reconciled revision rows: 2,320,279;
- effective qualified P/S rows at end-2022: 1,570,066;
- B3 definition release: research-phase1-b3-definition-v1;
- B3 development performance: not opened;
- 2023+ OOS: sealed;
- production scoring: unchanged.

## Immediate sequence

1. Complete raw B3 signal candidates 2016-2020 without outcomes.
2. Apply exact XNYS evaluation/entry mapping and frozen 20-session issuer dedup.
3. Freeze/assert final B3 event construction.
4. Run B3 development performance with outcomes bounded through 2022.
5. Run dependence-aware robustness and compare B0-B4.
6. Move to the feature tournament.
7. Test turning overlays only after the insider-only component is defensible.
8. Freeze full methodology before 2021-2022 validation.
9. Open 2023+ only with explicit authorization after freeze/validation.


## B3 raw signal universe

Recovery run 35500436177 completed successfully.

- raw candidates: **147,164**;
- distinct issuers: **5,606**;
- by year: 2016 = 30,038; 2017 = 24,053; 2018 = 31,166; 2019 = 30,553; 2020 = 31,354;
- market data joined: no;
- returns read: no;
- development performance computed: no;
- validation performance computed: no;
- OOS opened: no;
- production scoring changed: no;
- persistent release: research-phase1-b3-signal-input-v1;
- asset digest: sha256:c39c704bd59e861397be42f8b9a40fa5a6674d68e1cf088372f2f2fdf983ec87.

Next gate: exact XNYS evaluation/entry mapping plus frozen 20-session issuer dedup before outcomes.


## B3 pre-outcome event construction

Workflow run 35501673775 completed successfully.

- raw candidates: 147,164;
- development evaluation candidates: 147,138;
- boundary excluded: 26;
- dedup suppressed: 111,309;
- retained events: **35,829**;
- distinct retained issuers: **5,606**;
- returns read: no;
- market prices read: no;
- OOS opened: no.

Persistent release: research-phase1-b3-event-construction-v1.

Current next gate: PIT identity attachment and exact frozen signal-lineage
verification before any B3 market return is read.


## B3 PIT identity attachment

Workflow run 35501855162: PASS.

- source events: 35,829;
- exact signal lineage verified: yes;
- identity eligible: 34,472;
- identity coverage: 96.2126%;
- distinct eligible issuers: 5,420;
- quarantined: 1,357;
- missing real ticker: 1,248;
- multiple real tickers: 89;
- ticker/session CIK collision events: 20;
- current ticker fallback: no;
- fuzzy identity mapping: no;
- prices/returns read: no.

Persistent release: research-phase1-b3-identity-v1.
