# Phase-1 feature tournament Stage-B continuity audit gate

Frozen: 2026-09-21 after the strict Stage-B event-horizon scope was published
and before any feature forward outcome was opened.

## Purpose

Run the existing Phase-1 security-continuity machinery over the exact frozen
feature-tournament B0 scope. This stage is diagnostic and performance-blind.
It may identify unresolved rows; it may not classify them by looking at returns.

## Immutable source

Source release:

- `research-phase1-feature-tournament-stage-b-continuity-scope-v1`
- asset: `stage-b-continuity-scope.json`
- asset SHA-256:
  `sha256:db75f751fdfbfe85a715cc0eed00bab4026fce640ce7f81d9b4657820add1ced`
- scope-key SHA-256:
  `sha256:b57c748178ef73741d4ea6dc49bb1618f66442df9f01bab519803e0284f856fd`
- Stage-A source-key SHA-256:
  `sha256:ac7deace7c11ae9565faa4615d8ea345f115535479d44e073d3dfb860758f307`

Expected scope:

- 24,190 B0 issuer events;
- 4,729 distinct issuers;
- horizons 21 / 63 / 126 / 252 XNYS sessions;
- 96,760 event-horizon rows.

## Event adapter

The scope JSON is mechanically collapsed to one row per event with the four
already-frozen target sessions. The adapter may read only:

- eventNumber;
- issuerCik;
- historical ticker;
- evaluationSession;
- entrySession;
- horizon;
- targetExitSession.

It may not read prices or outcomes.

## Corporate-action inventory

The audit rebuilds a bounded Alpaca corporate-action inventory for the exact
feature-tournament historical ticker universe using the already frozen
2016-01-01 through 2022-12-31 provider window and the already frozen 13 action
types.

No 2023+ action is requested or accepted.

## Market continuity evidence

Only the frozen adjusted Alpaca SIP market archive for 2016-2022 is used to
establish presence/absence of regular-session bars and the already frozen
10-XNYS-session long-internal-gap rule.

OHLC values and realized returns are not selection inputs to the continuity
classification.

## Initial fixtures

The initial audit uses
`research/phase1-feature-tournament-continuity-empty-fixtures-v1.json`.

This deliberately does not inject prior B1/B3 case resolutions into the first
audit. After the exact unresolved key set is known, a later performance-blind
resolution stage may reuse prior frozen B1/B3 evidence only where the full
identity/event-horizon keys match and may gather new primary evidence for the
remaining rows.

## Required output

The audit must preserve:

- `performanceRead=false`;
- `researchOnly=true`;
- `oosOpened=false`;
- `productionScoringChanged=false`;
- `eventRowsScanned=24190`;
- `eventHorizonRows=96760`;
- `gapThresholdSessions=10`.

The unresolved count is intentionally **not predeclared**. Whatever the frozen
audit finds becomes the next exact resolution scope.

## Progression boundary

A green audit authorizes only:

1. freeze the exact unresolved key set;
2. classify it performance-blind using already frozen continuity semantics and
   primary evidence;
3. require zero unresolved rows.

Feature discovery returns remain closed until that zero-unresolved contract is
published. Validation 2021-2022 remains unopened for selection, 2023+ remains
sealed, and production scoring is unchanged.
