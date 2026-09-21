# Phase-1 feature tournament Stage-B continuity-scope gate

Originally frozen 2026-09-21 before Stage-A coverage/cutpoint output was
observed. The B0 evaluation-session boundary correction from 24,192 to 24,190
events was frozen before the successful strict Stage-A run and before any
Stage-B feature outcome is opened. This document records that corrected,
immutable Stage-A scope.

## Purpose

Create the exact event-horizon universe that must receive a performance-blind
security-continuity audit before any insider-feature forward outcome is opened.

## Source

Only the immutable Stage-A feature matrix from release
`research-phase1-insider-feature-tournament-stage-a-v1` may define the event
universe.

Pinned Stage-A archive:

- asset: `phase1-insider-feature-tournament-stage-a-v1.tar.gz`;
- SHA-256: `sha256:06bd11f7ea2352d95e0b3bcdb997af869b6b020c46c224e5ac942bb9a0eccb0d`.

Expected frozen event scope:

- benchmark event unit: B0 exact-entry issuer event;
- events: **24,190**;
- distinct issuers: **4,729**;
- evaluation sessions: 2016-2020;
- issuer deduplication: 20 XNYS sessions;
- no forward-return, SPY-excess, MAE or robustness field may be present/read.

The two previously counted boundary spillovers whose first eligible evaluation
session is 2021-01-04 are outside the tournament's 2016-2020 evaluation-session
scope. Their exclusion is key/date based and does not use forward outcomes.

## Event-horizon expansion

Every Stage-A event is expanded mechanically to the already-frozen horizons:

- 21 XNYS sessions;
- 63 XNYS sessions;
- 126 XNYS sessions;
- 252 XNYS sessions.

Expected rows: **96,760**.

Target session is exactly `horizon` XNYS sessions after the exact Stage-A
entry session. No nearest/later market bar may define the target.

The expansion reads the XNYS calendar only. It does not read market prices.

## Frozen key

Each scope row contains exactly the identity needed by later continuity work:

- eventNumber;
- issuerCik;
- historical ticker;
- evaluationSession;
- entrySession;
- horizon;
- targetExitSession.

The scope-key SHA-256 is computed from those fields in eventNumber/horizon
order and becomes immutable after the pinned Stage-A source asset is consumed.

## Boundary

- performanceRead=false;
- priceFieldsRead=[];
- featureOutcomesRead=false;
- validationOpened=false;
- oosOpened=false;
- productionScoringChanged=false;
- 2023+ remains sealed.

This scope does not itself decide continuity. A later performance-blind
continuity ledger/resolution stage must classify every affected row and reach
**zero unresolved** before 2016-2018 feature discovery outcomes may be read.
