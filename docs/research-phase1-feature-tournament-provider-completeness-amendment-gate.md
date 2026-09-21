# Phase-1 feature tournament provider-completeness amendment gate

Frozen: 2026-09-21 after the 2016-2018 discovery release and before any
successful 2019-2020 confirmation outcome run.

## Why this amendment exists

The original Stage-B continuity ledger correctly isolated **210 unresolved**
event-horizon rows and the final Stage-B v1 contract subsequently classified
all 210.

During the first confirmation execution, a separate completeness defect was
found among rows that the initial ledger had already classified as
`TRANSFORMED_HOLDER_CONSIDERATION`: four provider stock-merger actions had a
valid acquiree/acquirer economic ratio but an empty `acquirer_symbol`.

Those rows therefore were not part of the 210 unresolved set, yet could not be
valued to a terminal listed security without additional evidence.

This amendment is deliberately separate from the immutable 210-row final
contract. It supplies only the missing holder-consideration semantics for the
affected already-classified provider rows.

## Frozen affected scope

Exactly:
- **13 event-horizon rows**
- **7 events**
- **4 provider action IDs**
- evaluation years: **2019-2020 only**
- discovery overlap: **0 rows**
- validation-event overlap: **0 rows**

Ticker/action partition:
- WSTL: 5 rows
- QES: 4 rows
- PAAC: 3 rows
- MGYR: 1 row

The initial Stage-B continuity audit source remains:
- release:
  `research-phase1-feature-tournament-stage-b-continuity-audit-v1`
- archive:
  `feature-tournament-stage-b-continuity-audit-v1.tar.gz`
- SHA-256:
  `sha256:77066ec138f53c0572a206559294768c6c898270ba6dcc3b2429ac7ddddab88f`

## Frozen primary evidence

Repository contract:
`research/phase1-feature-tournament-provider-completeness-primary-evidence-v1.json`

Git blob:
`3b6a4c9976f769fc5cd7a67f97e1b18f7fee65b6`

The evidence contract was frozen before any successful confirmation outcome
run and opens no feature result.

### QES

Provider action:
`3f1999bc-0671-4ac9-832d-34a273de33b0`

The provider inventory carries the pre-reverse-split 0.4844 acquirer ratio and
no acquirer symbol. Primary SEC evidence establishes that KLXE completed a
1-for-5 reverse split immediately before the merger and that each QES share
ultimately received **0.0969 KLXE shares**.

Frozen amendment:
- effective date: 2020-07-28
- successor: KLXE
- quantity: 0.0969
- cash: 0

### WSTL

Provider action:
`025514e5-df61-4736-abbd-958aef5d7747`

The transaction was a 1-for-1,000 reverse split immediately followed by a
1,000-for-1 forward split. Holders below 1,000 shares were cashed out at
**$1.48 per share**, while larger holders remained shareholders.

The existing performance engine values one original entry share. Under that
already-frozen valuation unit, the modeled passive holder is below the
1,000-share threshold.

Frozen amendment:
- effective date: 2020-10-01
- successor: none
- quantity: 0
- cash per entry share: 1.48
- holder policy: `ONE_ENTRY_SHARE`

### PAAC

Provider action:
`5952fed5-9d9e-4228-b719-dab4e78cb1cc`

Primary evidence establishes that each PAAC common share was exchanged for one
Lion Group Holding security and that the public successor ADS trades as
**LGHL**.

Frozen amendment:
- effective date: 2020-06-16
- successor: LGHL
- quantity: 1
- cash: 0

### MGYR

Provider action:
`fd86b4fb-0687-4693-bf79-cbdef0e8bb19`

Primary SEC evidence establishes that each public pre-conversion MGYR share was
exchanged for **1.2213 new MGYR shares** in the second-step conversion.

Frozen amendment:
- effective date: 2021-07-14
- successor: MGYR
- quantity: 1.2213
- cash: 0

## Market-adjustment compatibility

The frozen Alpaca outcome corpus uses `adjustment=all`.

Alpaca defines this as split, cash-dividend and spin-off adjustment. Merger and
reorganization consideration is not included in that bar adjustment. Therefore
the QES, PAAC and MGYR holder exchange ratios must be applied explicitly.

WSTL is not valued from a post-action WSTL price under this overlay; the
one-entry-share holder receives the frozen cash-out consideration.

## Required amendment invariants

The amendment workflow must prove:
- initial Stage-B ledger rows = 96,760;
- exactly 13 amendment rows;
- exactly 7 affected events;
- exactly 4 action IDs;
- all source rows were already
  `TRANSFORMED_HOLDER_CONSIDERATION`;
- all had blank initial successor symbols;
- all came from provider classification;
- every amendment effective date lies within its event horizon;
- discovery overlap rows = 0;
- validation event rows = 0;
- performanceRead=false;
- featureOutcomesRead=false;
- validationOpened=false;
- oosOpened=false;
- productionScoringChanged=false.

## Progression rule

Only after this amendment is published successfully may the 2019-2020
confirmation runner be retried.

Confirmation must apply this amendment before the generic provider valuation
path. It may not use the amendment to alter:
- discovery family selection;
- feature thresholds;
- F2 orientation;
- confirmation PASS criteria;
- any 2021-2022 validation event;
- 2023+ OOS.
