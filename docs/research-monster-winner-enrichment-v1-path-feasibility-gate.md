# Monster Winner Enrichment v1 — performance-blind MFE path-feasibility gate

Frozen: 2026-09-22 after Monster Winner Enrichment v1 was predeclared and
before any M50/M100/M200/M500 or MFE price outcome is computed.

## Purpose

Prove that the frozen 2016-2020 B0 feature-tournament event universe can support
a close-to-entry holder-value path for the Monster Winner Enrichment v1 labels
without silent security substitution, silent delisting removal or price-based
classification.

This stage is **coverage/continuity only**. It must not read OHLC values and
must not compute a future return, threshold crossing, rank or monster label.

## Immutable event / feature source

Stage A release:
`research-phase1-insider-feature-tournament-stage-a-v1`.

Archive:
`phase1-insider-feature-tournament-stage-a-v1.tar.gz`.

SHA-256:
`sha256:06bd11f7ea2352d95e0b3bcdb997af869b6b020c46c224e5ac942bb9a0eccb0d`.

Expected:
- exact-entry events: **24,190**;
- distinct issuers: **4,729**;
- evaluation sessions: 2016-2020 only;
- 20-XNYS-session issuer dedup already applied.

Only event identity/timing fields are used from the Stage-A matrix in this
audit. Feature values may remain mounted but are not grouped or scored.

## Immutable continuity sources

Initial Stage-B continuity audit:

- release:
  `research-phase1-feature-tournament-stage-b-continuity-audit-v1`;
- archive:
  `feature-tournament-stage-b-continuity-audit-v1.tar.gz`;
- SHA-256:
  `sha256:77066ec138f53c0572a206559294768c6c898270ba6dcc3b2429ac7ddddab88f`;
- ledger rows: **96,760** = 24,190 × 4 horizons.

Files used:
- `ledger/continuity-ledger.csv`;
- `ca/corporate-actions.json`.

Final performance-blind continuity contract:

- release:
  `research-phase1-feature-tournament-stage-b-final-continuity-v1`;
- asset: `stage-b-final-continuity.json`;
- SHA-256:
  `sha256:24947122c8fa776dc6f5e8f628c5b45cdbec6551cf15df334421b405439b4518`;
- classified unresolved rows: **210 / 210**;
- unresolved: **0**.

For this audit only the exact **252-session** continuity row for each Stage-A
event is used.

## Frozen market-presence inputs

Release:
`research-market-alpaca-v1`.

Adjustment:
`all`.

Annual assets:

- 2016
  `sha256:df531881b67f9f42e40b2c2fff03f6ca19c0b5f9b13deb6190132b7987fb69ca`;
- 2017
  `sha256:7515a3807249bbead7cf7edc2a2aa1d267b01fc49ddf72885c40746520e762d0`;
- 2018
  `sha256:4a99eafc6cac31ee30d23bf82c1feccb4bbe14919f7c4df2d59e792f8a5b2f54`;
- 2019
  `sha256:c701d559a7d5128fd07ec19e2d5d3b39eb5ae8c0d9bd51a8b278d34c9b6f9238`;
- 2020
  `sha256:5577a548576e81c5e468b9e5027c9a8ec1ba8e1dd14ed38a0f223e797c5358e2`;
- 2021
  `sha256:550ff3456ad16a045692a5d9d567d13ef2b8788283f4c39c3baa5d8aecd7a704`;
- 2022
  `sha256:8a71037090cda77bc3937409ffa9fcb9c463545b5f3a7d9a73995a92759d187a`.

2023+ must not be downloaded or mounted.

### Permitted market columns

The feasibility runner may read only:

- `ticker`;
- `date`;
- `volume`;
- `trade_count`;
- `terminal_candidate`.

It may **not** read:

- open;
- high;
- low;
- close;
- VWAP;
- any return field.

A regular observable market row is present only when:

- `terminal_candidate != true`;
- volume > 0;
- trade_count > 0.

This reproduces the existing regular-bar presence rule without reading prices.

## Frozen 252-session path clock

For each event:

- holder entry occurs at the exact `entrySession` open;
- Stage-B 252 target remains exactly
  `targetExitSession = XNYS[entryIndex + 252]`;
- the first potential MFE observation is the **entry-session close**;
- the last potential observation is the exact 252 target-session close;
- therefore a fully observed path contains at most **253 close observation
  sessions** including the entry session.

No nearest/later-session substitution is allowed.

## Frozen holder-path routing

### Ordinary adjusted continuity

For `PRICE_CONTINUOUS_ADJUSTED` or final
`SAME_SECURITY_CONTINUITY`, require an observable regular row for the
historical ticker on each path session.

### Adjusted stock-dividend quantity

For frozen `STOCK_DIVIDEND_QUANTITY`, preserve the already-frozen adjusted
market semantics:

- market path remains one adjusted share of the same ticker;
- legal quantity remains audit metadata;
- do not multiply the adjusted market path by the legal stock-dividend factor.

### Same-security symbol change

Before the frozen effective date require the historical ticker.

On and after the frozen effective date require the frozen successor ticker.

If the provider/final evidence does not supply one deterministic effective date,
the row is not eligible for a negative monster label.

### Stock / stock-and-cash transformation

Before effective date require the historical ticker.

On and after effective date require the frozen successor ticker.

Cash is carried as cash and requires no market row.

### Cash merger / redemption

Before effective date require the historical ticker.

On and after effective date holder value is deterministic cash; every later
XNYS session is considered path-observable without a stock bar.

### Multi-component consideration

Before effective date require the historical ticker.

On and after effective date **every frozen basket component** must have an
observable regular row on the session. Missing any mandatory leg makes that
session unobservable.

### Discontinuous / incomplete valuation

For `DISCONTINUOUS_NO_COMPLETE_VALUATION`:

- pre-effective-date original-security sessions may remain observable;
- on/after the discontinuity effective date the mandatory holder-value path is
  unobservable;
- a negative MFE label cannot be assigned;
- a future positive label may only be established from a threshold crossing
  observed before the discontinuity.

The audit itself reads no price and therefore does not determine whether such a
crossing occurred.

## Frozen negative-label feasibility rule

For the primary 252-session monster label, a later negative label is permitted
only when all of the following are true:

1. exact entry identity is present;
2. 252-session continuity is deterministic;
3. no mandatory unvalued holder leg exists;
4. at least **95%** of the 253 required close-observation sessions are path
   observable;
5. the longest consecutive unobservable run is at most **5 XNYS sessions**.

Otherwise the eventual no-crossing state must be `MFE_UNKNOWN`, not negative.

Positive threshold labels remain one-sided: a later observed threshold crossing
can establish a positive label even when the path would not qualify for a
negative label.

## Required audit output

For all 24,190 events emit a row containing only identity, routing and coverage
metadata:

- event number / CIK / historical ticker;
- evaluation / entry / 252 target session;
- frozen continuity decision and transformation kind;
- effective date where applicable;
- successor / basket symbols as identifiers only;
- required path-session count;
- observable path-session count;
- coverage ratio;
- maximum consecutive unobservable sessions;
- first / last unobservable session;
- mandatory-unvalued-consideration flag;
- deterministic-effective-date flag;
- negative-label-feasible boolean;
- explicit feasibility reason.

No price, return, MFE, threshold-crossing or monster-label field may appear.

## Summary output

Report at minimum:

- total events;
- distinct issuers;
- path coverage distribution;
- count / share negative-label-feasible;
- count / share forced `MFE_UNKNOWN` if no positive crossing is later
  observed;
- reason counts;
- continuity-decision counts;
- transformation-kind counts;
- counts by evaluation year.

This summary is descriptive data-quality evidence only.

## Progression

After a successful immutable feasibility release:

1. inspect feasibility failure modes;
2. if needed, resolve only data/continuity issues without looking at prices;
3. freeze an exact Monster Winner **outcome execution contract**;
4. only then open 2016-2018 MFE/monster outcomes.

2021-2022 remain known-sample diagnostic only.
2023+ remains sealed.
Production scoring remains unchanged.
