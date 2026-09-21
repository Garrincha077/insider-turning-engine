# Phase-1 insider feature tournament confirmation execution gate

Frozen: 2026-09-21 after the immutable 2016-2018 discovery release and before
any 2019-2020 feature-tournament outcome is read.

## Immutable discovery selection

Source:
- release: `research-phase1-insider-feature-tournament-discovery-v1`
- asset: `discovery-results.json`
- SHA-256:
  `sha256:181a59eefec56eb38987e430b75538de28ee473fd65316d6b782de7941c7fadc`

Discovery scope:
- 14,340 events;
- 3,836 distinct issuers;
- primary horizon: 126 XNYS sessions;
- confirmationOpened=false;
- validationOpened=false;
- oosOpened=false.

Exactly three family candidates are authorized for confirmation:

1. **F1_ABS_PLUS_FRACTION_POST**
   - family: F1;
   - coverage: GENERAL_ELIGIBLE;
   - preferred: frozen Stage-A HIGH_HIGH boolean = true;
   - complement: false.

2. **F2_DIRECT_VS_INDIRECT**
   - family: F2;
   - coverage: GENERAL_ELIGIBLE;
   - discovery orientation: **INDIRECT_ONLY preferred**;
   - complement: DIRECT_ONLY.

3. **F4_RECLAIM_PERSIST_5**
   - family: F4;
   - coverage: GENERAL_ELIGIBLE;
   - preferred: true;
   - complement: false.

F3 has `NO_FAMILY_CANDIDATE` and may not enter confirmation.

No alternate F1/F2/F3/F4 variant, threshold, direction or orientation may be
substituted if a candidate fails confirmation.

## Confirmation event scope

Only events with evaluation sessions from **2019-01-01 through 2020-12-31**
may be scored.

Market observations from 2021-2022 may be used only as target-session prices
needed to mature the already-frozen 2019-2020 confirmation events. They do not
authorize evaluation of any 2021-2022 signal/event and do not open validation.

2023+ remains sealed.

## Frozen upstream evidence

Stage A:
- release: `research-phase1-insider-feature-tournament-stage-a-v1`;
- archive SHA-256:
  `sha256:06bd11f7ea2352d95e0b3bcdb997af869b6b020c46c224e5ac942bb9a0eccb0d`.

Stage-B initial continuity audit:
- archive SHA-256:
  `sha256:77066ec138f53c0572a206559294768c6c898270ba6dcc3b2429ac7ddddab88f`.

Stage-B final continuity:
- asset: `stage-b-final-continuity.json`;
- SHA-256:
  `sha256:24947122c8fa776dc6f5e8f628c5b45cdbec6551cf15df334421b405439b4518`;
- 210/210 classified;
- zero unresolved.

Provider-completeness amendment:
- release:
  `research-phase1-feature-tournament-provider-completeness-amendment-v1`;
- asset: `provider-completeness-amendment.json`;
- SHA-256:
  `sha256:faf787e918b953dcffbcc2b714c34873d6228031e25a09e509ee58e1a067fbb2`;
- 13 already-classified provider rows receive primary-evidence terminal
  consideration semantics;
- discovery overlap = 0;
- validation-event overlap = 0.

This amendment was created after an initial confirmation execution failed
closed on incomplete provider merger semantics and **before any successful
2019-2020 confirmation outcome run**. It does not alter discovery selection,
thresholds, orientation or PASS rules.

The discovery valuation/grouping helper source is frozen at Git blob:
`4bf0717f1d866dfbd282dd365f6e466f0cc92900`.

## Frozen market inputs

Use only `research-market-alpaca-v1`, 2016-2022. Annual SHA-256 digests:

- 2016: `df531881b67f9f42e40b2c2fff03f6ca19c0b5f9b13deb6190132b7987fb69ca`
- 2017: `7515a3807249bbead7cf7edc2a2aa1d267b01fc49ddf72885c40746520e762d0`
- 2018: `4a99eafc6cac31ee30d23bf82c1feccb4bbe14919f7c4df2d59e792f8a5b2f54`
- 2019: `c701d559a7d5128fd07ec19e2d5d3b39eb5ae8c0d9bd51a8b278d34c9b6f9238`
- 2020: `5577a548576e81c5e468b9e5027c9a8ec1ba8e1dd14ed38a0f223e797c5358e2`
- 2021: `550ff3456ad16a045692a5d9d567d13ef2b8788283f4c39c3baa5d8aecd7a704`
- 2022: `8a71037090cda77bc3937409ffa9fcb9c463545b5f3a7d9a73995a92759d187a`

Holder valuation semantics, SPY excess clock, top-1%-removal rule, context
quintile convention and benchmark overlap definitions remain exactly those
frozen before discovery.

## Frozen confirmation PASS rule

For each of the three candidates independently:

- preferred mature 126d N >= **150**;
- preferred distinct issuers >= **75**;
- pooled event-weighted incremental mean > 0;
- pooled issuer-equal-weight incremental mean > 0;
- pooled entry-session-equal-weight incremental mean > 0;
- pooled top-1%-removed incremental mean > 0;
- 2019 event-weighted incremental mean > 0;
- 2020 event-weighted incremental mean > 0;
- incremental mean outside the frozen bottom DOLLAR_ADV_20 quintile > 0.

Only an exact pass receives
`CONFIRMED_DEVELOPMENT_CANDIDATE`.

Failure is final for this tournament phase. No reselection, alternate cutpoint,
orientation or replacement variant is allowed.

## Boundary after confirmation

Confirmation may freeze zero to three candidates for later 2021-2022
validation. It does not itself open validation.

This stage does not:
- inspect outcomes of 2021-2022 evaluation events;
- open 2023+ OOS;
- fit composite weights;
- introduce a technical/Turning overlay;
- change production scoring.
