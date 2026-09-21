# Phase-1 insider feature tournament discovery execution gate

Frozen: 2026-09-21 after Stage-B continuity reached 210/210 classified and
before any 2016-2018 feature-tournament outcome is read.

## Authorized scope

This stage may open outcomes only for feature-tournament events with
`evaluationSession <= 2018-12-31`.

It may use market observations after 2018 only to mature the already-selected
21/63/126/252-session outcomes of those discovery events. Events evaluated in
2019-2020 are not scored in this stage. 2021-2022 validation and 2023+ OOS
remain closed.

Primary selection horizon: **126 XNYS sessions**.

## Immutable inputs

Stage A:
- release: `research-phase1-insider-feature-tournament-stage-a-v1`
- archive: `phase1-insider-feature-tournament-stage-a-v1.tar.gz`
- SHA-256:
  `sha256:06bd11f7ea2352d95e0b3bcdb997af869b6b020c46c224e5ac942bb9a0eccb0d`

Stage-B initial continuity audit:
- release: `research-phase1-feature-tournament-stage-b-continuity-audit-v1`
- archive: `feature-tournament-stage-b-continuity-audit-v1.tar.gz`
- SHA-256:
  `sha256:77066ec138f53c0572a206559294768c6c898270ba6dcc3b2429ac7ddddab88f`

Final Stage-B continuity contract:
- release: `research-phase1-feature-tournament-stage-b-final-continuity-v1`
- asset: `stage-b-final-continuity.json`
- SHA-256:
  `sha256:24947122c8fa776dc6f5e8f628c5b45cdbec6551cf15df334421b405439b4518`
- classified rows: **210 / 210**
- unresolved rows: **0**

Market outcome assets are restricted to frozen
`research-market-alpaca-v1` annual archives 2016-2020:
- 2016 `sha256:df531881b67f9f42e40b2c2fff03f6ca19c0b5f9b13deb6190132b7987fb69ca`
- 2017 `sha256:7515a3807249bbead7cf7edc2a2aa1d267b01fc49ddf72885c40746520e762d0`
- 2018 `sha256:4a99eafc6cac31ee30d23bf82c1feccb4bbe14919f7c4df2d59e792f8a5b2f54`
- 2019 `sha256:c701d559a7d5128fd07ec19e2d5d3b39eb5ae8c0d9bd51a8b278d34c9b6f9238`
- 2020 `sha256:5577a548576e81c5e468b9e5027c9a8ec1ba8e1dd14ed38a0f223e797c5358e2`

Benchmark overlap diagnostics are pinned to:
- B1 events `sha256:7f0da85bb561e0457ed85249376bb4fca1a0a7e996f424d81e23813b5ad6bbdb`
- B2 events `sha256:1d905cac1fd10a1051c4f0734fac5247a7a61a114a5baf29a42a395a361f1688`
- B4 events `sha256:dd8ea0454e9a608ba42b11fc393fa93ad83c3f0eedd04d9e5dee5624abb0ee7f`
from `research-phase1-baselines-v1`;
- B3 corrected archive
  `sha256:b7b058a2e82cb072876804178e9af6e247fa9dc70b6f93a3f3c8e32ffe67c8be`
from `research-phase1-b3-continuity-corrected-development-v1`.

## Holder-outcome reconstruction

Do not use canonical B0 return values.

For every discovery event/horizon, use the frozen Stage-B ledger. Rows already
classified there keep their frozen semantics. Rows whose ledger state was
`UNRESOLVED_CONTINUITY` must use the exact matching row in the final 210-row
contract.

Valuation rules are the already-frozen continuity rules:
- ordinary adjusted continuity: one original-ticker share;
- same-security symbol change: one successor share;
- provider cash merger/redemption: frozen cash rate;
- provider stock merger: acquirer_rate / acquiree_rate shares;
- provider stock-and-cash merger: the same stock ratio plus
  cash_rate / acquiree_rate;
- frozen `STOCK_DIVIDEND_QUANTITY` on adjusted market data uses one market
  share while preserving the legal quantity only as audit metadata;
- multi-component consideration values every frozen basket leg;
- `DISCONTINUOUS_NO_COMPLETE_VALUATION` remains missing.

SPY excess return uses the same entry open and target-session close clock.

## Frozen group construction

Continuous quintiles use Stage-A discovery cutpoints:
- Q1: value <= q20
- Q2: q20 < value <= q40
- Q3: q40 < value <= q60
- Q4: q60 < value <= q80
- Q5: value > q80

The Stage-A `F1_ABS_PLUS_FRACTION_POST` boolean is used as already frozen;
it is not recomputed here.

F4 distance variants both use Stage-A
`F4_DISTANCE_TO_BASIS` cutpoints:
- `F4_DISTANCE_ABOVE`: Q5 versus Q1-Q4
- `F4_DISTANCE_BELOW`: Q1 versus Q2-Q5

F2 contains only DIRECT_ONLY and INDIRECT_ONLY in its primary contrast.
Discovery orientation is chosen by the larger event-weighted 126d SPY-excess
mean. Exact ties choose DIRECT_ONLY as preferred. The chosen orientation is
frozen for confirmation.

## Frozen robustness calculations

All comparisons are inside the same feature-observed cohort.

- event-weighted incremental mean = preferred excess mean minus complement
  excess mean;
- issuer-EW = difference between the mean of issuer-level excess means in the
  two groups;
- entry-session-EW = difference between the mean of session-level excess means
  in the two groups;
- top-1%-removed = pool all mature preferred+complement rows, sort by 126d
  SPY-excess descending and then by stable event key, remove exactly
  `ceil(0.01 * N)` rows, then recompute the event-weighted increment;
- discovery-year increments are event weighted separately for 2016, 2017 and
  2018;
- outside-bottom-ADV increment uses rows with observed `DOLLAR_ADV_20`
  strictly above the frozen discovery q20 cutpoint.

Context-stratum diagnostics use the same frozen quintile convention for
DOLLAR_ADV_20, DOLLAR_ADV_60 and STOCK_PRICE. PIT market cap remains explicitly
unavailable; no substitute is allowed.

## Advancement

The predeclared tournament rules remain unchanged.

A variant may pass discovery only when:
- its Stage-A coverage class is GENERAL_ELIGIBLE or SPECIALTY_ELIGIBLE;
- preferred mature 126d N >= 200;
- preferred distinct issuers >= 100;
- event-weighted, issuer-EW, entry-session-EW, top-1%-removed and
  outside-bottom-ADV increments are all > 0;
- at least two of 2016/2017/2018 have positive event-weighted increments.

Within each family, only passing variants participate in the frozen tie-break:
1. top-1%-removed increment descending;
2. issuer-EW descending;
3. entry-session-EW descending;
4. event-weighted increment descending;
5. variant ID ascending.

At most one candidate per F1/F2/F3/F4 advances. If none passes, the family
result is `NO_FAMILY_CANDIDATE`.

## Boundary after this stage

The discovery release may freeze family candidates and their exact orientation,
variant and Stage-A thresholds for a later confirmation stage.

This discovery stage does **not**:
- read 2019-2020 event outcomes;
- open 2021-2022 validation;
- open 2023+ OOS;
- fit composite weights;
- add feature variants;
- change production scoring.
